from __future__ import annotations

import pytest

from jaw.application.document_workbench_application import DocumentWorkbenchApplication
from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer

playwright = pytest.importorskip("playwright.sync_api")


def _document(state: dict, document_id: str) -> dict:
    return next(item for item in state["documents"] if item["id"] == document_id)


def _click_reference(page, kind: str, symbol: str, occurrence: int = 0) -> None:
    page.evaluate(
        """([kind, symbol, occurrence]) => {
          const editor = document.querySelector(`[data-wb-editor="${kind}"]`);
          const matches = [...editor.value.matchAll(new RegExp(symbol, 'g'))];
          if (!matches[occurrence]) throw new Error(`Missing ${symbol} occurrence ${occurrence}`);
          const position = matches[occurrence].index + Math.min(1, symbol.length);
          editor.focus();
          editor.setSelectionRange(position, position);
          editor.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        }""",
        [kind, symbol, occurrence],
    )


def test_shared_global_template_inline_reference_uses_active_document_context(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    user_data = UserDataStore(database_path)
    user_id = int(user_data.read()["active_user_id"])
    app = DocumentWorkbenchApplication(database, user_data)

    first = app.create_document(
        user_id,
        {"name": "First", "template_source": "{{ body }}"},
    )
    second = app.create_document(
        user_id,
        {"name": "Second", "template_source": "{{ body }}"},
    )
    shared_template_id = first["template_id"]
    app.update_resource(
        user_id,
        {"resource_id": shared_template_id, "visibility": "global"},
    )
    shared = app.update_resource(
        user_id,
        {"resource_id": second["id"], "template_id": shared_template_id},
    )["state"]

    first_state = _document(shared, first["id"])
    second_state = _document(shared, second["id"])
    first_section = first_state["sections"][0]
    second_section = second_state["sections"][0]
    assert first_section["id"] != second_section["id"]
    assert first_section["reference_id"] != second_section["reference_id"]
    assert first_section["reference_symbol"] == second_section["reference_symbol"] == "body"

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

                page.locator(f'[data-wb-open-doc="{first["id"]}"]').click()
                editor = page.locator('[data-wb-editor="template"]')
                playwright.expect(editor).to_have_value("{{ body }}")
                page.wait_for_function(
                    "expected => window.JawWorkbenchStore.getSnapshot().activeDocumentId === expected",
                    arg=first["id"],
                )

                first_bindings = page.evaluate(
                    """() => window.JawWorkbenchReferenceIds
                      .bindingsFor('template')
                      .map(item => ({ referenceId: item.referenceId, resourceId: item.resourceId }))"""
                )
                assert first_bindings == [
                    {
                        "referenceId": first_section["reference_id"],
                        "resourceId": first_section["id"],
                    }
                ]

                _click_reference(page, "template", "body")
                page.wait_for_function(
                    "expected => window.JawWorkbenchStore.getSnapshot().activeTabs.section === expected",
                    arg=first_section["id"],
                )
                snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
                assert snapshot["activeDocumentId"] == first["id"]
                assert snapshot["selectedResourceId"] == first_section["id"]

                page.locator(f'[data-wb-open-doc="{second["id"]}"]').click()
                page.wait_for_function(
                    "expected => window.JawWorkbenchStore.getSnapshot().activeDocumentId === expected",
                    arg=second["id"],
                )
                playwright.expect(editor).to_have_value("{{ body }}")

                second_bindings = page.evaluate(
                    """() => window.JawWorkbenchReferenceIds
                      .bindingsFor('template')
                      .map(item => ({ referenceId: item.referenceId, resourceId: item.resourceId }))"""
                )
                assert second_bindings == [
                    {
                        "referenceId": second_section["reference_id"],
                        "resourceId": second_section["id"],
                    }
                ]

                _click_reference(page, "template", "body")
                page.wait_for_function(
                    "expected => window.JawWorkbenchStore.getSnapshot().activeTabs.section === expected",
                    arg=second_section["id"],
                )
                snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
                assert snapshot["activeDocumentId"] == second["id"]
                assert snapshot["selectedResourceId"] == second_section["id"]
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()
