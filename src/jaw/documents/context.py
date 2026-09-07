"""Normalized context providers for stateless document generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from typing import Any, Mapping

from .expression_context import build_expression_catalog


@dataclass(frozen=True)
class GenerationContext:
    """Stable, deliberately small input boundary for document generation."""

    schema_version: int
    source: str
    user: Mapping[str, Any]
    job_ref: Mapping[str, Any]
    work_exp: tuple[Mapping[str, Any], ...]
    cap: Mapping[str, Any]
    system: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, source: str) -> "GenerationContext":
        version = int(value.get("context_schema_version", value.get("schema_version", 2)))
        work_exp = tuple(
            dict(item)
            for item in value.get("work_exp", [])
            if isinstance(item, Mapping)
        )
        cap = value.get("cap", {})
        return cls(
            schema_version=version,
            source=source,
            user=dict(value.get("user", {})),
            job_ref=dict(value.get("job_ref", {})),
            work_exp=work_exp,
            cap=dict(cap) if isinstance(cap, Mapping) else {},
            system=dict(value.get("system", {})),
        )

    # Transitional Python-only access for the base Workbench service. These are
    # deliberately absent from template_context()/as_mapping(), so the Documents
    # runtime language exposes only job_ref, work_exp, and cap.
    @property
    def job(self) -> Mapping[str, Any]:
        return self.job_ref

    @property
    def work_history(self) -> tuple[Mapping[str, Any], ...]:
        return self.work_exp

    @property
    def capabilities(self) -> Mapping[str, Any]:
        return self.cap

    def template_context(self) -> dict[str, Any]:
        """Return only the supported structured Documents runtime roots."""
        return {
            "user": dict(self.user),
            "job_ref": dict(self.job_ref),
            "work_exp": [dict(item) for item in self.work_exp],
            "cap": dict(self.cap),
            "system": dict(self.system),
        }

    def expression_catalog(self) -> dict[str, Any]:
        """Return the least-context catalog consumed by generative functions."""
        return self.template_context()

    def as_mapping(self) -> dict[str, Any]:
        return {
            "context_schema_version": self.schema_version,
            "source": self.source,
            **self.template_context(),
        }


class ExampleContextProvider:
    """Load a versioned, fictional context bundled with JAW."""

    def __init__(self, version: int = 1) -> None:
        self.version = int(version)

    def load(self) -> GenerationContext:
        resource = (
            files("jaw")
            .joinpath("resources")
            .joinpath("documents")
            .joinpath(f"example_context_v{self.version}.json")
        )
        payload = json.loads(resource.read_text(encoding="utf-8"))
        return GenerationContext.from_mapping(
            payload,
            source=f"example_context_v{self.version}",
        )


class JobContextProvider:
    """Build current generation context from the active user and tracked job."""

    def __init__(self, database: Any, user_data: Any) -> None:
        self.database = database
        self.user_data = user_data

    def load(self, user_id: int, job_id: int) -> GenerationContext:
        user_state = self.user_data.read(user_id=user_id)
        job = self.database.get_job(job_id, user_id)
        if job is None:
            raise ValueError("Tracked job was not found")
        catalog = build_expression_catalog(user_state, job)
        user = dict(catalog["user"])
        first_name = str(user.get("first_name", "")).strip()
        last_name = str(user.get("last_name", "")).strip()
        if "full_name" not in user:
            user["full_name"] = " ".join(
                part for part in (first_name, last_name) if part
            )
        current_date = date.today().strftime("%B %d, %Y").replace(" 0", " ")
        return GenerationContext(
            schema_version=2,
            source=f"job:{job_id}",
            user=user,
            job_ref=dict(catalog["job_ref"]),
            work_exp=tuple(dict(item) for item in catalog["work_exp"]),
            cap=dict(catalog["cap"]),
            system={
                "current_date": current_date,
                "current_year": str(date.today().year),
                "greeting": "Dear Hiring Team,",
                "signoff": "Sincerely,",
            },
        )


__all__ = [
    "ExampleContextProvider",
    "GenerationContext",
    "JobContextProvider",
]
