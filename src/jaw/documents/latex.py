"""Safe Jinja-to-LaTeX rendering helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

from .contracts import DocumentRenderError, RenderDiagnostic

_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "%": r"\%",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


class _LatexEscaped(str):
    """Marker for text that has already crossed the LaTeX escaping boundary."""


class _RawLatex(str):
    """Marker returned by the explicit ``latex_raw(...)`` escape hatch."""


def escape_latex(value: Any) -> str:
    """Escape text for inclusion in ordinary LaTeX text mode.

    Unicode text is retained for XeTeX/Tectonic. Line endings are normalized,
    while TeX metacharacters and command introducers are made inert.
    """

    if value is None:
        return ""
    if isinstance(value, _LatexEscaped):
        return value
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return _LatexEscaped(
        "".join(_LATEX_ESCAPES.get(character, character) for character in text)
    )


def latex_raw(value: Any) -> str:
    """Return trusted LaTeX without automatic text escaping.

    This is intentionally explicit. Normal JAW values should render without
    this helper so the renderer can escape them safely at the final template
    boundary.
    """

    if value is None:
        return _RawLatex("")
    return _RawLatex(str(value))


def _latex_finalize(value: Any) -> Any:
    """Escape ordinary rendered values exactly once at the LaTeX boundary."""

    if isinstance(value, (_RawLatex, _LatexEscaped)):
        return str(value)
    if value is None:
        return ""
    if isinstance(value, (bool, int, float)):
        return value
    return escape_latex(value)


def latex_environment(*, autoescape_text: bool = False) -> SandboxedEnvironment:
    """Create the constrained environment used for LaTeX render templates.

    ``autoescape_text`` is enabled by the Workbench final Template render. It
    escapes the result of every normal Jinja output expression while leaving the
    LaTeX source authored in the Template untouched.
    """

    environment = SandboxedEnvironment(
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        finalize=_latex_finalize if autoescape_text else None,
    )
    # ``latex`` remains a low-level explicit helper for older/non-Workbench
    # render paths. Workbench Templates should rely on automatic escaping.
    environment.filters["latex"] = escape_latex
    environment.globals["latex_raw"] = latex_raw
    return environment


def _template_error_detail(error: Exception) -> str:
    """Return a concise user-facing description for template execution failures."""

    message = str(error).strip() or error.__class__.__name__
    if isinstance(error, TemplateError):
        return message
    return f"{error.__class__.__name__}: {message}"


def render_latex_template(
    template_source: str,
    context: Mapping[str, Any],
    *,
    autoescape_text: bool = False,
) -> str:
    """Render a LaTeX template or raise a document-specific error.

    Jinja may surface ordinary Python exceptions while executing valid template
    syntax (for example, iterating over ``None``). Keep those failures inside the
    document-rendering boundary so HTTP callers receive a normal JSON error
    instead of a dropped connection.
    """

    try:
        template = latex_environment(autoescape_text=autoescape_text).from_string(
            template_source
        )
        return template.render(dict(context))
    except Exception as error:
        detail = _template_error_detail(error)
        diagnostic = RenderDiagnostic("error", detail, "jinja2")
        raise DocumentRenderError(
            f"Could not render document template: {detail}",
            diagnostics=(diagnostic,),
        ) from error
