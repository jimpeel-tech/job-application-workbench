from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from jaw.application.document_template_repository_channels import TemplateRepository
from jaw.application.document_workbench_application import DocumentWorkbenchApplication
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase
from jaw.web.assets import static_asset_for


class _UserData:
    def __init__(self, name: str = "Regular") -> None:
        self.name = name

    def read(self, *, user_id: int | None = None):
        return {
            "active_user_id": user_id or 1,
            "active_user_name": self.name,
            "user": {"first_name": "Jane", "last_name": "Engineer"},
        }


def _archive(repo_version: str = "0.1.0") -> bytes:
    files = {
        "repo.json": json.dumps(
            {
                "repo_version": repo_version,
                "format_version": 1,
                "minimum_jaw_version": "0.1.0",
                "templates": [
                    {"id": "basic-document", "path": "templates/basic-document"}
                ],
            }
        ),
        "templates/basic-document/template.json": json.dumps(
            {
                "format_version": 1,
                "repo_version": repo_version,
                "id": "basic-document",
                "name": "Basic Document",
                "description": "Development channel example.",
                "template": {
                    "name": "Basic Document Template",
                    "file": "template.jinja",
                },
                "sections": [
                    {
                        "name": "Body",
                        "symbol": "body",
                        "file": "sections/body.jinja",
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
        ),
        "templates/basic-document/template.jinja": "{{ body }}\n",
        "templates/basic-document/sections/body.jinja": "{{ heading() }}\n",
        "templates/basic-document/functions/heading.jinja": "{{ user.full_name }}\n",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(f"jaw-templates-{repo_version}/{path}", content)
    return output.getvalue()


def _repository(
    tmp_path: Path,
    *,
    downloader,
) -> TemplateRepository:
    database = JobDatabase(tmp_path / "jaw.db")
    users = _UserData("Dev")
    service = DocumentWorkbenchService(database.document_workbench_repository, users)
    return TemplateRepository(
        database.document_workbench_repository,
        service,
        root=tmp_path / "JAWTemplateRepo",
        downloader=downloader,
    )


def test_dev_download_uses_branch_and_preserves_local(tmp_path: Path) -> None:
    requested: list[str] = []
    payload = _archive("0.2.0")

    def downloader(url: str) -> bytes:
        requested.append(url)
        return payload

    repository = _repository(tmp_path, downloader=downloader)
    local = repository.local_root / "mine"
    local.mkdir(parents=True)
    (local / "notes.txt").write_text("keep", encoding="utf-8")

    result = repository.download(channel="dev")

    assert requested == [
        "https://codeload.github.com/jimpeel-tech/jaw-templates/zip/refs/heads/dev"
    ]
    assert result["downloaded"] is True
    assert result["channel"] == "dev"
    assert result["version"] == "0.2.0"
    assert (local / "notes.txt").read_text(encoding="utf-8") == "keep"
    assert result["catalog"]["repository"]["installed_channel"] == "dev"
    assert result["catalog"]["repository"]["installed_reference"] == "dev"
    assert result["catalog"]["repository"]["installed_version"] == "0.2.0"
    assert result["catalog"]["templates"][0]["id"] == "basic-document"


def test_release_download_restores_release_channel_metadata(tmp_path: Path) -> None:
    requested: list[str] = []
    payload = _archive("0.1.0")

    def downloader(url: str) -> bytes:
        requested.append(url)
        return payload

    repository = _repository(tmp_path, downloader=downloader)
    repository.download(channel="dev")
    result = repository.download("0.1.0", channel="release")

    assert requested[-1] == (
        "https://codeload.github.com/jimpeel-tech/jaw-templates/zip/refs/tags/v0.1.0"
    )
    assert result["channel"] == "release"
    assert result["catalog"]["repository"]["installed_channel"] == "release"
    assert result["catalog"]["repository"]["installed_reference"] == "v0.1.0"


def test_workbench_application_only_allows_dev_channel_for_dev_user(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("JAW_TEMPLATE_REPO", str(tmp_path / "JAWTemplateRepo"))
    database = JobDatabase(tmp_path / "jaw.db")
    regular = _UserData("Regular")
    app = DocumentWorkbenchApplication(database, regular)
    app.template_repository._downloader = lambda _url: pytest.fail(
        "non-Dev request must be rejected before download"
    )

    assert app.repository_catalog()["repository"]["can_download_dev"] is False
    with pytest.raises(ValueError, match="only available to the Dev user"):
        app.repository_download({"channel": "dev"})

    dev = _UserData("Dev")
    dev_app = DocumentWorkbenchApplication(database, dev)
    requested: list[str] = []
    payload = _archive("0.2.0")

    def downloader(url: str) -> bytes:
        requested.append(url)
        return payload

    dev_app.template_repository._downloader = downloader
    assert dev_app.repository_catalog()["repository"]["can_download_dev"] is True
    result = dev_app.repository_download({"channel": "dev"})
    assert result["channel"] == "dev"
    assert result["catalog"]["repository"]["can_download_dev"] is True
    assert requested[0].endswith("/zip/refs/heads/dev")


def test_repository_assets_expose_dev_download_without_observers() -> None:
    javascript = static_asset_for("/document-workbench-repository.js").read().decode("utf-8")
    stylesheet = static_asset_for("/document-workbench-repository.css").read().decode("utf-8")

    assert "Download Dev" in javascript
    assert "data-wb-repository-download-dev" in javascript
    assert "channel: 'dev'" in javascript
    assert "repo.can_download_dev" in javascript
    assert "Installed Dev" in javascript
    assert "MutationObserver" not in javascript
    assert ".wb-repository-head button.dev" in stylesheet
