"""Provider-neutral contracts for JAW document rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class DocumentRenderRequest:
    """Fully resolved input for one document-rendering operation.

    ``template_source`` is deliberately separate from its context so callers can
    persist an exact source snapshot with every generated document. Set
    ``only_cached`` when generation must not download missing TeX resources.
    Workbench callers set ``autoescape_text`` so inserted values are escaped at
    the final renderer boundary while Template-authored LaTeX remains trusted.
    """

    template_source: str
    context: Mapping[str, Any]
    output_name: str = "document"
    only_cached: bool = False
    autoescape_text: bool = False


@dataclass(frozen=True)
class RenderDiagnostic:
    """One renderer message suitable for logging or presenting to a user."""

    level: str
    message: str
    source: str = "renderer"


@dataclass(frozen=True)
class DocumentRenderResult:
    """Successful rendered output and the exact source used to produce it."""

    pdf_bytes: bytes
    rendered_source: str
    diagnostics: tuple[RenderDiagnostic, ...]
    renderer: str
    command: tuple[str, ...]
    duration_ms: int


class DocumentRenderError(RuntimeError):
    """A template or renderer failure with troubleshooting context attached."""

    def __init__(
        self,
        message: str,
        *,
        rendered_source: str = "",
        diagnostics: tuple[RenderDiagnostic, ...] = (),
    ) -> None:
        super().__init__(message)
        self.rendered_source = rendered_source
        self.diagnostics = diagnostics


class DocumentRenderer(Protocol):
    """Boundary implemented by concrete document-renderer adapters."""

    name: str

    @property
    def available(self) -> bool:
        ...

    def render(self, request: DocumentRenderRequest) -> DocumentRenderResult:
        ...
