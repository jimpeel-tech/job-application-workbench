from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .capture import extract_job_fields
from .value_canonicalization import canonical_capture_value
from .work_arrangement import analyze_work_arrangement

_RESULT_FIELD_KEYS = (
    "company",
    "title",
    "pay",
    "remote_status",
    "location",
    "employment_type",
    "schedule",
    "on_call",
    "travel",
    "clearance",
    "sponsorship",
    "application_deadline",
)

_PAY_COMPONENTS = ("pay_min", "pay_max", "currency", "pay_period")


@dataclass(frozen=True)
class ParserCandidateEvidence:
    value: str
    priority: int
    support_count: int
    occurrence_count: int
    contexts: tuple[str, ...]
    selected: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "priority": self.priority,
            "support_count": self.support_count,
            "occurrence_count": self.occurrence_count,
            "contexts": list(self.contexts),
            "selected": self.selected,
        }


@dataclass(frozen=True)
class ParserFieldResolution:
    values: tuple[str, ...]
    priority: int
    support_count: int
    corroborated: bool
    contexts: tuple[str, ...]
    candidates: tuple[ParserCandidateEvidence, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "values": list(self.values),
            "priority": self.priority,
            "support_count": self.support_count,
            "corroborated": self.corroborated,
            "contexts": list(self.contexts),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True)
class ParserResolution:
    values: dict[str, tuple[str, ...]]
    fields: dict[str, ParserFieldResolution]

    def as_dict(self) -> dict[str, Any]:
        return {
            "values": {key: list(values) for key, values in self.values.items() if values},
            "fields": {key: value.as_dict() for key, value in self.fields.items()},
        }


def _field_priority(field: str, context: str) -> int:
    context = str(context or "").strip().lower()
    if field == "title":
        return {
            "job_title": 100,
            "job_description": 50,
            "combined": 30,
            "job_metadata": 15,
            "requirements": 5,
            "responsibilities": 5,
        }.get(context, 40)
    if field == "company":
        return {
            "company": 100,
            "job_description": 50,
            "combined": 30,
            "job_metadata": 20,
            "requirements": 5,
            "responsibilities": 5,
        }.get(context, 40)
    if field in {
        "pay_min",
        "pay_max",
        "currency",
        "pay_period",
        "remote_status",
        "location",
        "employment_type",
        "schedule",
        "on_call",
        "travel",
        "clearance",
        "sponsorship",
        "application_deadline",
    }:
        return {
            "work_arrangement": 95,
            "job_metadata": 90,
            "job_description": 55,
            "combined": 30,
            "job_title": 10,
            "company": 10,
            "requirements": 20,
            "responsibilities": 15,
        }.get(context, 40)
    return 40


def resolve_parser_evidence(
    extractions: Iterable[dict[str, Any]],
    combined_text: str = "",
) -> ParserResolution:
    """Resolve parser facts while retaining candidate and corroboration evidence.

    Context priority is authoritative. Independent capture repetition only breaks
    ties between candidates with the same top context priority; it never allows
    repeated low-authority inference to overrule an explicit high-authority fact.
    The synthetic whole-session extraction is fallback evidence and does not count
    as independent corroboration. Structured workplace evidence is resolved
    separately and outranks legacy whole-text workplace guesses.
    """
    occurrences: dict[str, list[dict[str, Any]]] = {}

    def add_value(
        field: str,
        value: str,
        *,
        context: str,
        capture_index: int | None,
    ) -> None:
        value = str(value).strip()
        if not value:
            return
        occurrences.setdefault(field, []).append(
            {
                "value": value,
                "key": canonical_capture_value(field, value),
                "priority": _field_priority(field, context),
                "context": context or "contextless",
                "capture_index": capture_index,
            }
        )

    def add_extraction(
        extraction: dict[str, Any],
        *,
        fallback_context: str = "",
        capture_index: int | None,
    ) -> None:
        context = str(extraction.get("capture_context", fallback_context))
        fields = extraction.get("fields", {})
        if not isinstance(fields, dict):
            return
        for raw_field, raw_value in fields.items():
            if isinstance(raw_value, (list, dict)):
                continue
            add_value(
                str(raw_field),
                str(raw_value),
                context=context,
                capture_index=capture_index,
            )

    for capture_index, extraction in enumerate(extractions, start=1):
        if isinstance(extraction, dict):
            add_extraction(extraction, capture_index=capture_index)

    if combined_text.strip():
        add_extraction(
            extract_job_fields(combined_text),
            fallback_context="combined",
            capture_index=None,
        )
        work_arrangement = analyze_work_arrangement(combined_text)
        if work_arrangement.status:
            add_value(
                "remote_status",
                work_arrangement.status,
                context="work_arrangement",
                capture_index=None,
            )
        if work_arrangement.location:
            add_value(
                "location",
                work_arrangement.location,
                context="work_arrangement",
                capture_index=None,
            )

    fields: dict[str, ParserFieldResolution] = {}
    scalar_values: dict[str, list[str]] = {}
    for field, field_occurrences in occurrences.items():
        resolution = _resolve_field(field_occurrences)
        fields[field] = resolution
        scalar_values[field] = list(resolution.values)

    pay_min = (scalar_values.get("pay_min") or [""])[0]
    pay_max = (scalar_values.get("pay_max") or [""])[0]
    currency = (scalar_values.get("currency") or [""])[0]
    period = (scalar_values.get("pay_period") or [""])[0]
    if pay_min or pay_max:
        symbol = "$" if currency == "USD" else f"{currency} "
        amount = pay_min if pay_min == pay_max or not pay_max else f"{pay_min}–{pay_max}"
        pay_value = f"{symbol}{amount}{f' per {period}' if period else ''}"
        scalar_values["pay"] = [pay_value]
        pay_resolution = _pay_resolution(pay_value, fields)
        fields["pay"] = pay_resolution

    values = {key: tuple(scalar_values.get(key, [])) for key in _RESULT_FIELD_KEYS}
    return ParserResolution(values=values, fields=fields)


def resolve_parser_values(
    extractions: Iterable[dict[str, Any]],
    combined_text: str = "",
) -> dict[str, tuple[str, ...]]:
    """Compatibility view over the richer cross-capture parser resolution."""
    return resolve_parser_evidence(extractions, combined_text).values


def _resolve_field(occurrences: list[dict[str, Any]]) -> ParserFieldResolution:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for occurrence in occurrences:
        grouped.setdefault(str(occurrence["key"]), []).append(occurrence)

    summaries: list[dict[str, Any]] = []
    for group in grouped.values():
        priority = max(int(item["priority"]) for item in group)
        independent = {
            int(item["capture_index"])
            for item in group
            if item.get("capture_index") is not None
        }
        support_count = len(independent)
        contexts = tuple(dict.fromkeys(str(item["context"]) for item in group))
        display = next(
            str(item["value"])
            for item in group
            if int(item["priority"]) == priority
        )
        summaries.append(
            {
                "value": display,
                "priority": priority,
                "support_count": support_count,
                "occurrence_count": len(group),
                "contexts": contexts,
            }
        )

    top_priority = max(int(item["priority"]) for item in summaries)
    top = [item for item in summaries if int(item["priority"]) == top_priority]
    best_support = max(int(item["support_count"]) for item in top)
    winners = [item for item in top if int(item["support_count"]) == best_support]
    winner_values = tuple(str(item["value"]) for item in winners)
    winner_contexts = tuple(
        dict.fromkeys(context for item in winners for context in item["contexts"])
    )

    candidates = tuple(
        ParserCandidateEvidence(
            value=str(item["value"]),
            priority=int(item["priority"]),
            support_count=int(item["support_count"]),
            occurrence_count=int(item["occurrence_count"]),
            contexts=tuple(item["contexts"]),
            selected=item in winners,
        )
        for item in sorted(
            summaries,
            key=lambda candidate: (
                -int(candidate["priority"]),
                -int(candidate["support_count"]),
                str(candidate["value"]).casefold(),
            ),
        )
    )
    return ParserFieldResolution(
        values=winner_values,
        priority=top_priority,
        support_count=best_support,
        corroborated=best_support >= 2,
        contexts=winner_contexts,
        candidates=candidates,
    )


def _pay_resolution(
    pay_value: str,
    fields: dict[str, ParserFieldResolution],
) -> ParserFieldResolution:
    components = [fields[key] for key in _PAY_COMPONENTS if key in fields and fields[key].values]
    if not components:
        return ParserFieldResolution((pay_value,), 0, 0, False, (), ())
    positive_support = [item.support_count for item in components if item.support_count > 0]
    support = min(positive_support) if positive_support else 0
    priority = min(item.priority for item in components)
    contexts = tuple(dict.fromkeys(context for item in components for context in item.contexts))
    candidate = ParserCandidateEvidence(
        value=pay_value,
        priority=priority,
        support_count=support,
        occurrence_count=max(item.candidates[0].occurrence_count for item in components),
        contexts=contexts,
        selected=True,
    )
    return ParserFieldResolution(
        values=(pay_value,),
        priority=priority,
        support_count=support,
        corroborated=support >= 2,
        contexts=contexts,
        candidates=(candidate,),
    )


__all__ = [
    "ParserCandidateEvidence",
    "ParserFieldResolution",
    "ParserResolution",
    "resolve_parser_evidence",
    "resolve_parser_values",
]
