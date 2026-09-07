from __future__ import annotations

import re

import pytest

from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer

playwright = pytest.importorskip("playwright.sync_api")


def test_workbench_editor_tracks_saved_changes_and_undo_redo(tmp_path):
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

                page.locator("#wbNewDocument").click()
                editor = page.locator('[data-wb-editor="template"]')
                # The click starts an async create request; wait for the returned
                # Workbench state to mount the starter Template before reading it.
                playwright.expect(editor).to_have_value(
                    re.compile(r"\\pagestyle\{empty\}")
                )
                saved = editor.input_value()
                changed = saved.replace(r"\pagestyle{empty}", r"\pagestyle{plain}")
                assert changed != saved

                editor.fill(changed)
                playwright.expect(
                    page.locator('[data-wb-pane="template"] .wb-gutter-line.modified')
                ).not_to_have_count(0)
                playwright.expect(
                    page.locator('[data-wb-pane="template"] [data-wb-changes="template"]')
                ).to_be_enabled()
                playwright.expect(
                    page.locator('[data-wb-pane="template"] .wb-resource-tab.active .wb-dirty')
                ).to_have_count(1)

                page.locator('[data-wb-pane="template"] [data-wb-changes="template"]').click()
                playwright.expect(page.locator(".wb-changes-overlay")).to_be_visible()
                playwright.expect(page.locator(".wb-changes-diff")).to_contain_text(
                    r"-\pagestyle{empty}"
                )
                playwright.expect(page.locator(".wb-changes-diff")).to_contain_text(
                    r"+\pagestyle{plain}"
                )
                page.locator(".wb-changes-head [data-wb-changes-close]").click()

                # Send shortcuts to the textarea itself. This both models the real
                # user gesture and avoids a page-level keyboard target racing a
                # pending Workbench render after clone-on-write/checkpointing.
                editor.press("Control+z")
                playwright.expect(editor).to_have_value(saved)
                playwright.expect(
                    page.locator('[data-wb-pane="template"] .wb-gutter-line.modified')
                ).to_have_count(0)
                playwright.expect(
                    page.locator('[data-wb-pane="template"] .wb-resource-tab.active .wb-dirty')
                ).to_have_count(0)
                playwright.expect(
                    page.locator('[data-wb-pane="template"] [data-wb-changes="template"]')
                ).to_be_disabled()

                editor.press("Control+y")
                playwright.expect(editor).to_have_value(changed)
                playwright.expect(
                    page.locator('[data-wb-pane="template"] .wb-resource-tab.active .wb-dirty')
                ).to_have_count(1)

                # Returning manually to the exact Saved content is clean even
                # though the recovery/checkpoint lifecycle may already have run.
                editor.fill(saved)
                playwright.expect(
                    page.locator('[data-wb-pane="template"] .wb-resource-tab.active .wb-dirty')
                ).to_have_count(0)
                playwright.expect(
                    page.locator('[data-wb-pane="template"] [data-wb-changes="template"]')
                ).to_be_disabled()
                playwright.expect(
                    page.locator('[data-wb-pane="template"] .wb-editor-gutter .wb-gutter-number')
                ).to_have_count(len(saved.split("\n")))
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()


def test_workbench_syntax_mirror_stays_aligned_at_trailing_newline(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    server = DashboardServer(database, port=0, user_data_path=database_path)
    server.start()
    try:
        with playwright.sync_playwright() as runtime:
            try:
                browser = runtime.chromium.launch(headless=True)
            except playwright.Error as error:
                pytest.skip(f"Playwright Chromium is not installed: {error}")
            try:
                page = browser.new_page(viewport={"width": 1100, "height": 760})
                page.goto(f"{server.url}/#documents", wait_until="domcontentloaded")
                playwright.expect(page.locator(".wb-shell")).to_be_visible(timeout=15_000)

                page.locator("#wbNewDocument").click()
                editor = page.locator('[data-wb-editor="template"]')
                playwright.expect(editor).to_have_value(re.compile(r"\\pagestyle\{empty\}"))

                content = "\n".join(f"line {number}" for number in range(1, 141)) + "\n"
                editor.fill(content)
                mirror = page.locator('[data-wb-pane="template"] .wb-editor-highlight')
                playwright.expect(mirror).to_be_visible()

                editor.evaluate(
                    """node => {
                        node.scrollTop = node.scrollHeight;
                        node.dispatchEvent(new Event('scroll'));
                    }"""
                )
                page.wait_for_timeout(20)

                metrics = page.evaluate(
                    """() => {
                        const editor = document.querySelector('[data-wb-editor="template"]');
                        const mirror = document.querySelector('[data-wb-pane="template"] .wb-editor-highlight');
                        return {
                            editorTop: editor.scrollTop,
                            mirrorTop: mirror.scrollTop,
                            editorMax: editor.scrollHeight - editor.clientHeight,
                            mirrorMax: mirror.scrollHeight - mirror.clientHeight,
                        };
                    }"""
                )

                assert abs(metrics["editorTop"] - metrics["mirrorTop"]) <= 1
                assert metrics["mirrorMax"] + 1 >= metrics["editorMax"]
            finally:
                browser.close()
    finally:
        server.stop()
