from __future__ import annotations

from pathlib import Path

import pytest

from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer

playwright = pytest.importorskip("playwright.sync_api")


def test_download_dev_only_appears_for_dev_user(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    users = UserDataStore(database_path)
    dev_id = users.create_user("Dev")
    users.switch_user(dev_id)

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

                page.locator("#wbTemplateRepo").click()
                dev_button = page.locator("[data-wb-repository-download-dev]")
                playwright.expect(dev_button).to_be_visible()
                playwright.expect(dev_button).to_have_text("Download Dev")

                page.locator("[data-wb-repository-close]").last.click()
                regular_id = users.create_user("Regular")
                users.switch_user(regular_id)

                page.locator("#wbTemplateRepo").click()
                playwright.expect(dev_button).to_be_hidden()
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()
