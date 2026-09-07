"""Candidate and job context assembly for all analysis providers."""

from __future__ import annotations

import json
from typing import Any

from ..capture import extract_job_fields
from ..config import (
    RATING_GUIDANCE,
    AppConfig,
    CapabilityEntry,
    RelationshipEntry,
)
from .contracts import AnalysisRequest


def capability_payload(capability: CapabilityEntry) -> dict[str, Any]:
    return {
        "id": capability.id,
        "type": capability.type,
        "name": capability.name,
        "canonical_name": capability.canonical_name,
        "aliases": list(capability.aliases),
        "rating": capability.rating,
    }


def relationship_payload(
    relationship: RelationshipEntry,
    by_id: dict[str, CapabilityEntry],
) -> dict[str, str] | None:
    source = by_id.get(relationship.source_id)
    target = by_id.get(relationship.target_id)
    if source is None or target is None:
        return None

    return {
        "source_id": source.id,
        "source": source.name,
        "type": relationship.type,
        "target_id": target.id,
        "target": target.name,
    }


def candidate_context_data(config: AppConfig) -> dict[str, Any]:
    """Build the provider-neutral candidate snapshot used for job analysis.

    ``match_enabled`` controls which rateable capabilities are sent for matching.
    Ratings remain authoritative; relationships describe semantic adjacency and
    never promote an unrated capability into claimed experience.
    """
    matching = list(config.job_matching_capabilities)
    matching_ids = {capability.id for capability in matching}
    by_id = config.capability_by_id

    relationships: list[dict[str, str]] = []
    for relationship in config.relationships:
        if (
            relationship.source_id not in matching_ids
            and relationship.target_id not in matching_ids
        ):
            continue

        payload = relationship_payload(relationship, by_id)
        if payload is not None:
            relationships.append(payload)

    capability_sets = [
        {
            "id": capability_set.id,
            "name": capability_set.name,
            "capability_ids": list(capability_set.capability_ids),
        }
        for capability_set in config.capability_sets
        if not capability_set.system
    ]

    work_history = [
        {
            "title": entry.title,
            "company": entry.company,
            "start": entry.start,
            "end": entry.end,
            "highlights": entry.highlights,
        }
        for entry in config.work_history
        if entry.enabled
    ]

    return {
        "rating_scale": {
            str(rating): {
                "label": guidance["label"],
                "description": guidance["description"],
            }
            for rating, guidance in RATING_GUIDANCE.items()
        },
        "capabilities": [capability_payload(capability) for capability in matching],
        "relationships": relationships,
        "capability_sets": capability_sets,
        "work_history": work_history,
    }


def candidate_context(config: AppConfig) -> str:
    """Compatibility helper returning the candidate snapshot as readable JSON."""
    return json.dumps(candidate_context_data(config), ensure_ascii=False, indent=2)


def build_analysis_request(
    config: AppConfig,
    description: str,
) -> AnalysisRequest:
    extracted = extract_job_fields(description)
    return AnalysisRequest(
        description=description,
        candidate=candidate_context_data(config),
        extracted_job=extracted,
    )
