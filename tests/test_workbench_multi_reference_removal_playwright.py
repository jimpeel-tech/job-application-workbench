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


@pytest.mark.parametrize("choice", ["stage", "delete"])
def test_multi_select_removal_applies_to_every_selected_reference(tmp_path, choice):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    source = (
        "\\begin{document}\n"
        "{{ alpha }}\n"
        "{{ beta }}\n"
        "{{ gamma }}\n"
        "\\end{document}"
    )
    selection_start = source.index("{{ alpha }}")
    selection_end = source.index("{{ gamma }}") + len("{{ gamma }}")
    expected_source = source[:selection_start] + source[selection_end:]
    document = service.create_document(
        1,
        {
            "name": f"Multi Reference {choice.title()}",
            "template_source": source,
        },
    )
    original_sections = document["sections"]
    original_ids = [item["id"] for item in original_sections]
    original_reference_ids = [item["reference_id"] for item in original_sections]

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
                playwright.expect(editor).to_have_value(source)
                editor.evaluate(
                    """
                    (editor, range) => {
                      editor.focus();
                      editor.setSelectionRange(range.start, range.end);
                    }
                    """,
                    {"start": selection_start, "end": selection_end},
                )
                page.keyboard.press("Delete")

                modal = page.locator(".wb-reference-modal")
                playwright.expect(modal).to_be_visible()
                playwright.expect(modal).to_contain_text("3")
                playwright.expect(modal).to_contain_text("Section references")
                playwright.expect(modal.locator(f'[data-choice="{choice}"]')).to_be_visible(
                    timeout=5000
                )
                modal.locator(f'[data-choice="{choice}"]').click()

                page.wait_for_function(
                    """
                    documentId => window.JawWorkbenchStore.getState().documents
                      ?.find(item => item.id === documentId)?.sections?.length === 0
                    """,
                    arg=document["id"],
                )
                playwright.expect(editor).to_have_value(expected_source)

                state = page.evaluate("window.JawWorkbenchStore.getState()")
                current = _document(state, document["id"])
                assert current["sections"] == []
                remaining_reference_ids = {
                    edge["id"]
                    for relation in state["relationships"].values()
                    for direction in ("inbound", "outbound")
                    for edge in relation.get(direction, [])
                }
                assert not set(original_reference_ids) & remaining_reference_ids

                resources = {item["id"]: item for item in state["resources"]}
                if choice == "stage":
                    assert all(resources[item_id]["state"] == "orphaned" for item_id in original_ids)
                    orphan_ids = {item["id"] for item in state.get("orphans", [])}
                    assert set(original_ids) <= orphan_ids
                else:
                    assert not set(original_ids) & set(resources)

                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()


def test_multi_select_delete_does_not_restore_dirty_buffer_or_create_new_jids(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    original_source = "\\begin{document}\n{{ keep }}\n\\end{document}"
    dirty_source = (
        "\\begin{document}\n"
        "{{ keep }}\n"
        "{{ section }}\n"
        "{{ section }}\n"
        "\\end{document}"
    )
    selection_start = dirty_source.index("{{ section }}")
    selection_end = dirty_source.rindex("{{ section }}") + len("{{ section }}")
    expected_source = dirty_source[:selection_start] + dirty_source[selection_end:]
    document = service.create_document(
        1,
        {
            "name": "Dirty Multi Reference Delete",
            "template_source": original_source,
        },
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

                editor = page.locator('[data-wb-editor="template"]')
                playwright.expect(editor).to_have_value(original_source)
                editor.evaluate(
                    """
                    (editor, source) => {
                      editor.value = source;
                      editor.focus();
                      editor.setSelectionRange(source.length, source.length);
                      editor.dispatchEvent(new InputEvent('input', {
                        bubbles: true,
                        inputType: 'insertText',
                        data: null,
                      }));
                    }
                    """,
                    dirty_source,
                )

                page.wait_for_function(
                    """
                    documentId => window.JawWorkbenchStore.getState().documents
                      ?.find(item => item.id === documentId)?.sections?.length === 3
                    """,
                    arg=document["id"],
                )
                playwright.expect(editor).to_have_value(dirty_source)
                dirty_state = page.evaluate("window.JawWorkbenchStore.getState()")
                dirty_document = _document(dirty_state, document["id"])
                removed = [
                    item
                    for item in dirty_document["sections"]
                    if item["reference_symbol"] == "section"
                ]
                assert len(removed) == 2
                removed_resource_ids = {item["id"] for item in removed}
                removed_reference_ids = {item["reference_id"] for item in removed}

                editor.evaluate(
                    """
                    (editor, range) => {
                      editor.focus();
                      editor.setSelectionRange(range.start, range.end);
                    }
                    """,
                    {"start": selection_start, "end": selection_end},
                )
                page.keyboard.press("Delete")

                modal = page.locator(".wb-reference-modal")
                playwright.expect(modal).to_be_visible()
                playwright.expect(modal).to_contain_text("2 Section references")
                playwright.expect(modal.locator('[data-choice="delete"]')).to_be_visible(
                    timeout=5000
                )
                modal.locator('[data-choice="delete"]').click()

                page.wait_for_function(
                    """
                    documentId => window.JawWorkbenchStore.getState().documents
                      ?.find(item => item.id === documentId)?.sections?.length === 1
                    """,
                    arg=document["id"],
                )
                playwright.expect(editor).to_have_value(expected_source)

                # Let the post-resolution recovery checkpoint run. The deleted
                # constructs must not reappear and replacement JIDs must not be made.
                page.wait_for_timeout(1000)
                playwright.expect(editor).to_have_value(expected_source)
                state = page.evaluate("window.JawWorkbenchStore.getState()")
                current = _document(state, document["id"])
                assert len(current["sections"]) == 1
                assert current["sections"][0]["reference_symbol"] == "keep"
                assert not removed_resource_ids & {item["id"] for item in state["resources"]}
                remaining_reference_ids = {
                    edge["id"]
                    for relation in state["relationships"].values()
                    for direction in ("inbound", "outbound")
                    for edge in relation.get(direction, [])
                }
                assert not removed_reference_ids & remaining_reference_ids
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()
