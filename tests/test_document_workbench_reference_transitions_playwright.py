from __future__ import annotations

import pytest

from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer

playwright = pytest.importorskip("playwright.sync_api")


def _state(page):
    return page.evaluate("window.JawWorkbenchStore.getState()")


def _select_text(locator, text: str) -> None:
    value = locator.input_value()
    start = value.index(text)
    locator.evaluate(
        "(editor, range) => { editor.focus(); editor.setSelectionRange(range.start, range.end); }",
        {"start": start, "end": start + len(text)},
    )


def _set_caret_after(locator, text: str) -> None:
    value = locator.input_value()
    position = value.index(text) + len(text)
    locator.evaluate(
        "(editor, position) => { editor.focus(); editor.setSelectionRange(position, position); }",
        position,
    )


def _select_construct(locator, symbol: str) -> None:
    value = locator.input_value()
    token = f"{{{{ {symbol} }}}}"
    start = value.index(token)
    locator.evaluate(
        "(editor, range) => { editor.focus(); editor.setSelectionRange(range.start, range.end); }",
        {"start": start, "end": start + len(token)},
    )


def _server(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    server = DashboardServer(database, port=0, user_data_path=database_path)
    server.start()
    return server


def test_pending_reference_update_cancel_validation_and_stage_flow(tmp_path):
    server = _server(tmp_path)
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
                page.locator("#wbNewDocument").click()
                page.wait_for_function(
                    """
                    () => {
                      const document = window.JawWorkbenchStore.getState().documents?.[0];
                      return Boolean(document?.sections?.[0]);
                    }
                    """
                )

                editor = page.locator('[data-wb-editor="template"]')
                playwright.expect(editor).to_be_enabled()
                state = _state(page)
                document = state["documents"][0]
                section = document["sections"][0]
                original_section_id = section["id"]
                template_id = document["template_id"]
                assert document["template"]["visibility"] == "private"
                assert document["template"]["owner_id"] == document["id"]

                # Editing a bound symbol creates a pending identity decision but
                # does not reconcile the graph in the background.
                _set_caret_after(editor, "section")
                page.keyboard.type("2")

                playwright.expect(page.locator('[data-wb-reference-update]')).to_have_text(
                    "Update Section"
                )
                playwright.expect(page.locator('[data-wb-reference-create]')).to_have_text(
                    "Create Section"
                )
                playwright.expect(page.locator('[data-wb-reference-cancel]')).to_have_text(
                    "Cancel"
                )
                page.wait_for_timeout(700)

                pending_state = _state(page)
                pending_document = pending_state["documents"][0]
                assert pending_document["template_id"] == template_id
                assert pending_document["sections"][0]["id"] == original_section_id
                assert pending_document["sections"][0]["reference_symbol"] == "section"
                assert "{{ section2 }}" in editor.input_value()

                # Inline Cancel restores the original construct without changing
                # either the private Template JID or Section JID.
                page.locator('[data-wb-reference-cancel]').click()
                playwright.expect(page.locator('[data-wb-reference-update]')).to_have_count(0)
                assert "{{ section }}" in editor.input_value()
                cancelled = _state(page)["documents"][0]
                assert cancelled["template_id"] == template_id
                assert cancelled["sections"][0]["id"] == original_section_id
                assert cancelled["sections"][0]["reference_symbol"] == "section"

                _set_caret_after(editor, "section")
                page.keyboard.type("2")
                page.locator('[data-wb-reference-update]').click()
                page.wait_for_function(
                    """
                    () => window.JawWorkbenchStore.getState().documents?.[0]
                      ?.sections?.[0]?.reference_symbol === 'section2'
                    """
                )
                updated_state = _state(page)
                updated_document = updated_state["documents"][0]
                assert updated_document["template_id"] == template_id
                assert updated_document["template"]["visibility"] == "private"
                assert updated_document["template"]["owner_id"] == updated_document["id"]
                assert updated_document["sections"][0]["id"] == original_section_id
                assert updated_document["sections"][0]["name"] == ""
                assert page.locator('[data-wb-reference-update]').count() == 0

                # Invalid intermediate source is allowed. Validation happens only
                # when Update is pressed, and a failed validation changes nothing.
                _select_text(editor, "section2")
                page.keyboard.insert_text("bad-")
                playwright.expect(page.locator('[data-wb-reference-update]')).to_have_text(
                    "Update Section"
                )
                page.wait_for_timeout(700)
                assert _state(page)["documents"][0]["sections"][0]["reference_symbol"] == "section2"

                page.locator('[data-wb-reference-update]').click()
                playwright.expect(page.locator("#wbStatus")).to_contain_text("Jinja syntax error")
                assert _state(page)["documents"][0]["sections"][0]["id"] == original_section_id
                assert _state(page)["documents"][0]["sections"][0]["reference_symbol"] == "section2"
                playwright.expect(page.locator('[data-wb-reference-update]')).to_be_visible()

                _select_text(editor, "bad-")
                page.keyboard.insert_text("section2")
                playwright.expect(page.locator('[data-wb-reference-update]')).to_have_count(0)

                # Removing the complete bound construct is different from editing
                # inside it: JAW blocks with an explicit Stage/Delete decision.
                _select_construct(editor, "section2")
                page.keyboard.press("Control+x")
                modal = page.locator(".wb-reference-modal")
                playwright.expect(modal).to_be_visible()
                playwright.expect(modal).to_contain_text("Remove reference")
                assert _state(page)["documents"][0]["sections"][0]["id"] == original_section_id

                modal.locator('[data-choice="cancel"]').click()
                playwright.expect(modal).to_have_count(0)
                assert "{{ section2 }}" in editor.input_value()
                assert _state(page)["documents"][0]["sections"][0]["id"] == original_section_id

                _select_construct(editor, "section2")
                page.keyboard.press("Delete")
                modal = page.locator(".wb-reference-modal")
                playwright.expect(modal).to_be_visible()
                playwright.expect(modal.locator('[data-choice="stage"]')).to_be_visible()
                modal.locator('[data-choice="stage"]').click()

                page.wait_for_function(
                    "id => window.JawWorkbenchStore.getState().orphans?.some(item => item.id === id)",
                    arg=original_section_id,
                )
                staged_state = _state(page)
                assert staged_state["documents"][0]["sections"] == []
                staged = next(
                    item for item in staged_state["orphans"] if item["id"] == original_section_id
                )
                assert staged["state"] == "orphaned"
                playwright.expect(
                    page.locator('[data-wb-side-pane="orphans"] .wb-side-head span')
                ).to_have_text("STAGED")
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()


def test_function_loop_can_edit_through_invalid_jinja_then_update(tmp_path):
    server = _server(tmp_path)
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
                page.locator("#wbNewDocument").click()
                page.wait_for_function(
                    """
                    () => {
                      const document = window.JawWorkbenchStore.getState().documents?.[0];
                      return Boolean(document?.sections?.[0]);
                    }
                    """
                )

                state = _state(page)
                section = state["documents"][0]["sections"][0]
                page.evaluate(
                    "id => window.JawDocumentWorkbench.openResource(id)",
                    section["id"],
                )
                editor = page.locator('[data-wb-editor="section"]')
                source = "{% for item in accomplishments() %}\n{{ item }}\n{% endfor %}"
                editor.fill(source)
                page.wait_for_function(
                    """
                    () => window.JawWorkbenchStore.getState().documents?.[0]
                      ?.sections?.[0]?.functions?.some(
                        item => item.reference_symbol === 'accomplishments'
                      )
                    """
                )
                function = _state(page)["documents"][0]["sections"][0]["functions"][0]
                original_function_id = function["id"]

                # Cancel is also available for Functions and restores the complete
                # original Jinja construct.
                _select_text(editor, "accomplishments")
                page.keyboard.insert_text("accomplish")
                playwright.expect(page.locator('[data-wb-reference-update]')).to_have_text(
                    "Update Function"
                )
                playwright.expect(page.locator('[data-wb-reference-create]')).to_have_text(
                    "Create Function"
                )
                playwright.expect(page.locator('[data-wb-reference-cancel]')).to_have_text(
                    "Cancel"
                )
                page.locator('[data-wb-reference-cancel]').click()
                assert editor.input_value() == source
                assert _state(page)["documents"][0]["sections"][0]["functions"][0]["id"] == original_function_id

                # Now deliberately edit through invalid states. The graph stays
                # bound to accomplishments until Update is explicitly accepted.
                _select_text(editor, "accomplishments")
                page.keyboard.insert_text("accomplish")
                _select_text(editor, "accomplish()")
                page.keyboard.press("Delete")
                assert "{% for item in  %}" in editor.input_value()
                playwright.expect(page.locator('[data-wb-reference-update]')).to_be_visible()

                _select_text(editor, "item in ")
                page.keyboard.press("Delete")
                assert "{% for  %}" in editor.input_value()
                playwright.expect(page.locator('[data-wb-reference-update]')).to_be_visible()
                assert _state(page)["documents"][0]["sections"][0]["functions"][0]["id"] == original_function_id
                assert _state(page)["documents"][0]["sections"][0]["functions"][0]["reference_symbol"] == "accomplishments"

                # Validation is intentionally deferred until the explicit action.
                page.locator('[data-wb-reference-update]').click()
                playwright.expect(page.locator("#wbStatus")).to_contain_text("Jinja syntax error")
                playwright.expect(page.locator('[data-wb-reference-update]')).to_be_visible()
                assert _state(page)["documents"][0]["sections"][0]["functions"][0]["id"] == original_function_id

                _set_caret_after(editor, "{% for ")
                page.keyboard.type("item in achievements()")
                assert "{% for item in achievements() %}" in editor.input_value()
                with page.expect_response(
                    lambda response: response.url.endswith("/api/workbench/rename-symbol")
                ) as update_response:
                    page.locator('[data-wb-reference-update]').click()
                assert update_response.value.ok, update_response.value.text()

                page.wait_for_function(
                    """
                    id => {
                      const fn = window.JawWorkbenchStore.getState().documents?.[0]
                        ?.sections?.[0]?.functions?.[0];
                      return fn?.id === id && fn?.reference_symbol === 'achievements';
                    }
                    """,
                    arg=original_function_id,
                )
                final_state = _state(page)
                updated = final_state["documents"][0]["sections"][0]["functions"][0]
                assert updated["id"] == original_function_id
                assert updated["reference_symbol"] == "achievements"
                assert updated["symbol"] == "achievements"
                assert updated["name"] == ""
                assert all(resource["symbol"] != "item" for resource in final_state["resources"])
                playwright.expect(page.locator('[data-wb-reference-update]')).to_have_count(0)
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()
