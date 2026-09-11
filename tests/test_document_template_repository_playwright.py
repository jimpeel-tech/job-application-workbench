from __future__ import annotations

import json
from pathlib import Path

import pytest

from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer

playwright = pytest.importorskip("playwright.sync_api")


def _write_local_package(root: Path) -> None:
    package = root / "local" / "repository-example"
    (package / "sections").mkdir(parents=True, exist_ok=True)
    (package / "functions").mkdir(parents=True, exist_ok=True)
    (package / "template.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "id": "repository-example",
                "name": "Repository Example",
                "description": "Clone this local Template → Section → Function example.",
                "template": {
                    "name": "Repository Example Template",
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
        encoding="utf-8",
    )
    (package / "template.jinja").write_text(
        "\\documentclass{article}\n\\begin{document}\n{{ body }}\n\\end{document}\n",
        encoding="utf-8",
    )
    (package / "sections" / "body.jinja").write_text(
        "{{ heading() }}\nBody\n", encoding="utf-8"
    )
    (package / "functions" / "heading.jinja").write_text(
        "\\section*{Repository Example}\n", encoding="utf-8"
    )


def test_template_repo_browses_local_package_and_clones_document(tmp_path, monkeypatch):
    template_root = tmp_path / "JAWTemplateRepo"
    _write_local_package(template_root)
    monkeypatch.setenv("JAW_TEMPLATE_REPO", str(template_root))

    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    server = DashboardServer(database, port=0, user_data_path=database_path)
    server.start()
    page_errors: list[str] = []
    try:
        with playwright.sync_playwright() as runtime:
            try:
                browser = runtime.chromium.launch(headless=True)
            except playwright.Error as error:
                pytest.skip(f"Playwright Chromium is not installed: {error}")
            try:
                page = browser.new_page()
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(f"{server.url}/#documents", wait_until="domcontentloaded")
                playwright.expect(page.locator(".wb-shell")).to_be_visible(timeout=15_000)
                playwright.expect(page.locator("#wbTemplateRepo")).to_have_text("+ Template Repo")

                page.locator("#wbTemplateRepo").click()
                dialog = page.locator(".wb-repository-dialog")
                playwright.expect(dialog).to_be_visible()
                playwright.expect(dialog).to_contain_text("Template Repository")
                playwright.expect(dialog).to_contain_text("Repository Example")
                playwright.expect(dialog).to_contain_text("Local")
                dialog.locator(
                    '[data-wb-repository-template="local:repository-example"]'
                ).click()
                playwright.expect(dialog).to_contain_text(
                    "Clone this local Template → Section → Function example."
                )

                with page.expect_response(
                    lambda response: response.url.endswith(
                        "/api/workbench/repository/clone"
                    )
                ) as cloned:
                    page.locator("[data-wb-repository-clone]").click()
                assert cloned.value.ok

                playwright.expect(dialog).to_be_hidden()
                playwright.expect(page.locator(".wb-doc-tab.active")).to_contain_text(
                    "Repository Example"
                )
                explorer = page.locator("#wbExplorer")
                playwright.expect(explorer).to_contain_text("Repository Example")
                sections_folder = explorer.locator(".wb-tree-row.folder", has_text="Sections")
                sections_folder.locator(".wb-chevron").click()
                playwright.expect(explorer).to_contain_text("body")

                state = page.evaluate("window.JawWorkbenchStore.getState()")
                document = next(
                    item
                    for item in state["documents"]
                    if item["name"] == "Repository Example"
                )
                assert document["template"]["visibility"] == "private"
                assert document["sections"][0]["reference_symbol"] == "body"
                assert document["sections"][0]["functions"][0]["reference_symbol"] == "heading"
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()
