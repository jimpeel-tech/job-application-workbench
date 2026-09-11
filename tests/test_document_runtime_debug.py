from __future__ import annotations

import json
from pathlib import Path

from jaw.application.document_workbench_render import DocumentWorkbenchRenderer
from jaw.database import JobDatabase
from jaw.documents.workbench_symbols import referenced_symbols


def _runtime(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    renderer = DocumentWorkbenchRenderer(database.document_workbench_repository)
    runtime = renderer._runtime_context(
        {
            "user": {"first_name": "Jane", "last_name": "Engineer", "email": "jane@example.com"},
            "job_ref": {"company": "Example Corp", "title": "Staff SRE"},
            "cap": {"all": [{"name": "Kubernetes", "rating": 5}], "sets": {}},
            "work_exp": [
                {
                    "company": "Example Corp",
                    "title": "Platform Engineer",
                    "highlights": [
                        "Built a platform.",
                        "Added supporting detail.",
                    ],
                    "enabled": True,
                }
            ],
            "system": {},
        }
    )
    return renderer, runtime


def test_dump_pretty_prints_runtime_values(tmp_path: Path) -> None:
    renderer, runtime = _runtime(tmp_path)

    dumped_job = runtime["dump"](runtime["job_ref"])
    assert dumped_job.startswith("{\n  ")
    assert json.loads(dumped_job) == {
        "company": "Example Corp",
        "title": "Staff SRE",
    }

    dumped_history = runtime["dump"](runtime["work_exp"])
    history = json.loads(dumped_history)
    assert history[0]["highlights"] == [
        "Built a platform.",
        "Added supporting detail.",
    ]

    rendered = renderer._render_text("{{ dump(job_ref) }}", runtime, label="debug dump")
    assert json.loads(rendered) == runtime["job_ref"]


def test_describe_reports_supported_runtime_contract(tmp_path: Path) -> None:
    _, runtime = _runtime(tmp_path)

    overview = runtime["describe"]()
    assert "JAW runtime" in overview
    assert "user: mapping" in overview
    assert "job_ref: mapping" in overview
    assert "work_exp: list[mapping] (1 records)" in overview
    assert "cap: mapping" in overview
    assert "dump(value): pretty JSON" in overview
    assert "describe([value]): runtime schema" in overview

    user_description = runtime["describe"](runtime["user"])
    assert "user\ntype: mapping\nfields:" in user_description
    assert "email: str" in user_description
    assert "full_name: str" in user_description

    work_description = runtime["describe"](runtime["work_exp"])
    assert "work_exp\ntype: list[mapping]" in work_description
    assert "highlights: list[str]" in work_description


def test_debug_helpers_and_runtime_roots_are_not_resources() -> None:
    source = """
{{ dump(job_ref) }}
{{ describe() }}
{{ describe(user) }}
{{ describe(work_exp) }}
{{ cap.sets }}
"""

    assert referenced_symbols(source) == []
