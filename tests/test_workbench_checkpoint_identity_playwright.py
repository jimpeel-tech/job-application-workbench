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


def _document(state: dict, document_id: str) -> dict:
    return next(item for item in state["documents"] if item["id"] == document_id)


def _bindings(page) -> list[dict[str, str]]:
    return page.evaluate(
        """() => window.JawWorkbenchReferenceIds
          .bindingsFor('template')
          .map(item => ({ referenceId: item.referenceId, resourceId: item.resourceId }))"""
    )


def test_incomplete_checkpoint_does_not_shift_duplicate_reference_identity(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    document = service.create_document(
        1,
        {
            "name": "Incremental Duplicate Insertion",
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
                assert _bindings(page) == [
                    {
                        "referenceId": original_first["reference_id"],
                        "resourceId": original_first["id"],
                    },
                    {
                        "referenceId": original_second["reference_id"],
                        "resourceId": original_second["id"],
                    },
                ]

                editor.evaluate(
                    "editor => { editor.focus(); editor.setSelectionRange(0, 0); }"
                )
                page.keyboard.type("{{ body", delay=30)

                # Let the normal 450ms recovery checkpoint complete while the
                # newly inserted Jinja expression is still incomplete. This is
                # the manual-edit path that previously discarded the shifted
                # occurrence bindings and reassigned the old JIDs by position.
                playwright.expect(page.locator("#wbStatus")).to_have_text(
                    "Recovered",
                    timeout=5000,
                )

                page.keyboard.type(" }}\n", delay=30)
                page.wait_for_function(
                    """
                    documentId => window.JawWorkbenchStore.getState().documents
                      ?.find(item => item.id === documentId)?.sections?.length === 3
                    """,
                    arg=document["id"],
                )

                state = page.evaluate("window.JawWorkbenchStore.getState()")
                current = _document(state, document["id"])
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

                expected_bindings = [
                    {
                        "referenceId": inserted["reference_id"],
                        "resourceId": inserted["id"],
                    },
                    {
                        "referenceId": original_first["reference_id"],
                        "resourceId": original_first["id"],
                    },
                    {
                        "referenceId": original_second["reference_id"],
                        "resourceId": original_second["id"],
                    },
                ]
                assert _bindings(page) == expected_bindings

                # Reload from persisted checkpoint state to prove the reference
                # order is correct in the graph, not only in the browser cache.
                page.reload(wait_until="domcontentloaded")
                playwright.expect(page.locator(".wb-shell")).to_be_visible(timeout=15_000)
                page.locator(f'[data-wb-open-doc="{document["id"]}"]').click()
                playwright.expect(page.locator('[data-wb-editor="template"]')).to_have_value(
                    "{{ body }}\n{{ body }}\n{{ body }}"
                )
                assert _bindings(page) == expected_bindings
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()
