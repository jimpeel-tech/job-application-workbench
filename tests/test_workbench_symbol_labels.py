from __future__ import annotations

import json
from pathlib import Path

import pytest

from jaw.application.document_template_repository import TemplateRepository
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase
from jaw.web.assets import static_asset_for


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def test_section_and_function_resources_do_not_store_separate_names(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository

    template = repository.create_resource(
        1,
        "template",
        name="Resume",
        symbol="template",
        content="{{ summary }}",
    )
    document = repository.create_document(
        1,
        "Resume",
        template["id"],
        output_pattern="Resume.pdf",
    )
    section = repository.create_resource(
        1,
        "section",
        name="Friendly Summary",
        symbol="summary",
        owner_id=document["id"],
    )
    function = repository.create_resource(
        1,
        "function",
        name="Friendly Helper",
        symbol="helper",
        owner_id=section["id"],
    )

    assert section["name"] == ""
    assert section["symbol"] == "summary"
    assert function["name"] == ""
    assert function["symbol"] == "helper"

    with pytest.raises(ValueError, match="named by their symbol"):
        repository.update_resource(1, section["id"], name="Another Summary")
    with pytest.raises(ValueError, match="named by their symbol"):
        repository.update_resource(1, function["id"], name="Another Helper")


def test_repository_initialization_clears_obsolete_section_and_function_names(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jaw.db"
    database = JobDatabase(path)
    repository = database.document_workbench_repository
    section = repository.create_resource(1, "section", symbol="summary")
    function = repository.create_resource(1, "function", symbol="helper")

    with database.connect() as connection:
        connection.execute(
            "UPDATE document_workbench_resources SET name='Old Section Name' WHERE id=?",
            (section["id"],),
        )
        connection.execute(
            "UPDATE document_workbench_resources SET name='Old Function Name' WHERE id=?",
            (function["id"],),
        )

    restarted = JobDatabase(path).document_workbench_repository
    assert restarted.require_resource(1, section["id"])["name"] == ""
    assert restarted.require_resource(1, function["id"])["name"] == ""


def test_template_packages_use_symbol_as_the_child_resource_label(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    packages = TemplateRepository(
        database.document_workbench_repository,
        service,
        root=tmp_path / "templates",
    )
    package = packages.local_root / "symbol-only"
    (package / "sections").mkdir(parents=True)
    (package / "functions").mkdir(parents=True)
    (package / "template.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "id": "symbol-only",
                "name": "Symbol Only",
                "template": {"name": "Symbol Only Template", "file": "template.jinja"},
                "sections": [
                    {
                        "symbol": "body",
                        "file": "sections/body.jinja",
                        "functions": [
                            {"symbol": "heading", "file": "functions/heading.jinja"}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (package / "template.jinja").write_text("{{ body }}", encoding="utf-8")
    (package / "sections" / "body.jinja").write_text("{{ heading }}", encoding="utf-8")
    (package / "functions" / "heading.jinja").write_text("Heading", encoding="utf-8")

    cloned = packages.clone(1, template_id="symbol-only", source="local")
    document = next(
        item
        for item in cloned["state"]["documents"]
        if item["id"] == cloned["document_id"]
    )
    section = document["sections"][0]
    function = section["functions"][0]

    assert section["reference_symbol"] == "body"
    assert section["symbol"] == "body"
    assert section["name"] == ""
    assert function["reference_symbol"] == "heading"
    assert function["symbol"] == "heading"
    assert function["name"] == ""


def test_workbench_ui_presents_section_and_function_symbols_not_names() -> None:
    javascript = static_asset_for("/document-workbench.js").read().decode("utf-8")
    resources = static_asset_for("/document-workbench-resources.js").read().decode("utf-8")

    assert "resource.kind === 'section' || resource.kind === 'function'" in javascript
    assert "resource.reference_symbol || resource.symbol || resource.kind" in javascript
    assert "const namedResource = resource.kind === 'document' || resource.kind === 'template'" in javascript
    assert "<span>JID</span>" in javascript
    assert "JawWorkbenchReferenceIds?.referenceAt" in javascript
    assert "lower(item.symbol) === lower(word)" not in javascript

    assert "function resourceTitle(resource, edge = null)" in resources
    assert "edge?.symbol || resource.symbol || resource.kind" in resources
    assert "Rename Symbol" in resources
