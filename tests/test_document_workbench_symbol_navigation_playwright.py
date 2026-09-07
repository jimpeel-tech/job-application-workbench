from __future__ import annotations

import pytest

from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer

playwright = pytest.importorskip("playwright.sync_api")


def _click_character(page, locator, index: int) -> None:
    point = locator.evaluate(
        r"""
        (editor, index) => {
          const style = getComputedStyle(editor);
          const canvas = document.createElement('canvas');
          const context = canvas.getContext('2d');
          context.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
          const lineStart = editor.value.lastIndexOf('\n', Math.max(0, index - 1)) + 1;
          const lineNumber = editor.value.slice(0, lineStart).split('\n').length - 1;
          const prefix = editor.value.slice(lineStart, index);
          const character = editor.value[index] || 'M';
          const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.5;
          return {
            x: parseFloat(style.paddingLeft) + context.measureText(prefix).width
              + context.measureText(character).width / 2 - editor.scrollLeft,
            y: parseFloat(style.paddingTop) + lineNumber * lineHeight
              + lineHeight / 2 - editor.scrollTop,
          };
        }
        """,
        index,
    )
    box = locator.bounding_box()
    assert box is not None
    page.mouse.click(box["x"] + point["x"], box["y"] + point["y"])


def _selection(locator) -> dict:
    return locator.evaluate(
        "editor => ({start: editor.selectionStart, end: editor.selectionEnd, direction: editor.selectionDirection})"
    )


def _assert_caret_in_word(locator, word: str) -> None:
    value = locator.input_value()
    word_start = value.index(word)
    word_end = word_start + len(word)
    selection = _selection(locator)
    assert selection["start"] == selection["end"]
    assert word_start <= selection["start"] <= word_end


def _assert_selected(page, resource: dict) -> None:
    snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
    assert snapshot["selectedResourceId"] == resource["id"]
    if resource["kind"] in {"document", "template"}:
        playwright.expect(page.locator("#wbInspectorName")).to_have_value(resource["name"])
    else:
        playwright.expect(page.locator("#wbInspector")).to_contain_text(resource["symbol"])
    playwright.expect(page.locator("#wbMetadata")).to_contain_text(resource["id"])


def _server(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    server = DashboardServer(database, port=0, user_data_path=database_path)
    server.start()
    return server


def test_duplicate_visible_symbols_navigate_to_their_exact_reference_jids(tmp_path):
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
                      const state = window.JawWorkbenchStore.getState();
                      const snapshot = window.JawWorkbenchStore.getSnapshot();
                      const document = state.documents?.[0];
                      const editor = document?.id
                        ? document.querySelector?.('[data-wb-editor="template"]')
                        : null;
                      return state.documents?.length === 1
                        && document?.id
                        && snapshot.activeDocumentId === document.id
                        && window.document.querySelector('[data-wb-editor="template"]')
                          ?.value.includes('{{ section }}');
                    }
                    """
                )

                editor = page.locator('[data-wb-editor="template"]')
                playwright.expect(editor).to_be_enabled()
                editor.evaluate(
                    "editor => { editor.focus(); editor.setSelectionRange(editor.value.length, editor.value.length); }"
                )
                page.keyboard.insert_text("\n{{ section }}")
                page.wait_for_function(
                    """
                    () => window.JawWorkbenchStore.getState().documents?.[0]
                      ?.sections?.length === 2
                    """
                )

                state = page.evaluate("window.JawWorkbenchStore.getState()")
                document = state["documents"][0]
                first, second = document["sections"]
                assert first["id"] != second["id"]
                assert first["reference_symbol"] == second["reference_symbol"] == "section"

                spans = page.locator(
                    '[data-wb-pane="template"] .wb-editor-highlight [data-wb-reference-jid]'
                )
                playwright.expect(spans).to_have_count(2)
                reference_ids = spans.evaluate_all(
                    "nodes => nodes.map(node => node.dataset.wbReferenceJid)"
                )
                assert reference_ids[0] != reference_ids[1]

                source = editor.input_value()
                first_index = source.index("section") + 2
                second_index = source.index("section", first_index + 1) + 2

                _click_character(page, editor, first_index)
                snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
                assert snapshot["activeTabs"]["section"] == first["id"]
                _assert_selected(page, first)

                _click_character(page, editor, second_index)
                snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
                assert snapshot["activeTabs"]["section"] == second["id"]
                _assert_selected(page, second)
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()


def test_clicking_editors_selects_owner_or_bound_child_and_keeps_caret(tmp_path):
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

                # Two Documents prove each owns its own private Template and that
                # inspecting the active Template never changes Document context.
                page.locator("#wbNewDocument").click()
                page.wait_for_function(
                    "() => window.JawWorkbenchStore.getState().documents?.length === 1"
                )
                page.locator("#wbNewDocument").click()
                page.wait_for_function(
                    "() => window.JawWorkbenchStore.getState().documents?.length === 2"
                )

                template_editor = page.locator('[data-wb-editor="template"]')
                playwright.expect(template_editor).to_be_enabled()
                assert "{{ section }}" in template_editor.input_value()

                state = page.evaluate("window.JawWorkbenchStore.getState()")
                snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
                active_document_id = snapshot["activeDocumentId"]
                document = next(
                    item for item in state["documents"] if item["id"] == active_document_id
                )
                other_document = next(
                    item for item in state["documents"] if item["id"] != active_document_id
                )
                assert document["template_id"] != other_document["template_id"]
                assert document["template"]["visibility"] == "private"
                assert document["template"]["owner_id"] == active_document_id
                template = document["template"]
                section = document["sections"][0]

                # Clicking a bound Section in the Template selects/opens that
                # Section while preserving the caret in the Template editor.
                click_index = template_editor.input_value().index("section") + 2
                _click_character(page, template_editor, click_index)

                playwright.expect(
                    page.locator('[data-wb-pane="section"] .wb-resource-tab.active')
                ).to_contain_text(section["reference_symbol"])
                snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
                assert snapshot["activeDocumentId"] == active_document_id
                assert snapshot["activeTabs"]["section"] == section["id"]
                _assert_selected(page, section)
                playwright.expect(page.locator("#wbRelationships")).to_contain_text("Used by")
                playwright.expect(page.locator("#wbRelationships")).to_contain_text("section")
                _assert_caret_in_word(template_editor, "section")
                assert page.evaluate(
                    "document.activeElement?.dataset?.wbEditor || ''"
                ) == "template"

                # Clicking ordinary Template text is selection-only. The active
                # Document and already-open Section pane must remain untouched.
                plain_template_index = template_editor.input_value().index("\\documentclass") + 1
                _click_character(page, template_editor, plain_template_index)
                _assert_selected(page, template)
                playwright.expect(page.locator("#wbInspector")).to_contain_text("template")
                playwright.expect(page.locator("#wbInspector")).to_contain_text("private")
                playwright.expect(page.locator("#wbRelationships")).to_contain_text(
                    "No relationships"
                )
                snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
                assert snapshot["activeDocumentId"] == active_document_id
                assert snapshot["activeTabs"]["section"] == section["id"]
                assert page.evaluate(
                    "document.activeElement?.dataset?.wbEditor || ''"
                ) == "template"

                section_editor = page.locator('[data-wb-editor="section"]')
                section_editor.fill("{{ helper() }}")
                page.wait_for_function(
                    """
                    documentId => {
                      const state = window.JawWorkbenchStore.getState();
                      const document = state.documents?.find(item => item.id === documentId);
                      return document?.sections?.[0]?.functions?.some(
                        item => item.reference_symbol === 'helper' || item.symbol === 'helper'
                      );
                    }
                    """,
                    arg=active_document_id,
                )
                state = page.evaluate("window.JawWorkbenchStore.getState()")
                document = next(
                    item for item in state["documents"] if item["id"] == active_document_id
                )
                helper = document["sections"][0]["functions"][0]

                # A bound Function in a Section behaves exactly like the Section
                # reference above: child selected/opened, source caret retained.
                click_index = section_editor.input_value().index("helper") + 2
                _click_character(page, section_editor, click_index)

                playwright.expect(
                    page.locator('[data-wb-pane="function"] .wb-resource-tab.active')
                ).to_contain_text(helper["reference_symbol"])
                snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
                assert snapshot["activeDocumentId"] == active_document_id
                assert snapshot["activeTabs"]["function"] == helper["id"]
                _assert_selected(page, helper)
                playwright.expect(page.locator("#wbRelationships")).to_contain_text("Used by")
                playwright.expect(page.locator("#wbRelationships")).to_contain_text("helper")
                _assert_caret_in_word(section_editor, "helper")
                assert page.evaluate(
                    "document.activeElement?.dataset?.wbEditor || ''"
                ) == "section"

                # Ordinary Section text resolves back to the Section without
                # closing the Function pane.
                _click_character(page, section_editor, 0)
                _assert_selected(page, section)
                playwright.expect(page.locator("#wbRelationships")).to_contain_text("Contains")
                playwright.expect(page.locator("#wbRelationships")).to_contain_text("helper")
                snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
                assert snapshot["activeDocumentId"] == active_document_id
                assert snapshot["activeTabs"]["function"] == helper["id"]

                # A Function has no Workbench children, so any ordinary click in
                # its editor resolves to the Function itself.
                function_editor = page.locator('[data-wb-editor="function"]')
                function_editor.fill("Helper body")
                _click_character(page, section_editor, 0)
                _assert_selected(page, section)
                _click_character(page, function_editor, 2)
                _assert_selected(page, helper)
                snapshot = page.evaluate("window.JawWorkbenchStore.getSnapshot()")
                assert snapshot["activeDocumentId"] == active_document_id
                assert page.evaluate(
                    "document.activeElement?.dataset?.wbEditor || ''"
                ) == "function"

                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()
