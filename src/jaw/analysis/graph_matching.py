"""Deterministic capability mention and relationship matching."""

from __future__ import annotations

import re

from ..config import AppConfig, CapabilityEntry
from .normalization import dedupe_strings

TRANSFER_RELATIONSHIPS = {
    "based_on": 1.0,
    "uses": 0.75,
    "related_to": 0.6,
}


def term_pattern(term: str, case_sensitive: bool = False) -> re.Pattern[str]:
    escaped = re.escape(term.strip())
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(
        rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])",
        flags,
    )


def term_present(text: str, term: str) -> bool:
    term = term.strip()
    if not term:
        return False

    compact = re.sub(r"\s+", " ", term)
    if len(compact) <= 2:
        return bool(term_pattern(compact, case_sensitive=True).search(text))

    return bool(term_pattern(compact).search(text))


def capability_terms(capability: CapabilityEntry) -> list[str]:
    return dedupe_strings(
        [
            capability.name,
            capability.canonical_name,
            *capability.aliases,
        ]
    )


def mentioned_capabilities(
    config: AppConfig,
    description: str,
) -> list[CapabilityEntry]:
    mentioned: list[CapabilityEntry] = []

    for capability in config.job_matching_capabilities:
        if any(
            term_present(description, term)
            for term in capability_terms(capability)
        ):
            mentioned.append(capability)

    return mentioned


def transfer_candidates(
    config: AppConfig,
    capability: CapabilityEntry,
) -> list[tuple[float, tuple[str, ...], CapabilityEntry]]:
    """Return rated, match-enabled evidence within two semantic hops.

    A second hop captures sibling products that share a foundation (for
    example, EKS -> Kubernetes <- OKE). The distance penalty keeps direct
    evidence stronger. These candidates are contextual evidence only: the
    requested capability keeps its own rating and is never promoted by the
    graph.
    """
    by_id = config.capability_by_id
    adjacency: dict[str, list[tuple[str, str, float]]] = {}

    for relationship in config.relationships:
        weight = TRANSFER_RELATIONSHIPS.get(relationship.type)
        if weight is None:
            continue

        adjacency.setdefault(relationship.source_id, []).append(
            (relationship.target_id, relationship.type, weight)
        )
        adjacency.setdefault(relationship.target_id, []).append(
            (relationship.source_id, relationship.type, weight)
        )

    candidates_by_id: dict[
        str, tuple[float, tuple[str, ...], CapabilityEntry]
    ] = {}
    frontier: list[tuple[str, float, tuple[str, ...]]] = [
        (capability.id, 1.0, ())
    ]
    best_path_weight = {capability.id: 1.0}

    for depth in range(1, 3):
        next_frontier: list[tuple[str, float, tuple[str, ...]]] = []
        for current_id, current_weight, current_path in frontier:
            for other_id, relationship_type, edge_weight in adjacency.get(
                current_id, []
            ):
                if other_id == capability.id:
                    continue

                path = (*current_path, relationship_type)
                distance_penalty = 0.7 if depth > 1 else 1.0
                path_weight = current_weight * edge_weight * distance_penalty
                if path_weight <= best_path_weight.get(other_id, -1.0):
                    continue

                best_path_weight[other_id] = path_weight
                next_frontier.append((other_id, path_weight, path))
                other = by_id.get(other_id)
                if (
                    other is None
                    or not other.rateable
                    or not other.match_enabled
                    or other.rating < 3
                ):
                    continue

                candidates_by_id[other.id] = (path_weight, path, other)

        frontier = next_frontier

    candidates = list(candidates_by_id.values())
    candidates.sort(
        key=lambda item: (
            -item[0],
            -item[2].rating,
            item[2].name.casefold(),
        )
    )
    return candidates


def local_capability_score(
    config: AppConfig,
    mentioned: list[CapabilityEntry],
) -> int:
    if not mentioned:
        return 35

    rating_value = {
        # 0 is unknown/unassessed, not evidence of zero knowledge. Give it a
        # neutral-low contribution rather than treating it as a confirmed gap.
        0: 0.35,
        1: 0.2,
        2: 0.4,
        3: 0.68,
        4: 0.86,
        5: 1.0,
    }

    values: list[float] = []
    for capability in mentioned:
        value = rating_value.get(capability.rating, 0.0)
        if capability.rating == 0:
            transfer = transfer_candidates(config, capability)
            if transfer:
                weight, _relationship_path, neighbor = transfer[0]
                value = min(
                    0.45,
                    0.18
                    + weight * 0.18
                    + max(0, neighbor.rating - 3) * 0.04,
                )
        values.append(value)

    coverage = sum(values) / len(values)
    return min(95, max(20, round(20 + coverage * 75)))
