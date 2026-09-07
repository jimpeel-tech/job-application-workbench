"""Job-scoped generation and deterministic Document routing for the Workbench."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from datetime import date
from typing import Any

from ..documents.context import GenerationContext
from ..documents.expression_context import build_expression_catalog
from ..persistence.document_workbench import DocumentWorkbenchRepository
from .document_workbench_render import DocumentWorkbenchRenderer

# Kept as a public compatibility symbol. Routing is now entirely user-defined.
DEFAULT_GENERATION_RULES: tuple[dict[str, Any], ...] = ()
_ROUTING_SETTINGS_KEY = "generation_routing"
_ROUTING_SETTINGS_VERSION = 2


def _clean_keywords(values: object) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").strip().casefold().split())
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _clean_document_ids(raw: Mapping[str, Any]) -> list[str]:
    values = raw.get("document_ids")
    if not isinstance(values, (list, tuple)):
        legacy = str(raw.get("document_id") or "").strip()
        values = [legacy] if legacy else []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        document_id = str(value or "").strip()
        if document_id and document_id not in seen:
            seen.add(document_id)
            result.append(document_id)
    return result


def _normalize_rule(raw: Mapping[str, Any]) -> dict[str, Any]:
    rule_id = str(raw.get("id") or "").strip().casefold()
    if not rule_id or not re.fullmatch(r"[a-z][a-z0-9_-]*", rule_id):
        raise ValueError("Document routing rule id is invalid")
    label = str(raw.get("label") or rule_id.replace("_", " ").title()).strip()
    keywords = _clean_keywords(raw.get("keywords"))
    if not keywords:
        raise ValueError(f"Document routing rule '{label}' needs at least one keyword")
    document_ids = _clean_document_ids(raw)
    return {
        "id": rule_id,
        "label": label or rule_id,
        "priority": int(raw.get("priority") or 100),
        "keywords": keywords,
        "document_ids": document_ids,
        # Compatibility for older clients/tests that expect one Document.
        "document_id": document_ids[0] if document_ids else "",
    }


def _routing_payload(
    rules: list[dict[str, Any]],
    default_document_ids: list[str],
) -> dict[str, Any]:
    return {
        "rules": rules,
        "default_document_ids": default_document_ids,
        # Compatibility for older clients/tests.
        "default_document_id": default_document_ids[0] if default_document_ids else "",
    }


def _routing_from_documents(documents: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_id = {str(document.get("id") or ""): document for document in documents}

    # Version 2 stores the complete routing configuration on every Document. This
    # lets one rule target many Documents while keeping routing user-owned and
    # preserving it if one of the routed Documents is later removed.
    candidates: list[tuple[int, Mapping[str, Any]]] = []
    for document in documents:
        settings = dict(document.get("settings") or {})
        raw = settings.get(_ROUTING_SETTINGS_KEY)
        if isinstance(raw, Mapping):
            candidates.append((int(raw.get("revision") or 0), raw))
    if candidates:
        _, raw_state = max(candidates, key=lambda item: item[0])
        rules: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for raw_rule in raw_state.get("rules") or []:
            if not isinstance(raw_rule, Mapping):
                continue
            try:
                rule = _normalize_rule(raw_rule)
            except ValueError:
                continue
            if rule["id"] in seen_ids:
                continue
            seen_ids.add(rule["id"])
            rule["document_ids"] = [
                document_id
                for document_id in rule["document_ids"]
                if document_id in by_id
            ]
            rule["document_id"] = rule["document_ids"][0] if rule["document_ids"] else ""
            rules.append(rule)
        rules.sort(key=lambda item: (int(item["priority"]), str(item["id"])))
        defaults = [
            document_id
            for document_id in (
                str(value or "").strip()
                for value in raw_state.get("default_document_ids") or []
            )
            if document_id and document_id in by_id
        ]
        return _routing_payload(rules, defaults)

    # Legacy migration path: older routing stored one rule on each target Document.
    # Aggregate identical rule ids so old data immediately behaves like v2.
    rules_by_id: dict[str, dict[str, Any]] = {}
    default_document_ids: list[str] = []
    for document in documents:
        document_id = str(document.get("id") or "")
        settings = dict(document.get("settings") or {})
        if settings.get("generation_default") and document_id:
            default_document_ids.append(document_id)
        for raw_rule in settings.get("generation_rules") or []:
            if not isinstance(raw_rule, Mapping):
                continue
            try:
                rule = _normalize_rule({**raw_rule, "document_id": document_id})
            except ValueError:
                continue
            existing = rules_by_id.get(rule["id"])
            if existing is None:
                rules_by_id[rule["id"]] = rule
                continue
            for target_id in rule["document_ids"]:
                if target_id not in existing["document_ids"]:
                    existing["document_ids"].append(target_id)
            existing["document_id"] = existing["document_ids"][0]

    rules = sorted(
        rules_by_id.values(),
        key=lambda item: (int(item["priority"]), str(item["id"])),
    )
    return _routing_payload(rules, default_document_ids)


def routing_state(repository: DocumentWorkbenchRepository, user_id: int) -> dict[str, Any]:
    return _routing_from_documents(repository.list_documents(user_id))


def save_routing(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    documents = repository.list_documents(user_id)
    by_id = {str(document["id"]): document for document in documents}
    incoming = payload.get("rules") or []
    if not isinstance(incoming, list):
        raise ValueError("Document routing rules must be a list")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in incoming:
        if not isinstance(raw, Mapping):
            raise ValueError("Document routing rule is invalid")
        rule = _normalize_rule(raw)
        if rule["id"] in seen_ids:
            raise ValueError(f"Document routing rule '{rule['id']}' is duplicated")
        seen_ids.add(rule["id"])
        missing = [document_id for document_id in rule["document_ids"] if document_id not in by_id]
        if missing:
            raise ValueError(f"Document for routing rule '{rule['label']}' was not found")
        normalized.append(rule)

    raw_defaults = payload.get("default_document_ids")
    if not isinstance(raw_defaults, (list, tuple)):
        legacy_default = str(payload.get("default_document_id") or "").strip()
        raw_defaults = [legacy_default] if legacy_default else []
    default_document_ids: list[str] = []
    seen_defaults: set[str] = set()
    for value in raw_defaults:
        document_id = str(value or "").strip()
        if not document_id or document_id in seen_defaults:
            continue
        if document_id not in by_id:
            raise ValueError("Default routed Document was not found")
        seen_defaults.add(document_id)
        default_document_ids.append(document_id)

    stored_rules = [
        {
            "id": rule["id"],
            "label": rule["label"],
            "priority": rule["priority"],
            "keywords": rule["keywords"],
            "document_ids": rule["document_ids"],
        }
        for rule in normalized
    ]
    stored_state = {
        "version": _ROUTING_SETTINGS_VERSION,
        "revision": time.time_ns(),
        "rules": stored_rules,
        "default_document_ids": default_document_ids,
    }

    for document in documents:
        settings = dict(document.get("settings") or {})
        settings.pop("generation_rules", None)
        settings.pop("generation_default", None)
        settings[_ROUTING_SETTINGS_KEY] = stored_state
        repository.update_resource(user_id, str(document["id"]), settings=settings)

    return _routing_payload(normalized, default_document_ids)


def _keyword_match(title: str, keyword: str) -> bool:
    normalized_title = " ".join(str(title or "").casefold().split())
    normalized_keyword = " ".join(str(keyword or "").casefold().split())
    if not normalized_title or not normalized_keyword:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])"
    return re.search(pattern, normalized_title) is not None


def select_routed_documents(
    documents: list[Mapping[str, Any]],
    title: str,
    *,
    explicit_document_id: str = "",
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    by_id = {str(document.get("id") or ""): document for document in documents}
    explicit = str(explicit_document_id or "").strip()
    if explicit:
        document = by_id.get(explicit)
        if document is None:
            raise ValueError("Selected Document was not found")
        return [document], {"id": "manual", "label": "Manual", "keyword": ""}

    routing = _routing_from_documents(documents)
    for rule in routing["rules"]:
        keyword = next(
            (item for item in rule["keywords"] if _keyword_match(title, item)),
            "",
        )
        if not keyword:
            continue
        selected = [
            by_id[document_id]
            for document_id in rule["document_ids"]
            if document_id in by_id
        ]
        if not selected:
            raise ValueError(
                f"Document routing rule '{rule['label']}' matched but has no Documents assigned"
            )
        return selected, {
            "id": rule["id"],
            "label": rule["label"],
            "keyword": keyword,
        }

    selected = [
        by_id[document_id]
        for document_id in routing["default_document_ids"]
        if document_id in by_id
    ]
    if selected:
        return selected, {"id": "default", "label": "Default", "keyword": ""}
    raise ValueError(
        "No automatic Document is configured for this job. "
        "Open Ctrl+P and configure Document Routing or choose a Document manually."
    )


def select_routed_document(
    documents: list[Mapping[str, Any]],
    title: str,
    *,
    explicit_document_id: str = "",
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Compatibility wrapper for callers that need one selected Document."""
    selected, route = select_routed_documents(
        documents,
        title,
        explicit_document_id=explicit_document_id,
    )
    return selected[0], route


def _job_context(
    user_state: Mapping[str, Any],
    job: Mapping[str, Any],
    *,
    job_id: int,
) -> GenerationContext:
    catalog = build_expression_catalog(user_state, job)
    user = dict(catalog["user"])
    first = str(user.get("first_name") or "").strip()
    last = str(user.get("last_name") or "").strip()
    user["full_name"] = str(user.get("full_name") or "").strip() or " ".join(
        part for part in (first, last) if part
    )
    today = date.today()
    return GenerationContext(
        schema_version=2,
        source=f"job:{job_id}",
        user=user,
        job_ref=dict(catalog["job_ref"]),
        work_exp=tuple(dict(item) for item in catalog["work_exp"]),
        cap=dict(catalog["cap"]),
        system={
            "current_date": today.strftime("%B %d, %Y").replace(" 0", " "),
            "current_year": str(today.year),
            "greeting": "Dear Hiring Team,",
            "signoff": "Sincerely,",
        },
    )


def _generated_result(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    document: Mapping[str, Any],
    route: Mapping[str, Any],
    context: GenerationContext,
    *,
    job: Mapping[str, Any],
    job_id: int,
    output_directory: str | None,
    analysis_settings: Mapping[str, Any],
) -> dict[str, Any]:
    generated = DocumentWorkbenchRenderer(repository).generate(
        user_id,
        str(document["id"]),
        context.as_mapping(),
        output_directory=output_directory,
        analysis_settings=analysis_settings,
    )
    generated.pop("pdf_base64", None)
    return {
        **generated,
        "document_id": str(document["id"]),
        "document_name": str(document.get("name") or "Document"),
        "job_id": job_id,
        "job_title": str(job.get("title") or ""),
        "company": str(job.get("company") or ""),
        "route": dict(route),
    }


def generate_job(
    repository: DocumentWorkbenchRepository,
    user_id: int,
    *,
    job: Mapping[str, Any],
    user_state: Mapping[str, Any],
    job_id: int,
    document_id: str = "",
    output_directory: str | None = None,
    analysis_settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if job_id <= 0:
        raise ValueError("Tracked job id is required")
    if job.get("id") and int(job.get("id") or 0) != job_id:
        raise ValueError("Tracked job context does not match the requested job")

    documents = repository.list_documents(user_id)
    selected, route = select_routed_documents(
        documents,
        str(job.get("title") or ""),
        explicit_document_id=document_id,
    )
    context = _job_context(user_state, job, job_id=job_id)
    settings = analysis_settings if isinstance(analysis_settings, Mapping) else {}
    results = [
        _generated_result(
            repository,
            user_id,
            document,
            route,
            context,
            job=job,
            job_id=job_id,
            output_directory=output_directory,
            analysis_settings=settings,
        )
        for document in selected
    ]
    if len(results) == 1:
        return results[0]
    return {
        "batch": True,
        "generated_documents": results,
        "job_id": job_id,
        "job_title": str(job.get("title") or ""),
        "company": str(job.get("company") or ""),
        "route": dict(route),
        "document_ids": [str(document["id"]) for document in selected],
    }


__all__ = [
    "DEFAULT_GENERATION_RULES",
    "generate_job",
    "routing_state",
    "save_routing",
    "select_routed_document",
    "select_routed_documents",
]
