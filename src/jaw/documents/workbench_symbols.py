"""Symbol parsing and reference-binding rules for the Document Workbench.

The editor language is Jinja plus JAW-owned roots/methods. Undeclared Jinja
symbols become Workbench resources according to editor context: Template symbols
become Sections and Section symbols become Functions. A visible symbol is not a
resource identity: every occurrence can bind to its own durable reference JID.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, TemplateSyntaxError, meta

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NON_IDENTIFIER = re.compile(r"[^A-Za-z0-9_]+")
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")
_GENERATION_VARIABLE = re.compile(
    r"<([A-Za-z_][A-Za-z0-9_]*)(?::(?:text|list))?>"
)
_JINJA_BLOCK = re.compile(r"(?:\{\{|\{%)(.*?)(?:\}\}|%\})", re.S)
_IDENTIFIER_TOKEN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_RAW_BLOCK = re.compile(r"\{%\s*raw\s*%\}[\s\S]*?\{%\s*endraw\s*%\}")
_COMMENT_BLOCK = re.compile(r"\{#[\s\S]*?#\}")
_QUOTED = re.compile(r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''')

JAW_SYMBOLS = {
    "user",
    "job_ref",
    "work_exp",
    "cap",
    "system",
    "csv",
    "latex_raw",
    "dump",
    "describe",
}


@dataclass(frozen=True, slots=True)
class ReferenceOccurrence:
    """One visible Workbench reference token in source order."""

    symbol: str
    start: int
    end: int
    order: int


def _identity_filter(value: Any) -> Any:
    return value


def _symbol_environment() -> Environment:
    environment = Environment()
    environment.filters["latex"] = _identity_filter
    environment.globals["latex_raw"] = _identity_filter
    return environment


_JINJA_GLOBALS = set(_symbol_environment().globals)


class WorkbenchSyntaxError(ValueError):
    """Jinja source could not be parsed for Workbench symbol resolution."""


def generation_variables(source: str) -> list[str]:
    """Return variables declared by JAW generation blocks in source order."""

    result: list[str] = []
    seen: set[str] = set()
    for match in _GENERATION_VARIABLE.finditer(str(source or "")):
        value = match.group(1)
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _blank_preserving_lines(value: str) -> str:
    return "".join("\n" if character == "\n" else " " for character in value)


def _mask_ignored_regions(source: str) -> str:
    masked = _RAW_BLOCK.sub(lambda match: _blank_preserving_lines(match.group(0)), source)
    return _COMMENT_BLOCK.sub(lambda match: _blank_preserving_lines(match.group(0)), masked)


def _mask_quoted(value: str) -> str:
    return _QUOTED.sub(lambda match: " " * len(match.group(0)), value)


def referenced_occurrences(
    source: str,
    *,
    extra_known: Iterable[str] = (),
) -> list[ReferenceOccurrence]:
    """Return every undeclared Workbench reference occurrence in source order.

    Unlike :func:`referenced_symbols`, duplicates are intentionally preserved.
    Matching is case-sensitive because Jinja identifiers are case-sensitive.
    """

    source = str(source or "")
    environment = _symbol_environment()
    try:
        ast = environment.parse(source)
        unresolved = set(meta.find_undeclared_variables(ast))
    except TemplateSyntaxError as error:
        raise WorkbenchSyntaxError(
            f"Jinja syntax error on line {error.lineno}: {error.message}"
        ) from error

    unresolved.difference_update(JAW_SYMBOLS)
    unresolved.difference_update(_JINJA_GLOBALS)
    unresolved.difference_update(generation_variables(source))
    unresolved.difference_update(str(item) for item in extra_known)
    if not unresolved:
        return []

    searchable = _mask_ignored_regions(source)
    result: list[ReferenceOccurrence] = []
    for block in _JINJA_BLOCK.finditer(searchable):
        body = block.group(1)
        masked_body = _mask_quoted(body)
        body_start = block.start(1)
        for token in _IDENTIFIER_TOKEN.finditer(masked_body):
            symbol = token.group(0)
            if symbol not in unresolved:
                continue
            before = masked_body[: token.start()].rstrip()
            if before.endswith((".", "|")):
                continue
            start = body_start + token.start()
            result.append(
                ReferenceOccurrence(
                    symbol=source[start : start + len(symbol)],
                    start=start,
                    end=start + len(symbol),
                    order=len(result),
                )
            )
    return result


def referenced_symbols(source: str, *, extra_known: Iterable[str] = ()) -> list[str]:
    """Return unique Workbench symbols in deterministic first-use order."""

    result: list[str] = []
    seen: set[str] = set()
    for occurrence in referenced_occurrences(source, extra_known=extra_known):
        if occurrence.symbol in seen:
            continue
        seen.add(occurrence.symbol)
        result.append(occurrence.symbol)
    return result


def bind_reference_occurrences(
    source: str,
    edges: Sequence[Mapping[str, Any]],
    *,
    extra_known: Iterable[str] = (),
) -> list[tuple[ReferenceOccurrence, Mapping[str, Any] | None]]:
    """Bind source occurrences to durable references by exact symbol and order."""

    queues: dict[str, deque[Mapping[str, Any]]] = defaultdict(deque)
    ordered_edges = sorted(
        edges,
        key=lambda edge: (
            int(edge.get("sort_order") or 0),
            str(edge.get("created_at") or ""),
            str(edge.get("id") or ""),
        ),
    )
    for edge in ordered_edges:
        queues[str(edge.get("symbol") or "")].append(edge)

    return [
        (occurrence, queues[occurrence.symbol].popleft() if queues[occurrence.symbol] else None)
        for occurrence in referenced_occurrences(source, extra_known=extra_known)
    ]


def reference_jinja_symbol(reference_id: str) -> str:
    """Return an internal valid Jinja identifier for a durable reference JID."""

    clean = re.sub(r"[^A-Za-z0-9_]", "_", str(reference_id or ""))
    return f"__jaw_{clean}"


def rewrite_bound_references(
    source: str,
    bindings: Sequence[tuple[ReferenceOccurrence, Mapping[str, Any] | None]],
) -> str:
    """Rewrite only bound visible tokens to internal reference-JID variables."""

    rewritten = str(source or "")
    replacements = [
        (occurrence.start, occurrence.end, reference_jinja_symbol(str(edge["id"])))
        for occurrence, edge in bindings
        if edge is not None and edge.get("id")
    ]
    for start, end, value in reversed(replacements):
        rewritten = rewritten[:start] + value + rewritten[end:]
    return rewritten


def normalize_symbol(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = _CAMEL_BOUNDARY.sub("_", text)
    text = _NON_IDENTIFIER.sub("_", text).strip("_").casefold()
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"_{text}"
    return text


def unique_symbol(preferred: str, used: Iterable[str], *, fallback: str) -> str:
    base = normalize_symbol(preferred, fallback=fallback)
    used_values = {str(item) for item in used}
    if base not in used_values:
        return base
    index = 2
    while f"{base}_{index}" in used_values:
        index += 1
    return f"{base}_{index}"


def display_name(symbol: str) -> str:
    clean = str(symbol or "").strip("_")
    if not clean:
        return "Resource"
    return " ".join(piece.capitalize() for piece in clean.split("_") if piece)


def is_identifier(value: str) -> bool:
    return bool(_IDENTIFIER.fullmatch(str(value or "")))


__all__ = [
    "JAW_SYMBOLS",
    "ReferenceOccurrence",
    "WorkbenchSyntaxError",
    "bind_reference_occurrences",
    "display_name",
    "generation_variables",
    "is_identifier",
    "normalize_symbol",
    "reference_jinja_symbol",
    "referenced_occurrences",
    "referenced_symbols",
    "rewrite_bound_references",
    "unique_symbol",
]
