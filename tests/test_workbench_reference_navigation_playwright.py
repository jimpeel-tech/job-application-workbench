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


def _open_document(page, document_id: str):
    page.goto(f"{page.url.split('#')[0]}#documents", wait_until="domcontentloaded")
    playwright.expect(page.locator(".wb-shell")).to_be_visible(timeout=15_000)
    page.locator(f'[data-wb-open-doc="{document_id}"]').click()
    return page.locator('[data-wb-editor="template"]')


def test_duplicate_template_symbols_navigate_to_the_exact_resource_jid(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    document = service.create_document(
        1,
        {
            "name": "Duplicate Navigation",
            "template_source": "{{ body }}\n{{ body }}",
        },
    )
    first, second = document["sections"]
    assert first["id"] != second["id"]
    assert first["reference_id"] != second["reference_id"]

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

                editor = page.locator('[data-wb-editor="template"]')
                playwright.expect(editor).to_have_value("{{ body }}\n{{ body }}")

                def click_reference(index: int) -> None:
                    page.evaluate(
                        """([index]) => {
                          const editor = document.querySelector('[data-wb-editor="template"]');
                          const matches = [...editor.value.matchAll(/body/g)];
                          const position = matches[index].index + 1;
                          editor.focus();
                          editor.setSelectionRange(position, position);
                          editor.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                        }""",
                        [index],
                    )

                click_reference(0)
                page.wait_for_function(
                    "expected => window.JawWorkbenchStore.getSnapshot().activeTabs.section === expected",
                    arg=first["id"],
                )

                click_reference(1)
                page.wait_for_function(
                    "expected => window.JawWorkbenchStore.getSnapshot().activeTabs.section === expected",
                    arg=second["id"],
                )

                bindings = page.evaluate(
                    """() => window.JawWorkbenchReferenceIds
                      .bindingsFor('template')
                      .map(item => ({ referenceId: item.referenceId, resourceId: item.resourceId }))"""
                )
                assert bindings == [
                    {"referenceId": first["reference_id"], "resourceId": first["id"]},
                    {"referenceId": second["reference_id"], "resourceId": second["id"]},
                ]
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()


def test_duplicate_function_symbols_navigate_to_the_exact_resource_jid(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    document = service.create_document(1, {"name": "Duplicate Function Navigation"})
    section = document["sections"][0]
    service.save(
        1,
        {"resource_id": section["id"], "content": "{{ helper }}\n{{ helper }}"},
    )
    current = next(
        item for item in service.state(1)["documents"] if item["id"] == document["id"]
    )
    first, second = current["sections"][0]["functions"]
    assert first["id"] != second["id"]
    assert first["reference_id"] != second["reference_id"]

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
                page.evaluate(
                    "id => window.JawDocumentWorkbench.openResource(id)",
                    section["id"],
                )

                editor = page.locator('[data-wb-editor="section"]')
                playwright.expect(editor).to_have_value("{{ helper }}\n{{ helper }}")

                def click_reference(index: int) -> None:
                    page.evaluate(
                        """([index]) => {
                          const editor = document.querySelector('[data-wb-editor="section"]');
                          const matches = [...editor.value.matchAll(/helper/g)];
                          const position = matches[index].index + 1;
                          editor.focus();
                          editor.setSelectionRange(position, position);
                          editor.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                        }""",
                        [index],
                    )

                click_reference(0)
                page.wait_for_function(
                    "expected => window.JawWorkbenchStore.getSnapshot().activeTabs.function === expected",
                    arg=first["id"],
                )

                click_reference(1)
                page.wait_for_function(
                    "expected => window.JawWorkbenchStore.getSnapshot().activeTabs.function === expected",
                    arg=second["id"],
                )

                bindings = page.evaluate(
                    """() => window.JawWorkbenchReferenceIds
                      .bindingsFor('section')
                      .map(item => ({ referenceId: item.referenceId, resourceId: item.resourceId }))"""
                )
                assert bindings == [
                    {"referenceId": first["reference_id"], "resourceId": first["id"]},
                    {"referenceId": second["reference_id"], "resourceId": second["id"]},
                ]
                snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
                assert snapshot["activeDocumentId"] == document["id"]
                assert snapshot["activeTabs"]["section"] == section["id"]
                assert snapshot["activeTabs"]["function"] == second["id"]
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()


def test_inserting_identical_reference_before_duplicates_preserves_existing_jids(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    document = service.create_document(
        1,
        {
            "name": "Duplicate Insertion",
            "template_source": "{{ body }}\n{{ body }}",
        },
    )
    original_first, original_second = document["sections"]

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

                editor = page.locator('[data-wb-editor="template"]')
                playwright.expect(editor).to_have_value("{{ body }}\n{{ body }}")
                initial_bindings = page.evaluate(
                    """() => window.JawWorkbenchReferenceIds
                      .bindingsFor('template')
                      .map(item => item.referenceId)"""
                )
                assert initial_bindings == [
                    original_first["reference_id"],
                    original_second["reference_id"],
                ]

                editor.evaluate(
                    "editor => { editor.focus(); editor.setSelectionRange(0, 0); }"
                )
                page.keyboard.insert_text("{{ body }}\n")

                page.wait_for_function(
                    """
                    documentId => window.JawWorkbenchStore.getState().documents
                      ?.find(item => item.id === documentId)?.sections?.length === 3
                    """,
                    arg=document["id"],
                )

                state = page.evaluate("window.JawWorkbenchStore.getState()")
                current = next(
                    item for item in state["documents"] if item["id"] == document["id"]
                )
                inserted, first, second = current["sections"]

                assert inserted["id"] not in {original_first["id"], original_second["id"]}
                assert inserted["reference_id"] not in {
                    original_first["reference_id"],
                    original_second["reference_id"],
                }
                assert first["id"] == original_first["id"]
                assert first["reference_id"] == original_first["reference_id"]
                assert second["id"] == original_second["id"]
                assert second["reference_id"] == original_second["reference_id"]

                bindings = page.evaluate(
                    """() => window.JawWorkbenchReferenceIds
                      .bindingsFor('template')
                      .map(item => ({ referenceId: item.referenceId, resourceId: item.resourceId }))"""
                )
                assert bindings == [
                    {"referenceId": inserted["reference_id"], "resourceId": inserted["id"]},
                    {"referenceId": original_first["reference_id"], "resourceId": original_first["id"]},
                    {"referenceId": original_second["reference_id"], "resourceId": original_second["id"]},
                ]
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()
