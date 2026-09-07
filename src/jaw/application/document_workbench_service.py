"""Application service for the IDE-style Document Workbench.

Canonical resource content is saved explicitly. Dirty buffers are checkpointed
separately so unsaved work survives process restarts. Normal source reconciliation
is intentionally additive: unresolved reference occurrences may create resources,
but existing resource identity/removal changes are committed only through explicit
Workbench reference transitions.

Every new Document owns a normal private Template from creation. The built-in
Template source is only a default source string; it is never represented as a
shared or immutable Workbench resource. Sections may contain the full generation
language, and staged resources remain durable until the user explicitly reuses or
deletes them.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from difflib import SequenceMatcher
from typing import Any

from ..documents.context import ExampleContextProvider
from ..documents.workbench_symbols import (
    JAW_SYMBOLS,
    ReferenceOccurrence,
    WorkbenchSyntaxError,
    bind_reference_occurrences,
    is_identifier,
    referenced_occurrences,
)
from ..persistence.document_workbench import DocumentWorkbenchRepository

_DEFAULT_TEMPLATE_SOURCE = r"""\documentclass[10pt,letterpaper]{article}
\usepackage[letterpaper,margin=0.75in]{geometry}
\pagestyle{empty}
\begin{document}
{{ section }}
\end{document}
"""
_DEFAULT_TEMPLATE_SETTINGS = {"renderer": "tectonic", "format": "latex_jinja"}
_GENERATION_TAG = re.compile(r"<[A-Za-z_][A-Za-z0-9_]*(?::(?:text|list))?>|</>")


class DocumentWorkbenchService:
    """Coordinate Workbench resources, reference graph, and editor recovery state."""

    def __init__(self, repository: DocumentWorkbenchRepository, user_data: Any) -> None:
        self.repository = repository
        self.user_data = user_data

    # State ---------------------------------------------------------

    def state(self, user_id: int) -> dict[str, Any]:
        resources = self.repository.list_resources(user_id)
        buffers = {item["resource_id"]: item for item in self.repository.list_buffers(user_id)}
        edges = self.repository.list_edges(user_id)
        by_id = {item["id"]: self._with_buffer(item, buffers) for item in resources}
        edges_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
        inbound: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            edges_by_parent[edge["parent_id"]].append(edge)
            inbound[edge["child_id"]].append(edge)

        documents: list[dict[str, Any]] = []
        for document in self.repository.list_documents(user_id):
            doc = self._with_buffer(document, buffers)
            template = by_id.get(document["template_id"])
            section_values: list[dict[str, Any]] = []
            for edge in edges_by_parent.get(document["id"], []):
                section = by_id.get(edge["child_id"])
                if not section:
                    continue
                section_value = {
                    **section,
                    "reference_id": edge.get("id"),
                    "reference_symbol": edge["symbol"],
                }
                function_values: list[dict[str, Any]] = []
                for function_edge in edges_by_parent.get(section["id"], []):
                    function = by_id.get(function_edge["child_id"])
                    if function:
                        function_values.append(
                            {
                                **function,
                                "reference_id": function_edge.get("id"),
                                "reference_symbol": function_edge["symbol"],
                            }
                        )
                section_value["functions"] = function_values
                section_values.append(section_value)
            doc["template"] = template
            doc["sections"] = section_values
            documents.append(doc)

        globals_sections = [
            item
            for item in by_id.values()
            if item["kind"] == "section"
            and item["visibility"] == "global"
            and item["state"] == "active"
        ]
        globals_functions = [
            item
            for item in by_id.values()
            if item["kind"] == "function"
            and item["visibility"] == "global"
            and item["state"] == "active"
        ]
        orphans = [
            item
            for item in by_id.values()
            if item["kind"] in {"section", "function"} and item["state"] == "orphaned"
        ]
        templates = [item for item in by_id.values() if item["kind"] == "template"]

        relationships: dict[str, dict[str, Any]] = {}
        for resource_id in by_id:
            relationships[resource_id] = {
                "inbound": [dict(edge) for edge in inbound.get(resource_id, [])],
                "outbound": [dict(edge) for edge in edges_by_parent.get(resource_id, [])],
            }

        generation_context = self._generation_context(user_id)
        return {
            "documents": documents,
            "templates": templates,
            "global_sections": globals_sections,
            "global_functions": globals_functions,
            "orphans": orphans,
            "resources": list(by_id.values()),
            "relationships": relationships,
            "jaw_objects": self._jaw_objects(generation_context),
            "generation_context": generation_context,
        }

    # Creation / Template lifecycle --------------------------------

    def create_document(
        self,
        user_id: int,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        value = dict(payload or {})
        name = str(value.get("name") or "Document").strip() or "Document"
        template_source = str(value.get("template_source") or _DEFAULT_TEMPLATE_SOURCE)
        template = self.repository.create_resource(
            user_id,
            "template",
            name=name,
            symbol="template",
            visibility="private",
            content=template_source,
            settings=_DEFAULT_TEMPLATE_SETTINGS,
        )
        output_pattern = str(
            value.get("output_pattern") or f"{{{{ user.full_name }}}} - {name}.pdf"
        )
        document = self.repository.create_document(
            user_id,
            name,
            template["id"],
            output_pattern=output_pattern,
        )
        self.repository.update_resource(user_id, template["id"], owner_id=document["id"])
        self._reconcile_template(user_id, document["id"], template_source)
        return self._document_state(user_id, document["id"])

    # Editor buffers ------------------------------------------------

    def _unchanged_checkpoint(
        self,
        user_id: int,
        resource: Mapping[str, Any],
        content: str,
    ) -> dict[str, Any] | None:
        """Clear recovery state when working source exactly matches Saved source."""

        if content != str(resource.get("content") or ""):
            return None
        self.repository.clear_buffer(user_id, str(resource["id"]))
        return {
            "buffer": {},
            "changes": {"created": [], "orphaned": [], "deleted": []},
            "state": self.state(user_id),
        }

    @staticmethod
    def _reference_hints(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        value = payload.get("reference_bindings") or []
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [item for item in value if isinstance(item, Mapping)]

    def checkpoint(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        resource_id = self._required(payload, "resource_id")
        content = str(payload.get("content") or "")
        resource = self.repository.require_resource(user_id, resource_id)
        unchanged = self._unchanged_checkpoint(user_id, resource, content)
        if unchanged is not None:
            return unchanged

        previous_source = self._effective(user_id, resource)
        self._validate_language(resource, content)
        buffer = self.repository.checkpoint_buffer(
            user_id,
            resource_id,
            content,
            cursor_start=int(payload.get("cursor_start") or 0),
            cursor_end=int(payload.get("cursor_end") or 0),
        )
        changes = self._reconcile(
            user_id,
            resource,
            content,
            document_id=str(payload.get("document_id") or "") or None,
            previous_source=previous_source,
            reference_bindings=self._reference_hints(payload),
        )
        return {
            "buffer": buffer,
            "changes": changes,
            "state": self.state(user_id),
        }

    def save(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        resource_id = self._required(payload, "resource_id")
        resource = self.repository.require_resource(user_id, resource_id)
        original_buffer = self.repository.get_buffer(user_id, resource_id)
        content = (
            str(payload.get("content"))
            if "content" in payload
            else str(original_buffer["content"])
            if original_buffer
            else str(resource.get("content") or "")
        )
        if content == str(resource.get("content") or ""):
            self.repository.clear_buffer(user_id, resource_id)
            return {
                "resource": self.repository.require_resource(user_id, resource_id),
                "changes": {"created": [], "orphaned": [], "deleted": []},
                "state": self.state(user_id),
            }

        previous_source = self._effective(user_id, resource)
        self._validate_language(resource, content)
        saved = self.repository.save_content(user_id, resource_id, content)
        changes = self._reconcile(
            user_id,
            saved,
            content,
            document_id=str(payload.get("document_id") or "") or None,
            previous_source=previous_source,
            reference_bindings=self._reference_hints(payload),
        )
        return {
            "resource": saved,
            "changes": changes,
            "state": self.state(user_id),
        }

    # Structural changes -------------------------------------------

    def update_resource(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        resource_id = self._required(payload, "resource_id")
        current = self.repository.require_resource(user_id, resource_id)
        current_document = (
            self.repository.get_document(user_id, resource_id)
            if current["kind"] == "document"
            else None
        )
        kwargs: dict[str, Any] = {}
        if "name" in payload:
            if current["kind"] in {"section", "function"}:
                raise ValueError("Sections and Functions are named by their symbol")
            kwargs["name"] = str(payload.get("name") or "")
        if "visibility" in payload:
            next_visibility = str(payload.get("visibility") or "").casefold()
            if next_visibility == "global":
                kwargs.update({"visibility": "global", "state": "active", "owner_id": None})
            elif next_visibility == "private":
                owner_id = self._private_owner(user_id, current, payload)
                kwargs.update({"visibility": "private", "owner_id": owner_id})
            else:
                raise ValueError("Visibility must be private or global")
        if "content_shape" in payload:
            if current["kind"] != "section":
                raise ValueError("Only Sections have a Content Shape")
            shape = str(payload.get("content_shape") or "").strip().casefold()
            if shape not in {"paragraphs", "list"}:
                raise ValueError("Content Shape must be Paragraphs or List")
            settings = dict(current.get("settings") or {})
            settings["content_shape"] = shape
            kwargs["settings"] = settings
        saved = self.repository.update_resource(user_id, resource_id, **kwargs)
        if "output_pattern" in payload or "template_id" in payload:
            if current["kind"] != "document":
                raise ValueError("Only Documents have output/template attributes")
            requested_template_id = str(payload.get("template_id") or "")
            template_changed = bool(
                "template_id" in payload
                and requested_template_id
                and current_document
                and requested_template_id != str(current_document.get("template_id") or "")
            )
            document = self.repository.update_document(
                user_id,
                resource_id,
                template_id=requested_template_id or None,
                output_pattern=(
                    str(payload.get("output_pattern") or "")
                    if "output_pattern" in payload
                    else None
                ),
            )
            if "template_id" in payload:
                template = self.repository.require_resource(user_id, document["template_id"])
                source = self._effective(user_id, template)
                self._reconcile_template(
                    user_id,
                    document["id"],
                    source,
                )
                if template_changed:
                    self._stage_unbound_document_sections(
                        user_id,
                        document["id"],
                        source,
                    )
        return {"resource": saved, "state": self.state(user_id)}

    def _stage_unbound_document_sections(
        self,
        user_id: int,
        document_id: str,
        source: str,
    ) -> list[str]:
        """Remove stale Section refs after an explicit Document Template switch.

        Normal source editing is additive and never infers removal. Choosing a
        different Template is itself an explicit structural operation, so Section
        references that are absent from the new Template no longer belong to the
        Document. Private resources are staged for reuse; Global resources are only
        unlinked.
        """

        edges = self.repository.list_edges(user_id, document_id)
        try:
            bindings = bind_reference_occurrences(source, edges)
        except WorkbenchSyntaxError:
            return []
        bound_reference_ids = {
            str(edge["id"])
            for _, edge in bindings
            if edge is not None and edge.get("id")
        }
        staged: list[str] = []
        for edge in list(edges):
            reference_id = str(edge.get("id") or "")
            if reference_id in bound_reference_ids:
                continue
            child_id = str(edge["child_id"])
            child = self.repository.require_resource(user_id, child_id)
            self.repository.unlink_reference(user_id, reference_id)
            if child["visibility"] == "global":
                continue
            if any(
                item["child_id"] == child_id
                for item in self.repository.list_edges(user_id)
            ):
                continue
            self.repository.update_resource(user_id, child_id, state="orphaned")
            staged.append(child_id)
        return staged

    def link_existing(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        parent_id = self._required(payload, "parent_id")
        child_id = self._required(payload, "child_id")
        child = self.repository.require_resource(user_id, child_id)
        parent = self.repository.require_resource(user_id, parent_id)
        edge_kind = "section" if child["kind"] == "section" else "function"
        if child["kind"] not in {"section", "function"}:
            raise ValueError("Only Sections and Functions can be inserted")
        if edge_kind == "section" and parent["kind"] != "document":
            raise ValueError("A Section must be dropped into a Template for a Document")
        if edge_kind == "function" and parent["kind"] != "section":
            raise ValueError("A Function must be dropped into a Section")
        symbol = str(payload.get("symbol") or child.get("symbol") or edge_kind).strip()
        if not is_identifier(symbol):
            raise ValueError("Symbol must be a valid Jinja identifier")
        if symbol in JAW_SYMBOLS:
            raise ValueError(f"'{symbol}' is reserved by JAW")
        if child["state"] == "orphaned":
            self.repository.update_resource(
                user_id,
                child_id,
                visibility="private",
                state="active",
                owner_id=parent_id,
            )
        reference = self.repository.link(
            user_id,
            parent_id,
            child_id,
            edge_kind=edge_kind,
            symbol=symbol,
        )
        return {
            "reference_id": reference.get("id"),
            "resource_id": child_id,
            "symbol": symbol,
            "insertion": f"{{{{ {symbol} }}}}",
            "state": self.state(user_id),
        }

    # Reconciliation ------------------------------------------------

    def _translated_template_reference_hints(
        self,
        user_id: int,
        *,
        source_document_id: str,
        target_document_id: str,
        hints: Sequence[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        """Translate active-Document ref hints to another graph using old occurrence order."""

        if not hints:
            return []
        if source_document_id == target_document_id:
            return list(hints)

        source_edges = {
            str(edge.get("id") or ""): edge
            for edge in self.repository.list_edges(user_id, source_document_id)
            if edge.get("id")
        }
        target_edges = self.repository.list_edges(user_id, target_document_id)
        translated: list[Mapping[str, Any]] = []
        for hint in hints:
            reference_id = str(hint.get("reference_id") or "").strip()
            source_edge = source_edges.get(reference_id)
            if source_edge is None:
                continue
            candidates = [
                edge
                for edge in target_edges
                if str(edge.get("edge_kind") or "") == str(source_edge.get("edge_kind") or "")
                and int(edge.get("sort_order") or 0) == int(source_edge.get("sort_order") or 0)
            ]
            if len(candidates) != 1:
                continue
            translated.append({**dict(hint), "reference_id": str(candidates[0]["id"])})
        return translated

    def _reconcile(
        self,
        user_id: int,
        resource: Mapping[str, Any],
        content: str,
        *,
        document_id: str | None,
        previous_source: str | None = None,
        reference_bindings: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        if resource["kind"] == "template":
            documents = self.repository.documents_for_template(user_id, str(resource["id"]))
            hints_by_document: dict[str, list[Mapping[str, Any]]] = {}
            if document_id:
                active = next(
                    (item for item in documents if str(item["id"]) == document_id),
                    None,
                )
                if active is None:
                    raise ValueError("Document does not use this Template")
                documents = [active] + [
                    item for item in documents if str(item["id"]) != document_id
                ]
                # Capture all cross-Document correspondence before any graph is
                # mutated. Reconciliation changes sort_order to the new occurrence
                # order, so translating later would lose the old shared position.
                hints_by_document = {
                    str(item["id"]): self._translated_template_reference_hints(
                        user_id,
                        source_document_id=document_id,
                        target_document_id=str(item["id"]),
                        hints=reference_bindings,
                    )
                    for item in documents
                }

            changes: dict[str, list[str]] = {
                "created": [],
                "orphaned": [],
                "deleted": [],
            }
            for document in documents:
                target_document_id = str(document["id"])
                result = self._reconcile_template(
                    user_id,
                    target_document_id,
                    content,
                    previous_source=previous_source,
                    reference_bindings=hints_by_document.get(target_document_id, []),
                )
                for key in changes:
                    changes[key].extend(result[key])
            return changes
        if resource["kind"] == "section":
            return self._reconcile_parent(
                user_id,
                parent_id=str(resource["id"]),
                source=content,
                child_kind="function",
                edge_kind="function",
                owner_id=str(resource["id"]),
                previous_source=previous_source,
                reference_bindings=reference_bindings,
            )
        return {"created": [], "orphaned": [], "deleted": []}

    def _reconcile_template(
        self,
        user_id: int,
        document_id: str,
        source: str,
        *,
        previous_source: str | None = None,
        reference_bindings: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        document = self.repository.get_document(user_id, document_id)
        if document is None:
            raise ValueError("Document was not found")
        return self._reconcile_parent(
            user_id,
            parent_id=document_id,
            source=source,
            child_kind="section",
            edge_kind="section",
            owner_id=document_id,
            previous_source=previous_source,
            reference_bindings=reference_bindings,
        )

    @staticmethod
    def _mapped_occurrence(
        occurrence: ReferenceOccurrence,
        blocks: list[Any],
        new_by_span: Mapping[tuple[int, int, str], ReferenceOccurrence],
    ) -> ReferenceOccurrence | None:
        for block in blocks:
            block_end = block.a + block.size
            if occurrence.start < block.a or occurrence.end > block_end:
                continue
            start = block.b + (occurrence.start - block.a)
            end = start + (occurrence.end - occurrence.start)
            return new_by_span.get((start, end, occurrence.symbol))
        return None

    @staticmethod
    def _hinted_reference_bindings(
        occurrences: Sequence[ReferenceOccurrence],
        existing: Sequence[Mapping[str, Any]],
        hints: Sequence[Mapping[str, Any]],
    ) -> tuple[dict[int, dict[str, Any]], set[str]]:
        if not hints:
            return {}, set()
        existing_by_id = {
            str(edge.get("id") or ""): dict(edge)
            for edge in existing
            if edge.get("id")
        }
        occurrences_by_span = {
            (item.start, item.end, item.symbol): item for item in occurrences
        }
        matched: dict[int, dict[str, Any]] = {}
        used: set[str] = set()
        for hint in hints:
            reference_id = str(hint.get("reference_id") or "").strip()
            edge = existing_by_id.get(reference_id)
            if edge is None or reference_id in used:
                continue
            try:
                start = int(hint.get("start"))
                end = int(hint.get("end"))
            except (TypeError, ValueError):
                continue
            symbol = str(hint.get("symbol") or edge.get("symbol") or "")
            if symbol != str(edge.get("symbol") or ""):
                continue
            occurrence = occurrences_by_span.get((start, end, symbol))
            if occurrence is None or occurrence.order in matched:
                continue
            matched[occurrence.order] = edge
            used.add(reference_id)
        return matched, used

    def _preserved_reference_bindings(
        self,
        source: str,
        existing: list[dict[str, Any]],
        *,
        previous_source: str | None,
        reference_bindings: Sequence[Mapping[str, Any]] = (),
    ) -> tuple[list[ReferenceOccurrence], dict[int, dict[str, Any]]]:
        occurrences = referenced_occurrences(source)
        if not existing:
            return occurrences, {}

        matched, used_reference_ids = self._hinted_reference_bindings(
            occurrences,
            existing,
            reference_bindings,
        )

        if previous_source is not None:
            try:
                old_bindings = bind_reference_occurrences(previous_source, existing)
                new_by_span = {
                    (item.start, item.end, item.symbol): item for item in occurrences
                }
                blocks = SequenceMatcher(
                    None,
                    str(previous_source),
                    str(source),
                    autojunk=False,
                ).get_matching_blocks()
                for old_occurrence, edge in old_bindings:
                    if edge is None or not edge.get("id"):
                        continue
                    reference_id = str(edge["id"])
                    if reference_id in used_reference_ids:
                        continue
                    mapped = self._mapped_occurrence(old_occurrence, blocks, new_by_span)
                    if mapped is None or mapped.order in matched:
                        continue
                    matched[mapped.order] = dict(edge)
                    used_reference_ids.add(reference_id)
            except WorkbenchSyntaxError:
                pass

        available = [
            edge
            for edge in existing
            if str(edge.get("id") or "") not in used_reference_ids
        ]
        for occurrence in occurrences:
            if occurrence.order in matched:
                continue
            candidates = [
                edge for edge in available if str(edge.get("symbol") or "") == occurrence.symbol
            ]
            if not candidates:
                continue
            edge = min(
                candidates,
                key=lambda item: (
                    abs(int(item.get("sort_order") or 0) - occurrence.order),
                    int(item.get("sort_order") or 0),
                    str(item.get("created_at") or ""),
                    str(item.get("id") or ""),
                ),
            )
            matched[occurrence.order] = edge
            available.remove(edge)
            if edge.get("id"):
                used_reference_ids.add(str(edge["id"]))

        return occurrences, matched

    def _reconcile_parent(
        self,
        user_id: int,
        *,
        parent_id: str,
        source: str,
        child_kind: str,
        edge_kind: str,
        owner_id: str,
        previous_source: str | None = None,
        reference_bindings: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        """Discover new reference occurrences without inferring removals."""

        existing = self.repository.list_edges(user_id, parent_id)
        try:
            occurrences, matched = self._preserved_reference_bindings(
                source,
                existing,
                previous_source=previous_source,
                reference_bindings=reference_bindings,
            )
        except WorkbenchSyntaxError:
            return {"created": [], "orphaned": [], "deleted": []}

        changes: dict[str, list[str]] = {"created": [], "orphaned": [], "deleted": []}
        for occurrence in occurrences:
            edge = matched.get(occurrence.order)
            if edge is not None:
                self.repository.link(
                    user_id,
                    parent_id,
                    edge["child_id"],
                    edge_kind=edge_kind,
                    symbol=occurrence.symbol,
                    sort_order=occurrence.order,
                    reference_id=str(edge["id"]),
                )
                continue

            settings = {"content_shape": "paragraphs"} if child_kind == "section" else {}
            child = self.repository.create_resource(
                user_id,
                child_kind,
                symbol=occurrence.symbol,
                visibility="private",
                state="active",
                owner_id=owner_id,
                content="",
                settings=settings,
            )
            self.repository.link(
                user_id,
                parent_id,
                child["id"],
                edge_kind=edge_kind,
                symbol=occurrence.symbol,
                sort_order=occurrence.order,
            )
            changes["created"].append(child["id"])

        # Missing existing references are intentionally untouched. The interactive
        # transition workflow must explicitly Update/Create/Stage/Delete them.
        return changes

    @staticmethod
    def _validate_language(resource: Mapping[str, Any], content: str) -> None:
        if resource["kind"] == "template" and _GENERATION_TAG.search(content):
            raise ValueError("Generation blocks belong in Sections or Functions, not Templates")

    # Helpers -------------------------------------------------------

    def _document_state(self, user_id: int, document_id: str) -> dict[str, Any]:
        state = self.state(user_id)
        document = next(
            (item for item in state["documents"] if item["id"] == document_id),
            None,
        )
        if document is None:
            raise ValueError("Document was not found")
        return document

    def _effective(self, user_id: int, resource: Mapping[str, Any]) -> str:
        buffer = self.repository.get_buffer(user_id, str(resource["id"]))
        return str(buffer["content"]) if buffer else str(resource.get("content") or "")

    @staticmethod
    def _with_buffer(
        resource: Mapping[str, Any],
        buffers: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        value = dict(resource)
        buffer = buffers.get(str(resource["id"]))
        value["dirty"] = bool(buffer)
        value["editor_content"] = (
            str(buffer["content"]) if buffer else str(resource.get("content") or "")
        )
        if buffer:
            value["cursor_start"] = int(buffer.get("cursor_start") or 0)
            value["cursor_end"] = int(buffer.get("cursor_end") or 0)
        return value

    def _private_owner(
        self,
        user_id: int,
        resource: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> str:
        inbound = [
            edge
            for edge in self.repository.list_edges(user_id)
            if edge["child_id"] == resource["id"]
        ]
        if len(inbound) > 1:
            raise ValueError(
                "This resource is used in multiple places. Detach it before making it private."
            )
        explicit = str(payload.get("owner_id") or "").strip()
        if inbound:
            owner = str(inbound[0]["parent_id"])
            if explicit and explicit != owner:
                raise ValueError("Private owner must match the resource's current relationship")
            return owner
        if explicit:
            self.repository.require_resource(user_id, explicit)
            return explicit
        raise ValueError("Choose an owner before making this resource private")

    def _generation_context(self, user_id: int) -> dict[str, Any]:
        state = self.user_data.read(user_id=user_id)
        user = dict(state.get("user", {}))
        first = str(user.get("first_name") or "").strip()
        last = str(user.get("last_name") or "").strip()
        user["full_name"] = str(user.get("full_name") or "").strip() or " ".join(
            part for part in (first, last) if part
        )
        example = ExampleContextProvider(1).load()
        work_history = [
            dict(item)
            for item in state.get("work_history", [])
            if isinstance(item, Mapping) and item.get("enabled", True)
        ]
        today = date.today()
        system = {
            "current_date": today.strftime("%B %d, %Y").replace(" 0", " "),
            "current_year": str(today.year),
        }
        return {
            "user": user,
            "job": dict(example.job),
            "capabilities": dict(example.capabilities),
            "work_history": work_history,
            "system": system,
        }

    @staticmethod
    def _jaw_objects(context: Mapping[str, Any]) -> dict[str, Any]:
        system = dict(context.get("system") or {})
        return {
            "user": dict(context.get("user") or {}),
            "job": dict(context.get("job") or {}),
            "capabilities": dict(context.get("capabilities") or {}),
            "system": system,
            "methods": [
                {
                    "name": "work_experience()",
                    "insert": "work_experience()",
                    "description": "Structured enabled work experience for the active user.",
                },
                {
                    "name": "csv(...)",
                    "insert": "csv()",
                    "description": "Render a sequence as comma-separated text.",
                },
                {
                    "name": "latex_raw(...)",
                    "insert": "latex_raw()",
                    "description": "Insert explicitly trusted LaTeX without automatic escaping.",
                },
            ],
        }

    @staticmethod
    def _required(payload: Mapping[str, Any], key: str) -> str:
        value = str(payload.get(key) or "").strip()
        if not value:
            raise ValueError(f"{key} is required")
        return value


__all__ = ["DocumentWorkbenchService"]