"""Structured content shapes shared by Document Studio and the render engine."""

from __future__ import annotations

import re

CONTENT_SHAPES = ("paragraphs", "list", "inline", "block")
DEFAULT_CONTENT_SHAPE = "paragraphs"

_LIST_MARKER = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)")


def normalize_content_shape(value: object) -> str:
    """Return a supported normalized content shape or raise a useful error."""
    shape = str(value or DEFAULT_CONTENT_SHAPE).strip().casefold()
    if shape not in CONTENT_SHAPES:
        choices = ", ".join(CONTENT_SHAPES)
        raise ValueError(f"Content shape must be one of: {choices}")
    return shape


def split_content(rendered: str, shape: str) -> list[str]:
    """Normalize rendered Section text into shape-aware items.

    Paragraphs are separated by blank lines. List and inline content use one
    non-empty line per item. Block content remains one value.
    """
    normalized = normalize_content_shape(shape)
    if normalized == "paragraphs":
        return [
            piece.strip()
            for piece in re.split(r"\n\s*\n", rendered)
            if piece.strip()
        ]
    if normalized in {"list", "inline"}:
        items: list[str] = []
        for line in rendered.splitlines():
            item = line.strip()
            if not item:
                continue
            if normalized == "list":
                item = _LIST_MARKER.sub("", item).strip()
            if item:
                items.append(item)
        return items
    return [rendered.strip()] if rendered.strip() else []


__all__ = [
    "CONTENT_SHAPES",
    "DEFAULT_CONTENT_SHAPE",
    "normalize_content_shape",
    "split_content",
]
