from __future__ import annotations

import pytest

from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer

playwright = pytest.importorskip("playwright.sync_api")


def test_keyboard_layout_switch_preserves_physical_action_positions(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    store = UserDataStore(database_path)
    server = DashboardServer(
        JobDatabase(database_path),
        port=0,
        user_data_path=database_path,
    )
    server.start()
    try:
        with playwright.sync_playwright() as runtime:
            try:
                browser = runtime.chromium.launch(headless=True)
            except playwright.Error as error:
                pytest.skip(f"Playwright Chromium is not installed: {error}")
            try:
                page = browser.new_page()
                page.goto(server.url, wait_until="domcontentloaded")
                page.locator("#menuButton").click()
                page.locator('[data-route="keybinds"]').click()

                matrix = page.locator("#keybindMatrix")
                playwright.expect(matrix.locator('[data-slot="P12"] .key-name')).to_have_text("E")
                playwright.expect(matrix.locator('[data-slot="P12"] .key-action')).to_contain_text(
                    "Previous"
                )
                playwright.expect(matrix.locator('[data-slot="P13"] .key-name')).to_have_text("R")
                playwright.expect(matrix.locator('[data-slot="P13"] .key-action')).to_contain_text(
                    "Work Exp"
                )
                playwright.expect(matrix.locator('[data-slot="P23"] .key-name')).to_have_text("F")
                playwright.expect(matrix.locator('[data-slot="P23"] .key-action')).to_contain_text(
                    "Skills"
                )

                page.locator("#keyboardLayout").select_option("colemak-dh")

                playwright.expect(matrix.locator('[data-slot="P12"] .key-name')).to_have_text("F")
                playwright.expect(matrix.locator('[data-slot="P12"] .key-action')).to_contain_text(
                    "Previous"
                )
                playwright.expect(matrix.locator('[data-slot="P13"] .key-name')).to_have_text("P")
                playwright.expect(matrix.locator('[data-slot="P13"] .key-action')).to_contain_text(
                    "Work Exp"
                )
                playwright.expect(matrix.locator('[data-slot="P23"] .key-name')).to_have_text("T")
                playwright.expect(matrix.locator('[data-slot="P23"] .key-action')).to_contain_text(
                    "Skills"
                )
                playwright.expect(matrix.locator('[data-slot="P24"] .key-name')).to_have_text("G")
                playwright.expect(matrix.locator('[data-slot="P24"] .key-action')).to_contain_text(
                    "Capture"
                )

                with page.expect_response(
                    lambda response: response.url.endswith("/api/keybinds")
                    and response.request.method == "POST"
                ) as save_response:
                    page.locator("#saveKeybinds").click()
                assert save_response.value.ok

                saved = store.read()
                assert saved["keyboard_layout"] == "colemak-dh"
                assert saved["keybinds"]["base"]["P12"] == "previous_iterator"
                assert saved["keybinds"]["base"]["P13"] == "iterate_work_exp"
                assert saved["keybinds"]["base"]["P23"] == "iterate_skills"
                assert saved["keybinds"]["base"]["P24"] == "smart_capture"
            finally:
                browser.close()
    finally:
        server.stop()
