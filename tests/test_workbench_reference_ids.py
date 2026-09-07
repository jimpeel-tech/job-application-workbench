from __future__ import annotations

from pathlib import Path

from jaw.database import JobDatabase
from jaw.web.assets import static_asset_for


def _graph(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    template = repository.create_resource(
        1,
        "template",
        name="Template",
        symbol="template",
        visibility="private",
        content="{{ section }}\n{{ section }}\n{{ Section }}",
    )
    document = repository.create_document(
        1,
        "Document",
        template["id"],
        output_pattern="Document.pdf",
    )
    return database, repository, document


def _section(repository, document_id: str, symbol: str, content: str = ""):
    return repository.create_resource(
        1,
        "section",
        name=symbol,
        symbol=symbol,
        visibility="private",
        owner_id=document_id,
        content=content,
        settings={"content_shape": "paragraphs"},
    )


def test_workbench_reference_jids_allow_duplicate_symbols_in_one_scope(tmp_path: Path) -> None:
    _, repository, document = _graph(tmp_path)
    first = _section(repository, document["id"], "section", "First")
    second = _section(repository, document["id"], "section", "Second")

    first_ref = repository.link(
        1,
        document["id"],
        first["id"],
        edge_kind="section",
        symbol="section",
        sort_order=0,
    )
    second_ref = repository.link(
        1,
        document["id"],
        second["id"],
        edge_kind="section",
        symbol="section",
        sort_order=1,
    )

    assert first_ref["id"].startswith("ref_")
    assert second_ref["id"].startswith("ref_")
    assert first_ref["id"] != second_ref["id"]
    assert first_ref["child_id"] != second_ref["child_id"]
    assert [edge["symbol"] for edge in repository.list_edges(1, document["id"])] == [
        "section",
        "section",
    ]


def test_same_resource_can_be_referenced_more_than_once(tmp_path: Path) -> None:
    _, repository, document = _graph(tmp_path)
    shared = repository.create_resource(
        1,
        "section",
        name="Shared",
        symbol="shared",
        visibility="global",
        content="Shared content",
        settings={"content_shape": "paragraphs"},
    )

    first = repository.link(
        1,
        document["id"],
        shared["id"],
        edge_kind="section",
        symbol="shared",
        sort_order=0,
    )
    second = repository.link(
        1,
        document["id"],
        shared["id"],
        edge_kind="section",
        symbol="shared",
        sort_order=1,
    )

    assert first["id"] != second["id"]
    assert first["child_id"] == second["child_id"] == shared["id"]
    assert len(repository.list_edges(1, document["id"])) == 2


def test_reference_symbols_are_case_sensitive(tmp_path: Path) -> None:
    _, repository, document = _graph(tmp_path)
    lower = _section(repository, document["id"], "section")
    title = _section(repository, document["id"], "Section")
    upper = _section(repository, document["id"], "SECTION")

    references = [
        repository.link(
            1,
            document["id"],
            child["id"],
            edge_kind="section",
            symbol=symbol,
            sort_order=index,
        )
        for index, (child, symbol) in enumerate(
            ((lower, "section"), (title, "Section"), (upper, "SECTION"))
        )
    ]

    assert len({reference["id"] for reference in references}) == 3
    assert repository.find_edge_symbol(1, document["id"], "section")["child_id"] == lower["id"]
    assert repository.find_edge_symbol(1, document["id"], "Section")["child_id"] == title["id"]
    assert repository.find_edge_symbol(1, document["id"], "SECTION")["child_id"] == upper["id"]


def test_reference_jid_stays_stable_when_that_reference_is_updated(tmp_path: Path) -> None:
    _, repository, document = _graph(tmp_path)
    section = _section(repository, document["id"], "section")
    reference = repository.link(
        1,
        document["id"],
        section["id"],
        edge_kind="section",
        symbol="section",
        sort_order=0,
    )

    updated = repository.link(
        1,
        document["id"],
        section["id"],
        edge_kind="section",
        symbol="Section",
        sort_order=2,
        reference_id=reference["id"],
    )

    assert updated["id"] == reference["id"]
    assert updated["child_id"] == section["id"]
    assert updated["symbol"] == "Section"
    assert updated["sort_order"] == 2


def test_workbench_reference_identity_asset_binds_both_jids_to_syntax_and_explorer() -> None:
    loader = static_asset_for("/document-workbench-loader.js").read().decode("utf-8")
    javascript = static_asset_for("/document-workbench-reference-ids.js").read().decode(
        "utf-8"
    )

    assert loader.index("'/document-workbench-intelligence.js'") < loader.index(
        "'/document-workbench-reference-ids.js'"
    )
    assert loader.index("'/document-workbench-reference-ids.js'") < loader.index(
        "'/document-workbench-resources.js'"
    )
    assert "span.dataset.wbReferenceJid = binding.referenceId" in javascript
    assert "span.dataset.wbResourceJid = binding.resourceId" in javascript
    assert "data-wb-syntax-symbol" in javascript
    assert "referencesIntersecting" in javascript
    assert "function decorateExplorer()" in javascript
    assert "row.dataset.wbReferenceJid = String(section.reference_id)" in javascript
    assert "row.dataset.wbReferenceJid = String(fn.reference_id)" in javascript
