from __future__ import annotations

import pytest

from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer

playwright = pytest.importorskip("playwright.sync_api")


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def test_relationship_rows_target_exact_duplicate_global_reference(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(
        1,
        {
            "name": "Relationship Identity",
            "template_source": "{{ shared }}\n{{ shared }}",
        },
    )
    first, obsolete_second = document["sections"]

    service.update_resource(
        1,
        {"resource_id": first["id"], "visibility": "global"},
    )
    repository.unlink_reference(1, obsolete_second["reference_id"])
    repository.update_resource(1, obsolete_second["id"], state="orphaned")
    repeated = service.link_existing(
        1,
        {"parent_id": document["id"], "child_id": first["id"]},
    )

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
                page.locator(f'[data-wb-open-doc="{document["id"]}"]').click()
                page.locator(
                    f'[data-wb-expand="{document["id"]}:sections"]'
                ).click()

                page.wait_for_function(
                    """
                    resourceId => document.querySelectorAll(
                      `[data-wb-open-resource="${resourceId}"][data-wb-reference-jid]`
                    ).length === 2
                    """,
                    arg=first["id"],
                )
                page.locator(
                    f'[data-wb-open-resource="{first["id"]}"][data-wb-reference-jid]'
                ).first.click()
                page.locator('[data-wb-side-toggle="relationships"]').click()

                rows = page.locator("#wbRelationships .wb-relations > div")
                playwright.expect(rows).to_have_count(2)
                page.wait_for_function(
                    """
                    expected => [...document.querySelectorAll('#wbRelationships .wb-relations > div')]
                      .every((row, index) => row.dataset.wbReferenceJid === expected[index])
                    """,
                    arg=[first["reference_id"], repeated["reference_id"]],
                )

                assert rows.nth(0).get_attribute("data-wb-select-resource") == first["id"]
                assert rows.nth(1).get_attribute("data-wb-select-resource") == first["id"]

                rows.nth(1).click(button="right")
                menu = page.locator(".wb-context-menu")
                playwright.expect(menu).to_be_visible()
                playwright.expect(menu).to_contain_text("Rename Reference")
                menu.locator('[data-wb-context-action="rename-symbol"]').dispatch_event("click")

                rename = page.locator("[data-wb-rename-form]")
                playwright.expect(rename).to_be_visible()
                rename.locator("[data-wb-rename-input]").fill("alternate")
                rename.locator("[data-wb-rename-accept]").click()

                editor = page.locator('[data-wb-editor="template"]')
                playwright.expect(editor).to_have_value(
                    "{{ shared }}\n{{ alternate }}",
                    timeout=5000,
                )

                state = page.evaluate("window.JawWorkbenchStore.getState()")
                current = next(
                    item for item in state["documents"] if item["id"] == document["id"]
                )
                assert [item["id"] for item in current["sections"]] == [first["id"], first["id"]]
                assert [item["reference_id"] for item in current["sections"]] == [
                    first["reference_id"],
                    repeated["reference_id"],
                ]
                assert [item["reference_symbol"] for item in current["sections"]] == [
                    "shared",
                    "alternate",
                ]
                canonical = next(
                    item for item in state["resources"] if item["id"] == first["id"]
                )
                assert canonical["symbol"] == "shared"
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()
