"""Stable, intentionally small context projections for Documents."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

REFERENCE_PATTERN = re.compile(r"\[([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*)\]")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

TEMPLATE_VARIABLES: tuple[dict[str, str], ...] = ()

_JOB_REF_FIELDS = (
    "company",
    "title",
    "raw_description",
    "questions",
    "strong_matches",
    "missing_qualifications",
    "concerns",
    "score",
    "summary",
)


class ExpressionContextError(ValueError):
    """An expression requested a context reference that does not exist."""


def slugify_reference(value: str) -> str:
    """Return a lower-snake identifier suitable for a document reference key."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value.casefold()).strip("_")
    if not slug:
        return "set"
    if slug[0].isdigit():
        return f"set_{slug}"
    return slug


def project_job_ref(job: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Project a tracker job into the small Documents-facing job reference."""
    if not isinstance(job, Mapping) or not job:
        return {}

    questions: list[dict[str, Any]] = []
    for raw in job.get("questions", []):
        if not isinstance(raw, Mapping):
            continue
        questions.append(
            {
                "question": str(raw.get("question") or ""),
                "suggested_answer": str(raw.get("suggested_answer") or ""),
                "submitted_answer": str(raw.get("submitted_answer") or ""),
            }
        )

    projected: dict[str, Any] = {
        "company": str(job.get("company") or ""),
        "title": str(job.get("title") or ""),
        "raw_description": str(job.get("raw_description") or ""),
        "questions": questions,
        "strong_matches": _string_list(job.get("strong_matches")),
        "missing_qualifications": _string_list(job.get("missing_qualifications")),
        "concerns": _string_list(job.get("concerns")),
        "score": job.get("score", job.get("match_score")),
        "summary": str(job.get("summary") or ""),
    }
    return {field: projected[field] for field in _JOB_REF_FIELDS}


def normalize_highlights(value: Any) -> list[str]:
    """Project pasted highlight text into clean runtime list items."""
    if value is None:
        return []

    if isinstance(value, str):
        raw_lines = value.splitlines()
    elif isinstance(value, (list, tuple)):
        raw_lines = [
            line
            for item in value
            for line in str(item).splitlines()
        ]
    else:
        raw_lines = str(value).splitlines()

    highlights: list[str] = []
    for raw_line in raw_lines:
        text = str(raw_line).strip()
        if not text:
            continue

        parts = text.split(maxsplit=1)
        marker = parts[0]
        if marker and all(
            unicodedata.category(char)[0] in {"P", "S"} for char in marker
        ):
            text = parts[1].lstrip() if len(parts) > 1 else ""

        if text:
            highlights.append(text)
    return highlights


def project_work_exp_entry(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Project one persisted work-history entry into the runtime object shape."""
    projected = _plain_mapping(value)
    projected["highlights"] = normalize_highlights(projected.get("highlights"))
    return projected


def build_cap_projection(user_state: Mapping[str, Any]) -> dict[str, Any]:
    """Return the lean capability snapshot Documents is allowed to consume.

    Capability hierarchy is deliberately excluded. User-managed Capability Sets
    are exposed only when their Document flag is enabled.
    """
    model = dict(user_state.get("capability_model") or {})
    raw_entities = [
        item for item in model.get("entities", []) if isinstance(item, Mapping)
    ]
    capabilities = [
        _capability(item)
        for item in raw_entities
        if str(item.get("type") or "").strip().casefold() != "set"
    ]
    capabilities = [item for item in capabilities if item]
    capabilities.sort(key=lambda item: (str(item["name"]).casefold(), str(item["type"])))

    by_id = {
        str(raw.get("id")): projected
        for raw, projected in (
            (raw, _capability(raw))
            for raw in raw_entities
            if str(raw.get("type") or "").strip().casefold() != "set"
        )
        if raw.get("id") and projected
    }

    members: dict[str, list[dict[str, Any]]] = {}
    for relationship in model.get("relationships", []):
        if not isinstance(relationship, Mapping):
            continue
        if str(relationship.get("type") or "") != "relevant_to":
            continue
        source_id = str(relationship.get("source_id") or "")
        target_id = str(relationship.get("target_id") or "")
        capability = by_id.get(source_id)
        if capability is not None:
            members.setdefault(target_id, []).append(dict(capability))

    sets: dict[str, list[dict[str, Any]]] = {}
    used_keys: set[str] = set()
    for raw in sorted(
        (
            item
            for item in raw_entities
            if str(item.get("type") or "").strip().casefold() == "set"
            and bool(item.get("document_enabled", True))
        ),
        key=lambda item: _entity_name(item).casefold(),
    ):
        set_id = str(raw.get("id") or "")
        name = _entity_name(raw)
        if not set_id or not name:
            continue
        base_key = str(raw.get("document_key") or raw.get("key") or "").strip()
        base_key = slugify_reference(base_key or name)
        key = base_key
        suffix = 2
        while key in used_keys:
            key = f"{base_key}_{suffix}"
            suffix += 1
        used_keys.add(key)
        values = members.get(set_id, [])
        sets[key] = sorted(values, key=lambda item: str(item["name"]).casefold())

    return {"all": capabilities, "sets": sets}


def build_expression_catalog(
    user_state: Mapping[str, Any],
    job: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the complete Documents runtime object catalog."""
    return {
        "user": _plain_mapping(user_state.get("user", {})),
        "job_ref": project_job_ref(job),
        "work_exp": [
            project_work_exp_entry(item)
            for item in user_state.get("work_history", [])
            if isinstance(item, Mapping) and item.get("enabled", True)
        ],
        "cap": build_cap_projection(user_state),
    }


def build_expression_reference(
    user_state: Mapping[str, Any],
    blueprints: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Describe the small supported Documents runtime language."""
    del blueprints
    catalog = build_expression_catalog(user_state, {})
    return {
        "output_placeholders": {
            "format": "{{ expression_key }}",
            "identifier_pattern": IDENTIFIER_PATTERN.pattern,
            "description": "Document expressions consume explicit JAW runtime objects.",
        },
        "template_variables": [],
        "context_references": [
            {
                "reference": "user",
                "label": "User",
                "kind": "record",
                "description": "Active user profile data.",
            },
            {
                "reference": "job_ref",
                "label": "Job reference",
                "kind": "record",
                "description": "Document-useful fields from the selected tracked job.",
            },
            {
                "reference": "work_exp",
                "label": "Work experience",
                "kind": "collection",
                "description": "Enabled work-experience entries and their evidence.",
            },
            {
                "reference": "cap",
                "label": "Capabilities",
                "kind": "record",
                "description": "Lean capability data and user-managed capability sets.",
                "count": len(catalog["cap"].get("all", [])),
            },
        ],
    }


def referenced_context(
    instructions: str,
    catalog: Mapping[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    """Return only explicitly referenced catalog entries, preserving nesting."""
    references: list[str] = []
    for match in REFERENCE_PATTERN.finditer(instructions):
        reference = match.group(1)
        if reference not in references:
            references.append(reference)
    unknown = [reference for reference in references if reference not in catalog]
    if unknown:
        raise ExpressionContextError(
            "Unknown generation context reference(s): " + ", ".join(unknown)
        )

    selected: dict[str, Any] = {}
    for reference in references:
        target = selected
        parts = reference.split(".")
        for part in parts[:-1]:
            child = target.setdefault(part, {})
            if not isinstance(child, dict):
                raise ExpressionContextError(
                    f"Generation context reference conflicts at {reference}"
                )
            target = child
        target[parts[-1]] = catalog[reference]
    return references, selected


def _capability(raw: Mapping[str, Any]) -> dict[str, Any]:
    name = _entity_name(raw)
    if not name:
        return {}
    result: dict[str, Any] = {
        "name": name,
        "type": str(raw.get("type") or ""),
        "aliases": [str(item) for item in raw.get("aliases", []) if str(item)],
    }
    if "rating" in raw and raw.get("rating") is not None:
        result["rating"] = int(raw["rating"])
    return result


def _entity_name(raw: Mapping[str, Any]) -> str:
    return str(raw.get("display_name") or raw.get("canonical_name") or "").strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if str(item)]


def _plain_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


__all__ = [
    "ExpressionContextError",
    "IDENTIFIER_PATTERN",
    "REFERENCE_PATTERN",
    "TEMPLATE_VARIABLES",
    "build_cap_projection",
    "build_expression_catalog",
    "build_expression_reference",
    "normalize_highlights",
    "project_job_ref",
    "project_work_exp_entry",
    "referenced_context",
    "slugify_reference",
]
