from __future__ import annotations

import json
import shutil
from pathlib import Path

from jaw.application.document_template_repository_channels import TemplateRepository
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {
            "active_user_id": user_id or 1,
            "user": {"first_name": "Jane", "last_name": "Engineer"},
        }


def _repository(tmp_path: Path) -> TemplateRepository:
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    return TemplateRepository(
        database.document_workbench_repository,
        service,
        root=tmp_path / "JAWTemplateRepo",
        downloader=lambda _url: b"",
    )


def test_quick_reference_is_seeded_into_local_on_initialization(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    package = repository.local_root / "quick-reference"
    catalog = repository.catalog()
    quick_reference = next(
        item
        for item in catalog["templates"]
        if item["source"] == "local" and item["id"] == "quick-reference"
    )

    assert quick_reference["name"] == "Quick Reference"
    assert quick_reference["valid"] is True
    assert (package / "template.json").is_file()
    source = (package / "template.jinja").read_text(encoding="utf-8")
    assert "JAW Documents Quick Reference" in source
    assert "{% for item in work_exp %}" in source
    assert "{% for highlight in item.highlights %}" in source

    marker = json.loads(
        (repository.root / ".jaw-local-defaults.json").read_text(encoding="utf-8")
    )
    assert marker == {"version": 1}


def test_existing_local_repository_receives_quick_reference_without_losing_user_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "JAWTemplateRepo"
    user_package = root / "local" / "my-template"
    user_package.mkdir(parents=True)
    (user_package / "notes.txt").write_text("keep me", encoding="utf-8")

    repository = _repository(tmp_path)

    assert (user_package / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert (repository.local_root / "quick-reference" / "template.json").is_file()


def test_seed_marker_prevents_recreating_or_overwriting_user_local_template(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    package = repository.local_root / "quick-reference"
    template = package / "template.jinja"
    template.write_text("user changed this", encoding="utf-8")

    second = _repository(tmp_path)
    assert (second.local_root / "quick-reference" / "template.jinja").read_text(
        encoding="utf-8"
    ) == "user changed this"

    shutil.rmtree(second.local_root / "quick-reference")
    third = _repository(tmp_path)
    assert not (third.local_root / "quick-reference").exists()
