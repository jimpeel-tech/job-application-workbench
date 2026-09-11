"""Render current Document Workbench buffers into a PDF preview.

Visible Workbench symbols are presentation only. Before Jinja evaluates a Template
or Section, every bound reference occurrence is rewritten to an internal variable
derived from its durable ``ref_*`` JID. Duplicate visible symbols therefore remain
independent while resources continue to use their stable resource JIDs.
"""

from __future__ import annotations

import base64
import re
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

from ..config import DEFAULT_OPENAI_MODEL
from ..documents.contracts import DocumentRenderError, DocumentRenderRequest
from ..documents.expression_context import project_work_exp_entry
from ..documents.function_runtime import FunctionRuntime, FunctionRuntimeError
from ..documents.latex import escape_latex, latex_raw
from ..documents.runtime_debug import build_runtime_debug_helpers
from ..documents.tectonic import TectonicRenderer
from ..documents.text_generation import (
    DEFAULT_OLLAMA_MODEL,
    ProviderTextGenerator,
    TextGenerator,
)
from ..documents.workbench_symbols import (
    bind_reference_occurrences,
    reference_jinja_symbol,
    rewrite_bound_references,
)
from ..persistence.document_workbench import DocumentWorkbenchRepository

_SAFE_FILENAME = re.compile(r"[<>:\"/\\|?*\x00-\x1f]+")
_TEX_ERROR_HINT = re.compile(
    r"(?:^|\b)(?:error:|undefined control sequence|missing [}$]|extra alignment|"
    r"runaway argument|emergency stop|fatal error|can't use|cannot use|"
    r"not found|halted on potentially-recoverable error)",
    re.IGNORECASE,
)


class WorkbenchRenderError(ValueError):
    """A Workbench render error safe to show in the browser error tab."""


@dataclass(frozen=True)
class SectionValue:
    """Rendered Section kept raw until the final renderer text boundary."""

    content: str
    shape: str
    values: tuple[str, ...]

    def __str__(self) -> str:
        return self.content

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def __bool__(self) -> bool:
        return bool(self.content.strip())


class _FunctionValue:
    """Lazy memoized Function value exposed to Jinja as value and callable."""

    def __init__(self, invoke: Callable[[], str]) -> None:
        self._invoke = invoke

    def __call__(self) -> str:
        return self._invoke()

    def __str__(self) -> str:
        return self._invoke()

    def __bool__(self) -> bool:
        return bool(self._invoke())


class DocumentWorkbenchRenderer:
    """Compose Template → Sections → optional Functions from the live graph."""

    def __init__(
        self,
        repository: DocumentWorkbenchRepository,
        *,
        renderer: TectonicRenderer | None = None,
        text_generator: TextGenerator | None = None,
        working_buffers: Mapping[str, Any] | None = None,
    ) -> None:
        self.repository = repository
        self.renderer = renderer or TectonicRenderer()
        self.text_generator = text_generator or ProviderTextGenerator()
        self.working_buffers = {
            str(resource_id): str(content)
            for resource_id, content in (working_buffers or {}).items()
            if str(resource_id)
        }

    def generate(
        self,
        user_id: int,
        document_id: str,
        context: Mapping[str, Any],
        *,
        output_directory: str | Path | None = None,
        analysis_settings: Mapping[str, Any] | None = None,
        write_output: bool = True,
    ) -> dict[str, Any]:
        document = self.repository.get_document(user_id, document_id)
        if document is None:
            raise WorkbenchRenderError("Document was not found")
        template = self.repository.require_resource(user_id, document["template_id"])
        template_source = self._effective(user_id, template)
        if not template_source.strip():
            raise WorkbenchRenderError("Template is empty")

        provider, model = self._generation_provider_settings(analysis_settings or {})
        generation_log: list[dict[str, Any]] = []
        runtime = self._runtime_context(context)
        section_edges = self.repository.list_edges(user_id, document_id)
        template_bindings = bind_reference_occurrences(template_source, section_edges)
        for _occurrence, edge in template_bindings:
            if edge is None:
                continue
            section = self.repository.require_resource(user_id, str(edge["child_id"]))
            if section["state"] != "active":
                continue
            runtime[reference_jinja_symbol(str(edge["id"]))] = self._section_value(
                user_id,
                section,
                runtime,
                provider=provider,
                model=model,
                generation_log=generation_log,
            )
        rendered_template_source = rewrite_bound_references(
            template_source,
            template_bindings,
        )

        output_name = self._render_text(
            str(document.get("output_pattern") or document.get("name") or "Document.pdf"),
            runtime,
            label="output filename",
        ).strip()
        if output_name.casefold().endswith(".pdf"):
            output_name = output_name[:-4]
        output_name = output_name or str(document.get("name") or "Document")

        try:
            result = self.renderer.render(
                DocumentRenderRequest(
                    template_source=rendered_template_source,
                    context=runtime,
                    output_name=output_name,
                    only_cached=False,
                    autoescape_text=True,
                )
            )
        except DocumentRenderError as error:
            detail = self._diagnostic_summary(error)
            raise WorkbenchRenderError(
                f"Document rendering failed{f': {detail}' if detail else ''}"
            ) from error

        filename = self._safe_filename(output_name)
        output_path = ""
        output_directory_value = ""
        output_written = False
        warning = ""
        if write_output:
            output_dir = self._output_directory(output_directory)
            target_path = output_dir / filename
            output_path = str(target_path.resolve())
            output_directory_value = str(output_dir.resolve())
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                warning = (
                    "Preview updated, but the output directory could not be prepared: "
                    f"{error}"
                )
            else:
                try:
                    target_path.write_bytes(result.pdf_bytes)
                    output_written = True
                except OSError:
                    warning = (
                        f"Preview updated, but {filename} could not be replaced. "
                        "Close the file if another application has it open."
                    )
        return {
            "filename": filename,
            "pdf_base64": base64.b64encode(result.pdf_bytes).decode("ascii"),
            "output_path": output_path,
            "output_directory": output_directory_value,
            "output_written": output_written,
            "warning": warning,
            "renderer": result.renderer,
            "duration_ms": result.duration_ms,
            "generations": generation_log,
        }

    def _section_value(
        self,
        user_id: int,
        section: Mapping[str, Any],
        runtime: Mapping[str, Any],
        *,
        provider: str,
        model: str,
        generation_log: list[dict[str, Any]],
    ) -> SectionValue:
        section_context = dict(runtime)
        content_runtime = FunctionRuntime(
            self.text_generator,
            provider=provider,
            model=model,
        )
        cache: dict[str, str] = {}
        evaluating: set[str] = set()
        functions: dict[str, tuple[dict[str, Any], dict[str, Any], str]] = {}
        by_symbol: dict[str, list[str]] = defaultdict(list)

        section_source = self._effective(user_id, section)
        function_edges = self.repository.list_edges(user_id, str(section["id"]))
        section_bindings = bind_reference_occurrences(section_source, function_edges)
        for edge in function_edges:
            function = self.repository.require_resource(user_id, str(edge["child_id"]))
            if function["state"] != "active":
                continue
            reference_id = str(edge["id"])
            label = str(function.get("name") or edge["symbol"] or "Function")
            functions[reference_id] = (dict(edge), function, label)
            by_symbol[str(edge["symbol"])].append(reference_id)

        def make_invoke(reference_id: str) -> Callable[[], str]:
            def invoke() -> str:
                if reference_id in cache:
                    return cache[reference_id]
                if reference_id in evaluating:
                    edge, _function, _label = functions[reference_id]
                    raise WorkbenchRenderError(
                        f"Function cycle detected while evaluating '{edge['symbol']}'"
                    )
                _edge, function, label = functions[reference_id]
                evaluating.add(reference_id)
                try:
                    execution = content_runtime.render(
                        self._effective(user_id, function),
                        section_context,
                        label=f"Function {label}",
                    )
                except FunctionRuntimeError as error:
                    raise WorkbenchRenderError(f"Function '{label}' failed: {error}") from error
                finally:
                    evaluating.discard(reference_id)
                for generated in execution.generations:
                    generation_log.append(
                        {
                            "resource_kind": "function",
                            "resource_id": str(function["id"]),
                            "reference_id": reference_id,
                            "resource": label,
                            **generated,
                        }
                    )
                cache[reference_id] = execution.text
                return execution.text

            return invoke

        values: dict[str, _FunctionValue] = {}
        # Every Section occurrence receives a JID-keyed helper. Unique visible
        # symbols are also exposed as sibling aliases so existing Functions may
        # call another Function by name. Duplicate sibling symbols are purposely
        # not aliased because the visible name is ambiguous outside the Section's
        # occurrence-bound source.
        for reference_id in functions:
            value = _FunctionValue(make_invoke(reference_id))
            values[reference_id] = value
            section_context[reference_jinja_symbol(reference_id)] = value
        for symbol, reference_ids in by_symbol.items():
            if len(reference_ids) == 1:
                section_context[symbol] = values[reference_ids[0]]

        rewritten_section_source = rewrite_bound_references(section_source, section_bindings)
        section_label = str(section.get("name") or section.get("symbol") or section["id"])
        try:
            execution = content_runtime.render(
                rewritten_section_source,
                section_context,
                label=f"Section {section_label}",
            )
        except FunctionRuntimeError as error:
            raise WorkbenchRenderError(f"Section '{section_label}' failed: {error}") from error
        for generated in execution.generations:
            generation_log.append(
                {
                    "resource_kind": "section",
                    "resource_id": str(section["id"]),
                    "resource": section_label,
                    **generated,
                }
            )
        rendered = execution.text

        shape = str((section.get("settings") or {}).get("content_shape") or "paragraphs")
        if shape not in {"paragraphs", "list"}:
            shape = "paragraphs"
        section_values = tuple(
            self._list_values(rendered)
            if shape == "list"
            else self._paragraph_values(rendered)
        )
        return SectionValue(content=rendered, shape=shape, values=section_values)

    def _runtime_context(self, value: Mapping[str, Any]) -> dict[str, Any]:
        user = dict(value.get("user") or {})
        first = str(user.get("first_name") or "").strip()
        last = str(user.get("last_name") or "").strip()
        user["full_name"] = str(user.get("full_name") or "").strip() or " ".join(
            part for part in (first, last) if part
        )
        job_ref = dict(value.get("job_ref") or {})
        cap = dict(value.get("cap") or {})
        work_exp = [
            project_work_exp_entry(item)
            for item in value.get("work_exp", [])
            if isinstance(item, Mapping)
        ]
        today = date.today()
        system = dict(value.get("system") or {})
        system["current_date"] = today.strftime("%B %d, %Y").replace(" 0", " ")
        system["current_year"] = str(today.year)

        def csv(items: Any) -> str:
            return ", ".join(str(item) for item in items)

        dump, describe = build_runtime_debug_helpers(
            user=user,
            job_ref=job_ref,
            work_exp=work_exp,
            cap=cap,
            system=system,
            csv=csv,
            latex_raw=latex_raw,
        )
        return {
            "user": user,
            "job_ref": job_ref,
            "work_exp": work_exp,
            "cap": cap,
            "system": system,
            "csv": csv,
            "latex_raw": latex_raw,
            "dump": dump,
            "describe": describe,
        }

    @staticmethod
    def _generation_provider_settings(
        analysis_settings: Mapping[str, Any],
    ) -> tuple[str, str]:
        provider = str(analysis_settings.get("provider") or "openai").strip().casefold()
        model = str(analysis_settings.get("model") or "").strip()
        if model:
            return provider, model
        if provider == "ollama":
            return provider, DEFAULT_OLLAMA_MODEL
        if provider == "openai":
            return provider, DEFAULT_OPENAI_MODEL
        return provider, ""

    @staticmethod
    def _paragraph_values(value: str) -> list[str]:
        lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        paragraphs: list[str] = []
        current: list[str] = []
        for line in lines:
            if line.strip():
                current.append(line)
                continue
            paragraphs.append("\n".join(current).strip())
            current = []
        if current or not paragraphs:
            paragraphs.append("\n".join(current).strip())
        while len(paragraphs) > 1 and paragraphs[-1] == "" and value.endswith("\n"):
            paragraphs.pop()
        return paragraphs

    @staticmethod
    def _list_values(value: str) -> list[str]:
        items: list[str] = []
        for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("- "):
                items.append(stripped[2:].strip())
            else:
                items.append(stripped)
        return items

    @staticmethod
    def _render_text(source: str, context: Mapping[str, Any], *, label: str) -> str:
        environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
        environment.filters["latex"] = escape_latex
        environment.globals["latex_raw"] = latex_raw
        try:
            return environment.from_string(source).render(dict(context))
        except TemplateError as error:
            raise WorkbenchRenderError(f"Could not render {label}: {error}") from error

    def _effective(self, user_id: int, resource: Mapping[str, Any]) -> str:
        resource_id = str(resource["id"])
        if resource_id in self.working_buffers:
            return self.working_buffers[resource_id]
        buffer = self.repository.get_buffer(user_id, resource_id)
        return str(buffer["content"]) if buffer else str(resource.get("content") or "")

    @staticmethod
    def _safe_filename(value: str) -> str:
        stem = _SAFE_FILENAME.sub("-", value).strip(" .-") or "Document"
        return f"{stem}.pdf"

    @staticmethod
    def _output_directory(value: str | Path | None) -> Path:
        raw = str(value or "").strip()
        if not raw or raw.casefold() == "downloads":
            return Path.home() / "Downloads"
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise WorkbenchRenderError(
                "Output directory must be an absolute path, or use Downloads"
            )
        return path

    @staticmethod
    def _diagnostic_summary(error: DocumentRenderError) -> str:
        error_lines: list[str] = []
        fallback: list[str] = []
        diagnostics = sorted(
            error.diagnostics,
            key=lambda diagnostic: 0 if str(diagnostic.level).casefold() == "error" else 1,
        )
        for diagnostic in diagnostics:
            lines = [
                line.strip()
                for line in str(diagnostic.message or "").splitlines()
                if line.strip() and not set(line.strip()) <= {"=", "-"}
            ]
            fallback.extend(lines)
            for line in lines:
                if _TEX_ERROR_HINT.search(line):
                    if "halted on potentially-recoverable error" in line.casefold() and error_lines:
                        continue
                    error_lines.append(line)
        chosen = error_lines or fallback
        if not chosen:
            return str(error).strip()
        unique: list[str] = []
        seen: set[str] = set()
        for line in chosen:
            folded = line.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            unique.append(line)
            if len(unique) >= 5:
                break
        return " | ".join(unique)


__all__ = ["DocumentWorkbenchRenderer", "SectionValue", "WorkbenchRenderError"]