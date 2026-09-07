"""Persistent context selection for native Document Workbench generation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from typing import Any

from ..documents.context import (
    ExampleContextProvider,
    GenerationContext,
    JobContextProvider,
)
from ..documents.expression_context import build_expression_catalog
from ..persistence.user_repository import UserRepository

_PREFERENCE_PREFIX = "document_generation_context:"
_VALID_MODES = {"auto", "example", "selected"}
_NO_JOBS_ERROR = "No tracked jobs available. Choose Example Data or add a job."
_MISSING_SELECTED_ERROR = (
    "The selected tracked job is no longer available. Choose another Generation Context."
)


class DocumentGenerationContext:
    """Resolve and persist the context used by direct Documents generation."""

    def __init__(self, database: Any, user_data: Any) -> None:
        self.database = database
        self.user_data = user_data
        self.preferences = UserRepository(database.path)
        with self.preferences.transaction() as repository:
            repository.initialize_schema()

    @staticmethod
    def _preference_key(user_id: int) -> str:
        return f"{_PREFERENCE_PREFIX}{int(user_id)}"

    def selection(self, user_id: int) -> dict[str, Any]:
        with self.preferences.transaction() as repository:
            raw = repository.get_preference(self._preference_key(user_id))
        if not raw:
            return {"mode": "auto", "job_id": None}
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return {"mode": "auto", "job_id": None}
        if not isinstance(value, Mapping):
            return {"mode": "auto", "job_id": None}
        mode = str(value.get("mode") or "auto").strip().casefold()
        if mode not in _VALID_MODES:
            mode = "auto"
        job_id = int(value.get("job_id") or 0) or None
        if mode != "selected":
            job_id = None
        return {"mode": mode, "job_id": job_id}

    def set_selection(self, user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode") or "auto").strip().casefold()
        if mode not in _VALID_MODES:
            raise ValueError("Generation Context must be Automatic, Example, or Selected Job")

        job_id: int | None = None
        if mode == "selected":
            job_id = int(payload.get("job_id") or 0)
            if job_id <= 0:
                raise ValueError("Choose a tracked job for Selected Job context")
            if self.database.get_job(job_id, user_id) is None:
                raise ValueError("Selected tracked job was not found")

        value = {"mode": mode, "job_id": job_id}
        with self.preferences.transaction() as repository:
            repository.set_preference(
                self._preference_key(user_id),
                json.dumps(value, separators=(",", ":")),
            )
        return self.info(user_id)

    def _jobs(self, user_id: int) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in self.database.list_jobs(
                sort="created_at",
                order="desc",
                user_id=user_id,
            )
        ]

    @staticmethod
    def _job_summary(job: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if not job:
            return None
        return {
            "id": int(job.get("id") or 0),
            "company": str(job.get("company") or ""),
            "title": str(job.get("title") or ""),
            "created_at": str(job.get("created_at") or ""),
        }

    @staticmethod
    def _job_label(job: Mapping[str, Any] | None) -> str:
        if not job:
            return "No tracked job"
        company = str(job.get("company") or "Unknown Company").strip()
        title = str(job.get("title") or "Untitled Job").strip()
        return f"{company} · {title}"

    def info(self, user_id: int) -> dict[str, Any]:
        selection = self.selection(user_id)
        mode = str(selection["mode"])
        jobs = self._jobs(user_id)
        effective_job: Mapping[str, Any] | None = None
        error = ""

        if mode == "example":
            example = ExampleContextProvider(1).load()
            example_job = dict(example.job_ref)
            label = f"EXAMPLE DATA · {self._job_label(example_job)}"
            can_generate = True
        elif mode == "selected":
            selected_id = int(selection.get("job_id") or 0)
            effective_job = next(
                (item for item in jobs if int(item.get("id") or 0) == selected_id),
                None,
            )
            if effective_job is None:
                error = _MISSING_SELECTED_ERROR
            label = f"Selected · {self._job_label(effective_job)}"
            can_generate = effective_job is not None
        else:
            effective_job = jobs[0] if jobs else None
            if effective_job is None:
                error = _NO_JOBS_ERROR
            label = f"Automatic · {self._job_label(effective_job)}"
            can_generate = effective_job is not None

        return {
            "mode": mode,
            "job_id": selection.get("job_id"),
            "effective_job_id": (
                int(effective_job.get("id") or 0) if effective_job is not None else None
            ),
            "label": label,
            "can_generate": can_generate,
            "error": error,
            "job": self._job_summary(effective_job),
            "available_jobs": [self._job_summary(item) for item in jobs],
        }

    def resolve(self, user_id: int, *, require_job: bool) -> GenerationContext:
        selection = self.selection(user_id)
        mode = str(selection["mode"])
        if mode == "example":
            return ExampleContextProvider(1).load()

        job_id: int | None
        if mode == "selected":
            job_id = int(selection.get("job_id") or 0) or None
            if job_id is None or self.database.get_job(job_id, user_id) is None:
                if require_job:
                    raise ValueError(_MISSING_SELECTED_ERROR)
                return self._real_without_job(user_id)
        else:
            jobs = self._jobs(user_id)
            job_id = int(jobs[0]["id"]) if jobs else None
            if job_id is None:
                if require_job:
                    raise ValueError(_NO_JOBS_ERROR)
                return self._real_without_job(user_id)

        return JobContextProvider(self.database, self.user_data).load(user_id, job_id)

    def context_mapping(self, user_id: int, *, require_job: bool) -> dict[str, Any]:
        return self.resolve(user_id, require_job=require_job).as_mapping()

    def _real_without_job(self, user_id: int) -> GenerationContext:
        user_state = self.user_data.read(user_id=user_id)
        catalog = build_expression_catalog(user_state, {})
        user = dict(catalog["user"])
        first = str(user.get("first_name") or "").strip()
        last = str(user.get("last_name") or "").strip()
        user["full_name"] = str(user.get("full_name") or "").strip() or " ".join(
            part for part in (first, last) if part
        )
        today = date.today()
        return GenerationContext(
            schema_version=2,
            source="real:no-job",
            user=user,
            job_ref={},
            work_exp=tuple(dict(item) for item in catalog["work_exp"]),
            cap=dict(catalog["cap"]),
            system={
                "current_date": today.strftime("%B %d, %Y").replace(" 0", " "),
                "current_year": str(today.year),
                "greeting": "Dear Hiring Team,",
                "signoff": "Sincerely,",
            },
        )


__all__ = ["DocumentGenerationContext"]
