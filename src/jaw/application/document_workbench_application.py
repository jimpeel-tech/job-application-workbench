"""Native application boundary for JAW Documents.

The browser and Job Tracker call this facade directly. It replaces the old pattern
of tunneling Workbench operations through Document Studio authoring methods and
keeps one canonical service/repository model for authoring, routing, and rendering.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .document_generation_context import DocumentGenerationContext
from .document_template_repository_channels import TemplateRepository
from .document_workbench_job_generation import generate_job, routing_state, save_routing
from .document_workbench_render import DocumentWorkbenchRenderer
from .document_workbench_resource_service import (
    delete_unreferenced_resource,
    rename_reference_symbol,
)
from .document_workbench_service import DocumentWorkbenchService
from .document_workbench_transition_service import (
    resolve_reference_transition,
    validate_reference_transition,
)


class _ContextAwareDocumentWorkbenchService(DocumentWorkbenchService):
    """Expose the selected generation context through every Workbench state."""

    def __init__(
        self,
        repository: Any,
        user_data: Any,
        generation_contexts: DocumentGenerationContext,
    ) -> None:
        super().__init__(repository, user_data)
        self.generation_contexts = generation_contexts

    def _generation_context(self, user_id: int) -> dict[str, Any]:
        return self.generation_contexts.context_mapping(user_id, require_job=False)

    def state(self, user_id: int) -> dict[str, Any]:
        state = super().state(user_id)
        return {
            **state,
            "generation_context_info": self.generation_contexts.info(user_id),
        }


class DocumentWorkbenchApplication:
    """One application-level entry point for all Workbench operations."""

    def __init__(self, database: Any, user_data: Any) -> None:
        self.database = database
        self.user_data = user_data
        self.repository = database.document_workbench_repository
        self.generation_contexts = DocumentGenerationContext(database, user_data)
        self.service = _ContextAwareDocumentWorkbenchService(
            self.repository,
            user_data,
            self.generation_contexts,
        )
        self.template_repository = TemplateRepository(self.repository, self.service)

    def state(self, user_id: int) -> dict[str, Any]:
        return self.service.state(user_id)

    def create_document(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.service.create_document(user_id, payload)

    # Template repository ------------------------------------------

    def _template_repository_dev_allowed(self) -> bool:
        active_name = str(self.user_data.read().get("active_user_name") or "").strip()
        return active_name.casefold() == "dev"

    def _repository_catalog_with_access(self) -> dict[str, Any]:
        value = self.template_repository.catalog()
        repository = dict(value.get("repository") or {})
        repository["can_download_dev"] = self._template_repository_dev_allowed()
        return {**value, "repository": repository}

    def repository_catalog(self) -> dict[str, Any]:
        return self._repository_catalog_with_access()

    def repository_download(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        channel = str(payload.get("channel") or "release").strip().casefold()
        if channel == "dev" and not self._template_repository_dev_allowed():
            raise ValueError("Download Dev is only available to the Dev user")
        version = str(payload.get("version") or "").strip() or None
        result = self.template_repository.download(version, channel=channel)
        return {**result, "catalog": self._repository_catalog_with_access()}

    def repository_open_local(self) -> dict[str, Any]:
        return self.template_repository.open_local()

    def repository_clone(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.template_repository.clone(
            user_id,
            template_id=str(payload.get("template_id") or ""),
            source=str(payload.get("source") or ""),
        )

    def checkpoint(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.service.checkpoint(user_id, payload)

    def save(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.service.save(user_id, payload)

    def _make_template_private(
        self,
        user_id: int,
        template: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        usage = self.repository.documents_for_template(user_id, str(template["id"]))
        owner_id = str(payload.get("owner_id") or "").strip()
        if not owner_id and len(usage) == 1:
            owner_id = str(usage[0]["id"])
        if not owner_id:
            raise ValueError("Choose the Document that should receive the private Template")
        owner = next((item for item in usage if str(item["id"]) == owner_id), None)
        if owner is None:
            raise ValueError("Private Template owner must currently use this Template")

        if len(usage) == 1:
            saved = self.repository.update_resource(
                user_id,
                str(template["id"]),
                visibility="private",
                state="active",
                owner_id=owner_id,
            )
            return {
                "resource": saved,
                "state": self.state(user_id),
                "template_detached": None,
            }

        source = self.service._effective(user_id, template)
        clone = self.repository.create_resource(
            user_id,
            "template",
            name=str(template.get("name") or owner.get("name") or "Template"),
            symbol=str(template.get("symbol") or "template"),
            visibility="private",
            state="active",
            owner_id=owner_id,
            content=source,
            settings=dict(template.get("settings") or {}),
        )
        self.repository.update_document(user_id, owner_id, template_id=clone["id"])
        self.service._reconcile_template(user_id, owner_id, source)
        return {
            "resource": clone,
            "state": self.state(user_id),
            "template_detached": {
                "global_template_id": str(template["id"]),
                "private_template_id": clone["id"],
                "document_id": owner_id,
            },
        }

    def update_resource(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        resource_id = str(payload.get("resource_id") or "").strip()
        current = self.repository.require_resource(user_id, resource_id)
        requested_visibility = str(payload.get("visibility") or "").strip().casefold()
        if (
            current["kind"] == "template"
            and current["visibility"] == "global"
            and requested_visibility == "private"
        ):
            return self._make_template_private(user_id, current, payload)

        result = self.service.update_resource(user_id, payload)
        if payload.get("template_id"):
            document_id = resource_id
            document = self.repository.get_document(user_id, document_id)
            if document is not None:
                template = self.repository.require_resource(user_id, document["template_id"])
                usage = self.repository.documents_for_template(user_id, template["id"])
                if len(usage) > 1 and template["visibility"] != "global":
                    self.repository.update_resource(
                        user_id,
                        template["id"],
                        visibility="global",
                        state="active",
                        owner_id=None,
                    )
                    result = {**result, "state": self.state(user_id)}
        return result

    def link(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.service.link_existing(user_id, payload)

    def delete(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        result = delete_unreferenced_resource(self.repository, user_id, payload)
        return {**result, "state": self.service.state(user_id)}

    def rename_symbol(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Handle explicit context-menu rename and inline transition transport."""

        if str(payload.get("action") or "").strip():
            return self.transition_reference(user_id, payload)
        result = rename_reference_symbol(self.repository, user_id, payload)
        return {**result, "state": self.state(user_id)}

    def transition_reference(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate once, then commit one explicit Update/Create/Remove decision."""

        validation = validate_reference_transition(self.repository, user_id, payload)
        if str(payload.get("disposition") or "").strip().casefold() == "preview":
            # Preview is intentionally pure. Returning no state prevents the browser
            # from repainting persisted content while the user is still deciding.
            return {
                **validation,
                "source_content": str(payload.get("source_content") or ""),
            }

        result = resolve_reference_transition(
            self.repository,
            user_id,
            payload,
            validation=validation,
        )
        return {**result, "state": self.state(user_id)}

    def generate(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        document_id = str(payload.get("document_id") or payload.get("resource_id") or "").strip()
        if not document_id:
            raise ValueError("document_id is required")
        context = self.generation_contexts.context_mapping(user_id, require_job=True)
        user_state = self.user_data.read(user_id=user_id)
        analysis_settings = user_state.get("analysis_settings") or {}
        if not isinstance(analysis_settings, Mapping):
            analysis_settings = {}
        working_buffers = payload.get("working_buffers")
        if not isinstance(working_buffers, Mapping):
            working_buffers = {}
        return DocumentWorkbenchRenderer(
            self.repository,
            working_buffers=working_buffers,
        ).generate(
            user_id,
            document_id,
            context,
            output_directory=str(payload.get("output_directory") or "").strip() or None,
            analysis_settings=analysis_settings,
            write_output=not bool(payload.get("preview")),
        )

    def routing(self, user_id: int) -> dict[str, Any]:
        return routing_state(self.repository, user_id)

    def save_routing(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        context = payload.get("generation_context")
        if isinstance(context, Mapping):
            self.generation_contexts.set_selection(user_id, context)
        if "rules" in payload or "default_document_id" in payload:
            return save_routing(self.repository, user_id, payload)
        return routing_state(self.repository, user_id)

    def generate_job(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        job_id = int(payload.get("job_id") or 0)
        if job_id <= 0:
            raise ValueError("job_id is required")
        job = self.database.get_job(job_id, user_id)
        if job is None:
            raise ValueError("Tracked job was not found")
        user_state = self.user_data.read(user_id=user_id)
        analysis_settings = user_state.get("analysis_settings") or {}
        if not isinstance(analysis_settings, Mapping):
            analysis_settings = {}
        return generate_job(
            self.repository,
            user_id,
            job=job,
            user_state=user_state,
            job_id=job_id,
            document_id=str(payload.get("document_id") or "").strip(),
            output_directory=str(payload.get("output_directory") or "").strip() or None,
            analysis_settings=analysis_settings,
        )

    @staticmethod
    def open_output(payload: Mapping[str, Any]) -> dict[str, Any]:
        raw = str(payload.get("path") or "").strip()
        if not raw:
            raise ValueError("Output path is required")
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Output does not exist: {path}")
        target = str(payload.get("target") or "file").strip().casefold()
        if target not in {"file", "location"}:
            raise ValueError("Open target must be file or location")

        if target == "location":
            if sys.platform == "win32":
                if path.is_file():
                    subprocess.Popen(["explorer.exe", "/select,", str(path)])  # noqa: S603,S607
                else:
                    os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])  # noqa: S603,S607
            else:
                subprocess.Popen(["xdg-open", str(path.parent if path.is_file() else path)])  # noqa: S603,S607
        else:
            if path.is_dir() or path.suffix.casefold() != ".pdf":
                raise ValueError("Only generated PDF files can be opened")
            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])  # noqa: S603,S607
            else:
                subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
        return {"opened": str(path), "target": target}


__all__ = ["DocumentWorkbenchApplication"]