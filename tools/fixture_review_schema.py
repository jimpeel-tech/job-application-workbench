"""Shared schema for offline fixture/corpus review tools.

This module intentionally lives outside ``jaw.fixture_store``. Smart Capture's
production fixture store only snapshots observations; expected corpus values are
an offline/manual-review concern. Keeping this schema here prevents corpus review
helpers from becoming compatibility consumers of the production snapshot store.
"""

from __future__ import annotations

FIXTURE_FIELDS = (
    "company",
    "title",
    "job_id",
    "location",
    "remote_status",
    "employment_type",
    "pay_min",
    "pay_max",
    "currency",
    "pay_period",
    "required_skills",
    "preferred_skills",
    "required_certifications",
    "education",
    "experience_requirements",
    "responsibilities",
    "benefits",
    "application_questions",
    "source_url",
    "raw_description",
)

REVIEW_FIELDS = tuple(field for field in FIXTURE_FIELDS if field != "raw_description")

LIST_FIELDS = {
    "required_skills",
    "preferred_skills",
    "required_certifications",
    "experience_requirements",
    "responsibilities",
    "benefits",
    "application_questions",
}

__all__ = ["FIXTURE_FIELDS", "LIST_FIELDS", "REVIEW_FIELDS"]
