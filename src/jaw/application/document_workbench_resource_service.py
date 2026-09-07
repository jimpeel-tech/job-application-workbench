"""Source-aware resource-management operations for the Document Workbench."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..documents.workbench_symbols import (
    JAW_SYMBOLS,
    WorkbenchSyntaxError,
    bind_reference_occurrences,
    is_identifier,
    referenced_occurrences,
)
from ..persistence.document_workbench import DocumentWorkbenchRepository


def _source_resource_for_parent(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    parent_id: str,
) -> tuple[dict[str, Any], list[str]]:
    parent = repository.require_resource(user_id, parent_id)
    if parent["kind"] == "section":
        return parent, [parent_id]
    if parent["kind"] != "document":
        raise ValueError("Reference symbols can only be renamed in a Template or Section")
    document = repository.get_document(user_id, parent_id)
    if document is None:
        raise ValueError("Document was not found")
    template = repository.require_resource(user_id, document["template_id"])
    document_ids = [
        item["id"] for item in repository.documents_for_template(user_id, template["id"])
    ]
    return template, document_ids


def _effective_source(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    resource: Mapping[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    buffer = repository.get_buffer(user_id, str(resource["id"]))
    if buffer is not None:
        return str(buffer["content"]), buffer
    return str(resource.get("content") or ""), None


def _reference_from_payload(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    *,
    parent_id: str,
    child_id: str,
    reference_id: str,
) -> dict[str, Any]:
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


def _bound_occurrence(
    source: str,
    references: list[dict[str, Any]],
    reference_id: str,
) -> tuple[int, int]:
    try:
        bindings = bind_reference_occurrences(source, references)
    except WorkbenchSyntaxError as error:
        raise ValueError(str(error)) from error
    for occurrence, edge in bindings:
        if edge is not None and str(edge.get("id") or "") == reference_id:
            return occurrence.start, occurrence.end
    raise ValueError("The selected reference is not present in the current source")


def _corresponding_reference(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    parent_id: str,
    selected: Mapping[str, Any],
) -> dict[str, Any] | None:
    if parent_id == selected["parent_id"]:
        return dict(selected)
    order = int(selected.get("sort_order") or 0)
    edge_kind = str(selected.get("edge_kind") or "")
    return next(
        (
            edge
            for edge in repository.list_edges(user_id, parent_id)
            if int(edge.get("sort_order") or 0) == order
            and str(edge.get("edge_kind") or "") == edge_kind
        ),
        None,
    )


def _shift_cursor_for_range(
    cursor: int,
    *,
    start: int,
    end: int,
    replacement_length: int,
) -> int:
    position = max(0, int(cursor))
    delta = replacement_length - (end - start)
    if position <= start:
        return position
    if position >= end:
        return max(0, position + delta)
    return start + replacement_length


def rename_reference_symbol(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Rename exactly one durable reference while preserving resource identity."""

    parent_id = str(payload.get("parent_id") or "").strip()
    child_id = str(payload.get("child_id") or payload.get("resource_id") or "").strip()
    reference_id = str(payload.get("reference_id") or "").strip()
    new_symbol = str(payload.get("symbol") or "").strip()
    if not parent_id or not child_id or not new_symbol:
        raise ValueError("parent_id, child_id, and symbol are required")
    if not is_identifier(new_symbol):
        raise ValueError("Symbol must be a valid Jinja identifier")
    if new_symbol in JAW_SYMBOLS:
        raise ValueError(f"'{new_symbol}' is reserved by JAW")

    selected = _reference_from_payload(
        repository,
        user_id,
        parent_id=parent_id,
        child_id=child_id,
        reference_id=reference_id,
    )
    reference_id = str(selected["id"])
    old_symbol = str(selected["symbol"])
    if old_symbol == new_symbol:
        return {
            "reference_id": reference_id,
            "resource_id": child_id,
            "parent_id": parent_id,
            "old_symbol": old_symbol,
            "new_symbol": old_symbol,
            "changed": False,
        }

    source_resource, affected_parents = _source_resource_for_parent(
        repository, user_id, parent_id
    )
    source, buffer = _effective_source(repository, user_id, source_resource)
    start, end = _bound_occurrence(
        source,
        repository.list_edges(user_id, parent_id),
        reference_id,
    )
    rewritten = source[:start] + new_symbol + source[end:]

    try:
        occurrences = referenced_occurrences(rewritten)
    except WorkbenchSyntaxError as error:
        raise ValueError(str(error)) from error
    if not any(
        item.symbol == new_symbol and item.start == start
        for item in occurrences
    ):
        raise ValueError(
            f"'{new_symbol}' conflicts with a Jinja local, built-in, or JAW-owned symbol"
        )

    affected_edges: list[dict[str, Any]] = []
    for affected_parent in affected_parents:
        edge = _corresponding_reference(
            repository,
            user_id,
            affected_parent,
            selected,
        )
        if edge is not None:
            affected_edges.append(edge)
    if not affected_edges:
        raise ValueError("No matching Workbench references were found")

    updated_private: set[str] = set()
    for edge in affected_edges:
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
        if child["visibility"] == "private" and child["id"] not in updated_private:
            # The resource JID is identity. A reference edit may update the private
            # resource's canonical symbol, but never silently changes its display name.
            repository.update_resource(
                user_id,
                child["id"],
                symbol=new_symbol,
            )
            updated_private.add(child["id"])

    if buffer is None:
        repository.save_content(user_id, source_resource["id"], rewritten)
    else:
        cursor_start = int(buffer.get("cursor_start") or 0)
        cursor_end = int(buffer.get("cursor_end") or cursor_start)
        repository.checkpoint_buffer(
            user_id,
            source_resource["id"],
            rewritten,
            cursor_start=_shift_cursor_for_range(
                cursor_start,
                start=start,
                end=end,
                replacement_length=len(new_symbol),
            ),
            cursor_end=_shift_cursor_for_range(
                cursor_end,
                start=start,
                end=end,
                replacement_length=len(new_symbol),
            ),
        )

    return {
        "reference_id": reference_id,
        "resource_id": child_id,
        "parent_id": parent_id,
        "source_resource_id": source_resource["id"],
        "source_content": rewritten,
        "source_dirty": buffer is not None,
        "old_symbol": old_symbol,
        "new_symbol": new_symbol,
        "affected_parent_ids": [edge["parent_id"] for edge in affected_edges],
        "affected_reference_ids": [edge["id"] for edge in affected_edges],
        "affected_resource_ids": [edge["child_id"] for edge in affected_edges],
        "changed": True,
    }


def _inbound_edges(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    resource_id: str,
) -> list[dict[str, Any]]:
    return [
        edge for edge in repository.list_edges(user_id) if edge["child_id"] == resource_id
    ]


def _delete_private_tree_if_unreferenced(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    resource_id: str,
    deleted: list[str],
) -> None:
    try:
        resource = repository.require_resource(user_id, resource_id)
    except ValueError:
        return
    if resource["visibility"] == "global" or _inbound_edges(repository, user_id, resource_id):
        return
    children = [edge["child_id"] for edge in repository.list_edges(user_id, resource_id)]
    repository.delete_resource(user_id, resource_id)
    deleted.append(resource_id)
    for child_id in children:
        _delete_private_tree_if_unreferenced(repository, user_id, child_id, deleted)


def _delete_unreferenced_tree(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    resource_id: str,
    deleted: list[str],
) -> None:
    resource = repository.require_resource(user_id, resource_id)
    if _inbound_edges(repository, user_id, resource_id):
        raise ValueError("Resource is still referenced")
    if resource["kind"] not in {"section", "function"}:
        raise ValueError("Only unreferenced Sections and Functions can be deleted here")

    children = [edge["child_id"] for edge in repository.list_edges(user_id, resource_id)]
    repository.delete_resource(user_id, resource_id)
    deleted.append(resource_id)
    for child_id in children:
        _delete_private_tree_if_unreferenced(repository, user_id, child_id, deleted)


def _delete_template(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    resource: Mapping[str, Any],
    deleted: list[str],
) -> None:
    usage = repository.documents_for_template(user_id, str(resource["id"]))
    if usage:
        count = len(usage)
        raise ValueError(
            f"Template is used by {count} Document{'s' if count != 1 else ''}"
        )
    repository.delete_resource(user_id, str(resource["id"]))
    deleted.append(str(resource["id"]))


def _delete_document(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    document: Mapping[str, Any],
    deleted: list[str],
) -> None:
    document_id = str(document["id"])
    template_id = str(document["template_id"])
    section_ids = [edge["child_id"] for edge in repository.list_edges(user_id, document_id)]
    template = repository.require_resource(user_id, template_id)

    repository.delete_resource(user_id, document_id)
    deleted.append(document_id)

    for section_id in section_ids:
        _delete_private_tree_if_unreferenced(repository, user_id, section_id, deleted)

    if (
        not repository.documents_for_template(user_id, template_id)
        and template["visibility"] == "private"
    ):
        repository.delete_resource(user_id, template_id)
        deleted.append(template_id)


def delete_unreferenced_resource(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Delete an explicit resource using Workbench ownership rules.

    Sections/Functions must be unreferenced. Templates may be deleted only when no
    Document uses them. Explicit Document deletion removes the Document plus its
    now-unreferenced private resource tree and its unused private Template;
    global/shared resources survive.
    """

    resource_id = str(payload.get("resource_id") or payload.get("id") or "").strip()
    if not resource_id:
        raise ValueError("resource_id is required")
    resource = repository.require_resource(user_id, resource_id)
    deleted: list[str] = []
    if resource["kind"] == "document":
        document = repository.get_document(user_id, resource_id)
        if document is None:
            raise ValueError("Document was not found")
        _delete_document(repository, user_id, document, deleted)
    elif resource["kind"] == "template":
        _delete_template(repository, user_id, resource, deleted)
    else:
        _delete_unreferenced_tree(repository, user_id, resource_id, deleted)
    return {"deleted": deleted, "resource_id": resource_id}


__all__ = ["delete_unreferenced_resource", "rename_reference_symbol"]
