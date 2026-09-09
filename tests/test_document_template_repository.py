from __future__ import annotations

import io
import json
import urllib.request
import zipfile
from pathlib import Path

import pytest

from jaw.application.document_template_repository import TemplateRepository
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {
            "active_user_id": user_id or 1,
            "user": {"first_name": "Jane", "last_name": "Engineer"},
        }


def _write_package(
    root: Path,
    *,
    package_id: str = "repository-example",
    name: str = "Repository Example",
    repo_version: str = "",
) -> Path:
    package = root / package_id
    (package / "sections").mkdir(parents=True, exist_ok=True)
    (package / "functions").mkdir(parents=True, exist_ok=True)
    manifest = {
        "format_version": 1,
        "id": package_id,
        "name": name,
        "description": "Small Template → Section → Function repository example.",
        "output_pattern": "{{ user.full_name }} - Repository Example.pdf",
        "template": {
            "name": "Repository Example Template",
            "file": "template.jinja",
        },
        "sections": [
            {
                "name": "Body",
                "symbol": "body",
                "file": "sections/body.jinja",
                "settings": {"content_shape": "paragraphs"},
                "functions": [
                    {
                        "name": "Heading",
                        "symbol": "heading",
                        "file": "functions/heading.jinja",
                    }
                ],
            }
        ],
    }
    if repo_version:
        manifest["repo_version"] = repo_version
    (package / "template.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (package / "template.jinja").write_text(
        "\\documentclass[10pt,letterpaper]{article}\n"
        "\\begin{document}\n"
        "{{ body }}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    (package / "sections" / "body.jinja").write_text(
        "{{ heading() }}\n\n{{ user.full_name }}\n",
        encoding="utf-8",
    )
    (package / "functions" / "heading.jinja").write_text(
        "\\section*{Template Repository Example}\n",
        encoding="utf-8",
    )
    return package


def _repository(tmp_path: Path, *, downloader=None) -> tuple[JobDatabase, TemplateRepository]:
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    repository = TemplateRepository(
        database.document_workbench_repository,
        service,
        root=tmp_path / "JAWTemplateRepo",
        downloader=downloader,
    )
    return database, repository


def _zip_repository(
    tmp_path: Path,
    *,
    version: str = "0.1.0",
    template_api: int = 1,
) -> bytes:
    source = tmp_path / "download-source" / f"jaw-templates-{version}"
    package = _write_package(
        source / "templates",
        repo_version=version,
    )
    (source / "repo.json").write_text(
        json.dumps(
            {
                "repo_version": version,
                "format_version": 1,
                "template_api": template_api,
                "minimum_jaw_version": "0.1.0",
                "templates": [
                    {"id": "repository-example", "path": "templates/repository-example"}
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    assert package.is_dir()

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in source.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(source.parent))
    return output.getvalue()


def _release_registry(*releases: dict) -> bytes:
    return json.dumps(
        {
            "registry_format": 1,
            "releases": list(releases),
        }
    ).encode("utf-8")


def test_local_package_catalog_and_clone_create_new_private_graph(tmp_path: Path) -> None:
    database, repository = _repository(tmp_path)
    _write_package(repository.local_root)

    catalog = repository.catalog()
    assert [(item["id"], item["source"], item["valid"]) for item in catalog["templates"]] == [
        ("repository-example", "local", True)
    ]

    first = repository.clone(1, template_id="repository-example", source="local")
    document = next(
        item for item in first["state"]["documents"] if item["id"] == first["document_id"]
    )
    section = document["sections"][0]
    function = section["functions"][0]

    assert document["name"] == "Repository Example"
    assert document["template"]["id"] == first["template_id"]
    assert document["template"]["visibility"] == "private"
    assert document["template"]["owner_id"] == document["id"]
    assert "{{ body }}" in document["template"]["content"]
    assert section["reference_symbol"] == "body"
    assert section["visibility"] == "private"
    assert section["owner_id"] == document["id"]
    assert "{{ heading() }}" in section["content"]
    assert function["reference_symbol"] == "heading"
    assert function["visibility"] == "private"
    assert function["owner_id"] == section["id"]
    assert function["content"] == "\\section*{Template Repository Example}\n"
    assert document["id"].startswith("doc_")
    assert document["template"]["id"].startswith("tpl_")
    assert section["id"].startswith("sec_")
    assert function["id"].startswith("fn_")

    first_ids = {
        document["id"], document["template"]["id"], section["id"], function["id"]
    }
    second = repository.clone(1, template_id="repository-example", source="local")
    second_document = next(
        item for item in second["state"]["documents"] if item["id"] == second["document_id"]
    )
    second_section = second_document["sections"][0]
    second_function = second_section["functions"][0]
    second_ids = {
        second_document["id"],
        second_document["template"]["id"],
        second_section["id"],
        second_function["id"],
    }

    assert second_document["name"] == "Repository Example 2"
    assert first_ids.isdisjoint(second_ids)
    assert database.document_workbench_repository.list_resources(1, visibility="global") == []


def test_local_package_can_bind_duplicate_child_symbols_by_occurrence(tmp_path: Path) -> None:
    database, repository = _repository(tmp_path)
    package = _write_package(
        repository.local_root,
        package_id="duplicate-sections",
        name="Duplicate Sections",
    )
    manifest_path = package / "template.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["template"]["name"] = "Duplicate Sections Template"
    manifest["sections"] = [
        {
            "name": "Body One",
            "symbol": "body",
            "file": "sections/body-one.jinja",
            "functions": [],
        },
        {
            "name": "Body Two",
            "symbol": "body",
            "file": "sections/body-two.jinja",
            "functions": [],
        },
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (package / "template.jinja").write_text("{{ body }}\n{{ body }}\n", encoding="utf-8")
    (package / "sections" / "body-one.jinja").write_text("First body\n", encoding="utf-8")
    (package / "sections" / "body-two.jinja").write_text("Second body\n", encoding="utf-8")

    catalog = repository.catalog()
    item = next(value for value in catalog["templates"] if value["id"] == "duplicate-sections")
    assert item["valid"] is True

    cloned = repository.clone(1, template_id="duplicate-sections", source="local")
    document = next(
        value
        for value in cloned["state"]["documents"]
        if value["id"] == cloned["document_id"]
    )
    assert [section["reference_symbol"] for section in document["sections"]] == [
        "body",
        "body",
    ]
    assert document["sections"][0]["id"] != document["sections"][1]["id"]

    edges = database.document_workbench_repository.list_edges(1, document["id"])
    assert [edge["symbol"] for edge in edges] == ["body", "body"]
    assert edges[0]["id"] != edges[1]["id"]


def test_invalid_local_package_is_visible_but_cannot_clone(tmp_path: Path) -> None:
    _, repository = _repository(tmp_path)
    package = _write_package(repository.local_root)
    (package / "template.jinja").write_text(
        "\\begin{document}\n{{ missing_section }}\n\\end{document}\n",
        encoding="utf-8",
    )

    catalog = repository.catalog()
    assert len(catalog["templates"]) == 1
    assert catalog["templates"][0]["valid"] is False
    assert "references do not match" in catalog["templates"][0]["error"]

    with pytest.raises(ValueError, match="references do not match"):
        repository.clone(1, template_id="repository-example", source="local")


def test_download_replaces_examples_without_touching_local_templates(tmp_path: Path) -> None:
    archive = _zip_repository(tmp_path)
    registry = _release_registry(
        {
            "version": "0.1.0",
            "ref": "v0.1.0",
            "template_api": 1,
            "package_format": 1,
            "jaw": ">=0.1.0,<0.2.0",
        }
    )
    requested_urls: list[str] = []

    def downloader(url: str) -> bytes:
        requested_urls.append(url)
        if url.endswith("/releases.json"):
            return registry
        return archive

    _, repository = _repository(tmp_path, downloader=downloader)
    _write_package(repository.local_root, package_id="my-local", name="My Local")
    repository.examples_root.mkdir(parents=True, exist_ok=True)
    stale = repository.examples_root / "stale.txt"
    stale.write_text("old", encoding="utf-8")

    result = repository.download("0.1.0")

    assert requested_urls == [
        "https://raw.githubusercontent.com/jimpeel-tech/jaw-templates/main/releases.json",
        "https://codeload.github.com/jimpeel-tech/jaw-templates/zip/refs/tags/v0.1.0",
    ]
    assert result["downloaded"] is True
    assert result["version"] == "0.1.0"
    assert result["reference"] == "v0.1.0"
    assert result["template_api"] == 1
    assert result["catalog"]["repository"]["release_resolution"] == "compatible"
    assert not stale.exists()
    assert (repository.local_root / "my-local" / "template.json").is_file()
    assert (repository.examples_root / "repo.json").is_file()
    assert {
        (item["id"], item["source"], item["valid"])
        for item in result["catalog"]["templates"]
    } == {
        ("repository-example", "example", True),
        ("my-local", "local", True),
    }


def test_repository_http_catalog_and_clone_routes(tmp_path: Path, monkeypatch) -> None:
    template_root = tmp_path / "JAWTemplateRepo"
    _write_package(template_root / "local")
    monkeypatch.setenv("JAW_TEMPLATE_REPO", str(template_root))

    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    store = UserDataStore(database_path)
    user_id = int(store.read()["active_user_id"])
    server = DashboardServer(database, port=0, user_data_path=database_path)
    server.start()
    try:
        with urllib.request.urlopen(f"{server.url}/api/workbench/repository") as response:
            catalog = json.loads(response.read())
        assert catalog["local_path"] == str((template_root / "local").resolve())
        assert catalog["repository"]["release_resolution"] == "compatible"
        assert catalog["templates"][0]["id"] == "repository-example"

        request = urllib.request.Request(
            f"{server.url}/api/workbench/repository/clone",
            data=json.dumps(
                {"template_id": "repository-example", "source": "local"}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            cloned = json.loads(response.read())
        assert cloned["document_id"].startswith("doc_")

        with urllib.request.urlopen(f"{server.url}/api/workbench/state") as response:
            state = json.loads(response.read())["workbench"]
        document = next(item for item in state["documents"] if item["id"] == cloned["document_id"])
        assert document["name"] == "Repository Example"
        assert document["sections"][0]["reference_symbol"] == "body"
        assert document["sections"][0]["functions"][0]["reference_symbol"] == "heading"
        assert document["id"] == cloned["document_id"]
        assert user_id > 0
    finally:
        server.stop()
