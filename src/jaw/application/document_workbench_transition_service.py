"""Explicit source-to-graph transitions for edited Workbench references.

Interactive editing is free-form. This service is called only when an explicit
Update/Create/Remove action is committed. The durable ``ref_*`` JID is the identity
of the relationship being changed; visible symbols are case-sensitive text and may
be duplicated within the same parent scope.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..documents.workbench_symbols import (
    JAW_SYMBOLS,
    ReferenceOccurrence,
    WorkbenchSyntaxError,
    is_identifier,
    referenced_occurrences,
)
from ..persistence.document_workbench import DocumentWorkbenchRepository
from .document_workbench_resource_service import delete_unreferenced_resource

_ACTIONS = {"update", "create", "remove"}


def _required(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _reference_from_payload(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    parent_id = _required(payload, "parent_id")
    child_id = _required(payload, "child_id")
    reference_id = str(payload.get("reference_id") or "").strip()
    if reference_id:
        reference = repository.require_reference(user_id, reference_id)
        if reference["parent_id"] != parent_id or reference["child_id"] != child_id:
            raise ValueError("Reference JID does not match the selected relationship")
        return reference

    matches = [
        edge
        for edge in repository.list_edges(user_id, parent_id)
        if edge["child_id"] == child_id
    ]
    if len(matches) != 1:
        raise ValueError("reference_id is required for this Workbench relationship")
    return matches[0]


def _source_resource(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    parent_id: str,
) -> dict[str, Any]:
    parent = repository.require_resource(user_id, parent_id)
    if parent["kind"] == "section":
        return parent
    if parent["kind"] != "document":
        raise ValueError("References can only be edited in a Template or Section")
    document = repository.get_document(user_id, parent_id)
    if document is None:
        raise ValueError("Document was not found")
    return repository.require_resource(user_id, document["template_id"])


def _affected_parents_for_source(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    parent_id: str,
) -> list[str]:
    """Return graph scopes that share the source being edited."""

    parent = repository.require_resource(user_id, parent_id)
    if parent["kind"] == "section":
        return [parent_id]
    if parent["kind"] != "document":
        raise ValueError("References can only be edited in a Template or Section")
    document = repository.get_document(user_id, parent_id)
    if document is None:
        raise ValueError("Document was not found")
    return [
        item["id"]
        for item in repository.documents_for_template(user_id, document["template_id"])
    ]


def _corresponding_references(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    parent_id: str,
    selected: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Resolve the same source occurrence in every graph scope sharing the source."""

    order = int(selected.get("sort_order") or 0)
    edge_kind = str(selected.get("edge_kind") or "")
    result: list[dict[str, Any]] = []
    for affected_parent in _affected_parents_for_source(repository, user_id, parent_id):
        if affected_parent == parent_id:
            result.append(dict(selected))
            continue
        candidates = [
            edge
            for edge in repository.list_edges(user_id, affected_parent)
            if int(edge.get("sort_order") or 0) == order
            and str(edge.get("edge_kind") or "") == edge_kind
        ]
        if candidates:
            result.append(candidates[0])
    return result


def _validated_occurrences(source: str) -> list[ReferenceOccurrence]:
    try:
        return referenced_occurrences(source)
    except WorkbenchSyntaxError as error:
        raise ValueError(str(error)) from error


def _validate_symbol(symbol: str) -> None:
    if not is_identifier(symbol):
        raise ValueError("The edited reference must resolve to one valid Jinja identifier")
    if symbol in JAW_SYMBOLS:
        raise ValueError(f"'{symbol}' is owned by JAW and cannot become a Workbench resource")


def _resolve_occurrence(
    source: str,
    reference: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> tuple[ReferenceOccurrence, list[ReferenceOccurrence]]:
    occurrences = _validated_occurrences(source)
    hint = str(payload.get("symbol") or "").strip()
    valid_hint = hint if is_identifier(hint) else ""

    start_value = payload.get("reference_start")
    end_value = payload.get("reference_end")
    if start_value is not None and end_value is not None:
        start = max(0, int(start_value))
        end = max(start, int(end_value))
        positional = [
            occurrence
            for occurrence in occurrences
            if occurrence.end > start and occurrence.start < max(end, start + 1)
        ]
        if valid_hint:
            exact = [item for item in positional if item.symbol == valid_hint]
            if len(exact) == 1:
                _validate_symbol(exact[0].symbol)
                return exact[0], occurrences
        if len(positional) == 1:
            _validate_symbol(positional[0].symbol)
            return positional[0], occurrences

    # Browser token/range state is deliberately only a hint. A user may edit
    # through temporarily invalid Jinja, which can leave the tracked token range
    # pointing at stale text. If the final valid source has exactly one Workbench
    # occurrence, it is unambiguous and should win over stale editor hints.
    if valid_hint:
        candidates = [item for item in occurrences if item.symbol == valid_hint]
        if len(candidates) == 1:
            _validate_symbol(candidates[0].symbol)
            return candidates[0], occurrences

    if len(occurrences) == 1:
        _validate_symbol(occurrences[0].symbol)
        return occurrences[0], occurrences
    if not occurrences:
        raise ValueError("The edited construct does not contain a new Section/Function reference")
    raise ValueError(
        "The edited construct contains multiple new Workbench references; "
        "make one structural change at a time"
    )


def _checkpoint_source(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    parent_id: str,
    source: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    resource = _source_resource(repository, user_id, parent_id)
    return repository.checkpoint_buffer(
        user_id,
        resource["id"],
        source,
        cursor_start=int(payload.get("cursor_start") or 0),
        cursor_end=int(payload.get("cursor_end") or 0),
    )


def _resource_has_other_references(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    child_id: str,
    selected_reference_ids: set[str],
) -> bool:
    return any(
        edge["child_id"] == child_id and str(edge.get("id") or "") not in selected_reference_ids
        for edge in repository.list_edges(user_id)
    )


def _source_still_needs_selected_reference(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    parent_id: str,
    reference: Mapping[str, Any],
    occurrences: list[ReferenceOccurrence],
) -> bool:
    """Return whether the edited source still needs this old reference occurrence.

    Create means "bind the edited/new occurrence to a new resource". If the old
    visible symbol still exists in source, its durable reference must survive too.
    Counts matter because duplicate visible symbols are valid and independently
    bound by reference JID.
    """

    old_symbol = str(reference.get("symbol") or "")
    source_count = sum(1 for item in occurrences if item.symbol == old_symbol)
    if source_count <= 0:
        return False

    selected_id = str(reference.get("id") or "")
    other_bound_count = sum(
        1
        for edge in repository.list_edges(user_id, parent_id)
        if str(edge.get("id") or "") != selected_id
        and str(edge.get("symbol") or "") == old_symbol
    )
    return source_count > other_bound_count


def _update_explicit_binding(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    *,
    parent_id: str,
    reference: Mapping[str, Any],
    new_symbol: str,
) -> list[str]:
    """Rename exactly one reference occurrence in every scope sharing its source."""

    affected = _corresponding_references(repository, user_id, parent_id, reference)
    if not affected:
        raise ValueError("No matching Workbench references were found")

    resource_ids: list[str] = []
    for edge in affected:
        repository.link(
            user_id,
            edge["parent_id"],
            edge["child_id"],
            edge_kind=edge["edge_kind"],
            symbol=new_symbol,
            sort_order=int(edge["sort_order"]),
            reference_id=str(edge["id"]),
        )
        child = repository.require_resource(user_id, edge["child_id"])
        if child["visibility"] == "private":
            repository.update_resource(
                user_id,
                child["id"],
                symbol=new_symbol,
                state="active",
            )
        resource_ids.append(str(edge["child_id"]))
    return resource_ids


def validate_reference_transition(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one pending decision without changing source, references, or resources."""

    action = _required(payload, "action").casefold()
    if action not in _ACTIONS:
        raise ValueError("Reference action must be update, create, or remove")

    parent_id = _required(payload, "parent_id")
    child_id = _required(payload, "child_id")
    source = str(payload.get("source_content") or "")
    reference = _reference_from_payload(repository, user_id, payload)
    child = repository.require_resource(user_id, child_id)
    old_symbol = str(reference["symbol"])

    occurrence: ReferenceOccurrence | None = None
    occurrences: list[ReferenceOccurrence] = _validated_occurrences(source)
    symbol = ""
    if action in {"update", "create"}:
        occurrence, occurrences = _resolve_occurrence(source, reference, payload)
        symbol = occurrence.symbol

    affected = _corresponding_references(repository, user_id, parent_id, reference)
    affected_reference_ids = {str(edge["id"]) for edge in affected}
    preserve_selected_reference = action == "create" and _source_still_needs_selected_reference(
        repository,
        user_id,
        parent_id,
        reference,
        occurrences,
    )
    old_still_referenced = preserve_selected_reference or _resource_has_other_references(
        repository,
        user_id,
        child_id,
        affected_reference_ids,
    )

    disposition = str(payload.get("disposition") or "").strip().casefold()
    requires_disposition = ""
    if action != "update" and not old_still_referenced:
        if child["visibility"] == "global":
            requires_disposition = "remove"
            if disposition not in {"preview", "remove"}:
                raise ValueError("Confirm removal of the Global reference")
        else:
            requires_disposition = "stage-delete"
            if disposition not in {"preview", "stage", "delete"}:
                raise ValueError(
                    "Choose Stage or Delete before removing the last private reference"
                )

    return {
        "validated": True,
        "action": action,
        "reference_id": str(reference["id"]),
        "parent_id": parent_id,
        "child_id": child_id,
        "old_symbol": old_symbol,
        "new_symbol": symbol,
        "reference_order": int(reference.get("sort_order") or 0),
        "occurrence_order": occurrence.order if occurrence is not None else None,
        "symbols": [item.symbol for item in occurrences],
        "old_still_referenced": old_still_referenced,
        "preserve_selected_reference": preserve_selected_reference,
        "requires_disposition": requires_disposition,
        "visibility": child["visibility"],
        "kind": child["kind"],
    }


def _create_explicit_resource(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    *,
    parent_id: str,
    symbol: str,
    sort_order: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    parent = repository.require_resource(user_id, parent_id)
    if parent["kind"] == "document":
        child_kind = "section"
        edge_kind = "section"
        settings: dict[str, Any] = {"content_shape": "paragraphs"}
    elif parent["kind"] == "section":
        child_kind = "function"
        edge_kind = "function"
        settings = {}
    else:
        raise ValueError("New references can only create Sections or Functions")

    child = repository.create_resource(
        user_id,
        child_kind,
        symbol=symbol,
        visibility="private",
        state="active",
        owner_id=parent_id,
        content="",
        settings=settings,
    )
    reference = repository.link(
        user_id,
        parent_id,
        child["id"],
        edge_kind=edge_kind,
        symbol=symbol,
        sort_order=sort_order,
    )
    return child, reference


def _remove_reference_resource(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    edge: Mapping[str, Any],
    *,
    disposition: str,
) -> tuple[bool, list[str]]:
    child_id = str(edge["child_id"])
    child = repository.require_resource(user_id, child_id)
    repository.unlink_reference(user_id, str(edge["id"]))

    if child["visibility"] == "global":
        return False, []
    if any(item["child_id"] == child_id for item in repository.list_edges(user_id)):
        return False, []
    if disposition == "stage":
        repository.update_resource(user_id, child_id, state="orphaned")
        return True, []
    if disposition == "delete":
        result = delete_unreferenced_resource(
            repository,
            user_id,
            {"resource_id": child_id},
        )
        return False, list(result.get("deleted") or [])
    return False, []


def resolve_reference_transition(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    payload: Mapping[str, Any],
    *,
    validation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Commit one validated Update/Create/Remove decision."""

    checked = dict(validation or validate_reference_transition(repository, user_id, payload))
    action = str(checked["action"])
    parent_id = str(checked["parent_id"])
    reference_id = str(checked["reference_id"])
    child_id = str(checked["child_id"])
    symbol = str(checked["new_symbol"])
    source = str(payload.get("source_content") or "")

    if str(payload.get("disposition") or "").strip().casefold() == "preview":
        return {**checked, "source_content": source}

    selected = repository.require_reference(user_id, reference_id)
    if action == "update":
        affected_resource_ids = _update_explicit_binding(
            repository,
            user_id,
            parent_id=parent_id,
            reference=selected,
            new_symbol=symbol,
        )
        checkpoint = _checkpoint_source(repository, user_id, parent_id, source, payload)
        return {
            **checked,
            "resource_id": child_id,
            "affected_resource_ids": affected_resource_ids,
            "source_content": source,
            "checkpoint": checkpoint,
        }

    affected = (
        []
        if action == "create" and checked.get("preserve_selected_reference")
        else _corresponding_references(repository, user_id, parent_id, selected)
    )
    disposition = str(payload.get("disposition") or "").strip().casefold()
    if not disposition and checked.get("old_still_referenced") and affected:
        disposition = "remove"
    staged = False
    deleted: list[str] = []
    removed_reference_ids: list[str] = []

    for edge in affected:
        removed_reference_ids.append(str(edge["id"]))
        did_stage, removed = _remove_reference_resource(
            repository,
            user_id,
            edge,
            disposition=disposition,
        )
        staged = staged or did_stage
        for resource_id in removed:
            if resource_id not in deleted:
                deleted.append(resource_id)

    created_resource_ids: list[str] = []
    created_reference_ids: list[str] = []
    if action == "create":
        occurrence_order = checked.get("occurrence_order")
        order = int(
            occurrence_order
            if occurrence_order is not None
            else checked.get("reference_order") or 0
        )
        for affected_parent in _affected_parents_for_source(repository, user_id, parent_id):
            child, reference = _create_explicit_resource(
                repository,
                user_id,
                parent_id=affected_parent,
                symbol=symbol,
                sort_order=order,
            )
            created_resource_ids.append(str(child["id"]))
            created_reference_ids.append(str(reference["id"]))

    checkpoint = _checkpoint_source(repository, user_id, parent_id, source, payload)
    return {
        **checked,
        "resource_id": child_id,
        "removed_reference_ids": removed_reference_ids,
        "created_resource_id": created_resource_ids[0] if created_resource_ids else None,
        "created_resource_ids": created_resource_ids,
        "created_reference_ids": created_reference_ids,
        "disposition": disposition or "preserve",
        "staged": staged,
        "deleted": deleted,
        "source_content": source,
        "checkpoint": checkpoint,
    }


__all__ = ["resolve_reference_transition", "validate_reference_transition"]