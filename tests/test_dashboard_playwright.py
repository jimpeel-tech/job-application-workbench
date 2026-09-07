from __future__ import annotations

import re

import pytest

from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer

playwright = pytest.importorskip("playwright.sync_api")


def test_dashboard_capabilities_smoke_in_real_browser(tmp_path):
    """Exercise Capability Set lifecycle and user isolation in Chromium."""

    database_path = tmp_path / "data" / "jaw.db"
    store = UserDataStore(database_path)
    first_user = store.read()
    first_user_id = int(first_user["active_user_id"])
    kubernetes = store.upsert_entity(
        {
            "id": "cap_browser_kubernetes",
            "type": "technology",
            "canonical_name": "Kubernetes",
            "display_name": "Kubernetes",
            "rating": 4,
        }
    )
    second_user_id = store.create_user("Browser Empty User", clone_current=False)
    store.switch_user(first_user_id)

    server = DashboardServer(
        JobDatabase(database_path),
        port=0,
        user_data_path=database_path,
    )
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
                page.goto(server.url, wait_until="domcontentloaded")
                playwright.expect(page.locator(".brand")).to_have_text(
                    "Job Application Workbench"
                )
                playwright.expect(page.locator("#userSelector option")).to_have_count(2)

                page.locator("#menuButton").click()
                page.locator('[data-route="capabilities"]').click()
                playwright.expect(page.locator("#capViewTitle")).to_have_text(
                    "Hierarchy View"
                )
                playwright.expect(page.locator("#capContent")).to_contain_text(
                    "Kubernetes"
                )
                playwright.expect(page.locator("#capStats")).to_contain_text(
                    "Capabilities"
                )

                page.locator('[data-cap-view="set"]').click()
                playwright.expect(page.locator("#capNewSet")).to_be_visible()
                page.locator("#capNewSet").click()
                playwright.expect(page.locator("#capSetDialog")).to_be_visible()
                assert page.locator("#capSetDialog").evaluate(
                    "element => element.open"
                ) is True
                playwright.expect(page.locator("#capSetDocument")).to_be_checked()
                playwright.expect(page.locator("#capSetPaste")).to_be_checked()
                page.locator("#capSetName").fill("Platform & SRE")
                page.locator("#capSetPaste").uncheck()
                with page.expect_response(
                    lambda response: response.url.endswith(
                        "/api/capabilities/sets/save"
                    )
                ) as save_set:
                    page.locator("#capSaveSet").click()
                assert save_set.value.ok

                set_button = page.locator(
                    '[data-cap-set]', has_text="Platform & SRE"
                )
                playwright.expect(set_button).to_be_visible()
                set_id = set_button.get_attribute("data-cap-set")
                assert set_id and set_id != "__all__"
                assert (
                    store.read()["capability_model"]["active_set_id"]
                    == "__all__"
                )

                member = page.locator(
                    f'[data-cap-card="{kubernetes["id"]}"]'
                ).first
                playwright.expect(member).to_be_visible()
                assert "selected" not in (member.get_attribute("class") or "")
                with page.expect_response(
                    lambda response: response.url.endswith(
                        "/api/capabilities/sets/save"
                    )
                ) as membership_save:
                    member.click()
                assert membership_save.value.ok
                playwright.expect(member).to_have_class(re.compile(r"\bselected\b"))

                page.locator("#capEditSet").click()
                playwright.expect(page.locator("#capSetDocument")).to_be_checked()
                playwright.expect(page.locator("#capSetPaste")).not_to_be_checked()
                page.locator("#capSetName").fill("Platform Reliability")
                with page.expect_response(
                    lambda response: response.url.endswith(
                        "/api/capabilities/sets/save"
                    )
                ) as rename_save:
                    page.locator("#capSaveSet").click()
                assert rename_save.value.ok
                renamed_button = page.locator(
                    '[data-cap-set]', has_text="Platform Reliability"
                )
                playwright.expect(renamed_button).to_be_visible()
                assert renamed_button.get_attribute("data-cap-set") == set_id
                playwright.expect(
                    page.locator(f'[data-cap-card="{kubernetes["id"]}"]').first
                ).to_have_class(re.compile(r"\bselected\b"))

                # Switching users while Capabilities is active must replace the
                # capability state immediately, not leave the first user's model.
                with page.expect_response(
                    lambda response: response.url.endswith("/api/users/switch")
                ) as switch_user:
                    page.locator("#userSelector").select_option(str(second_user_id))
                assert switch_user.value.ok
                playwright.expect(page.locator("#capStats")).to_contain_text(
                    "0Capabilities"
                )
                playwright.expect(page.locator("#capContent")).not_to_contain_text(
                    "Kubernetes"
                )
                playwright.expect(
                    page.locator('[data-cap-set]', has_text="Platform Reliability")
                ).to_have_count(0)

                page.locator("#userSelector").select_option(str(first_user_id))
                playwright.expect(page.locator("#capContent")).to_contain_text(
                    "Kubernetes"
                )
                renamed_button = page.locator(
                    '[data-cap-set]', has_text="Platform Reliability"
                )
                playwright.expect(renamed_button).to_be_visible()
                renamed_button.click()
                playwright.expect(
                    page.locator(f'[data-cap-card="{kubernetes["id"]}"]').first
                ).to_have_class(re.compile(r"\bselected\b"))

                page.locator("#capEditSet").click()
                page.once("dialog", lambda dialog: dialog.accept())
                with page.expect_response(
                    lambda response: response.url.endswith(
                        "/api/capabilities/sets/delete"
                    )
                ) as delete_set:
                    page.locator("#capDeleteSet").click()
                assert delete_set.value.ok
                playwright.expect(
                    page.locator('[data-cap-set]', has_text="Platform Reliability")
                ).to_have_count(0)
                playwright.expect(
                    page.locator('[data-cap-set="__all__"]')
                ).to_have_class(re.compile(r"\bactive\b"))
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()


def test_tracker_requires_explicit_job_selection_in_real_browser(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    store = UserDataStore(database_path)
    user_id = int(store.read()["active_user_id"])
    job_id = database.create_job("Explicit tracker selection", user_id=user_id)
    database.update_analysis(
        job_id,
        {"company": "Example Corp", "title": "Platform Engineer"},
        "browser-smoke",
    )

    server = DashboardServer(database, port=0, user_data_path=database_path)
    server.start()
    try:
        with playwright.sync_playwright() as runtime:
            try:
                browser = runtime.chromium.launch(headless=True)
            except playwright.Error as error:
                pytest.skip(f"Playwright Chromium is not installed: {error}")
            try:
                page = browser.new_page()
                page.goto(f"{server.url}/#tracker", wait_until="domcontentloaded")
                playwright.expect(page.locator("#jobs")).to_contain_text("Platform Engineer")
                playwright.expect(page.locator("#detail")).to_contain_text(
                    "Select a job to review it."
                )
                playwright.expect(page.locator(".tracker-job.active")).to_have_count(0)

                page.goto(
                    f"{server.url}/#tracker/job/{job_id}",
                    wait_until="domcontentloaded",
                )
                playwright.expect(page.locator("#detail h1")).to_have_text(
                    "Platform Engineer"
                )
                playwright.expect(page.locator(".tracker-job.active")).to_have_count(1)
            finally:
                browser.close()
    finally:
        server.stop()


def test_native_workbench_and_tracker_document_routing_in_real_browser(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    store = UserDataStore(database_path)
    user_id = int(store.read()["active_user_id"])
    job_id = database.create_job("Senior platform reliability role", user_id=user_id)
    database.update_analysis(
        job_id,
        {
            "company": "Example Corp",
            "title": "Senior SRE",
            "summary": "Own platform reliability.",
        },
        "browser-smoke",
    )

    server = DashboardServer(database, port=0, user_data_path=database_path)
    server.start()
    page_errors: list[str] = []
    workbench_state_requests: list[str] = []
    try:
        with playwright.sync_playwright() as runtime:
            try:
                browser = runtime.chromium.launch(headless=True)
            except playwright.Error as error:
                pytest.skip(f"Playwright Chromium is not installed: {error}")
            try:
                page = browser.new_page()
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on(
                    "request",
                    lambda request: workbench_state_requests.append(request.url)
                    if request.url.endswith("/api/workbench/state")
                    else None,
                )
                page.goto(f"{server.url}/#documents", wait_until="domcontentloaded")

                playwright.expect(page.locator(".wb-shell")).to_be_visible(timeout=15_000)
                playwright.expect(page.locator("#wbExplorer")).to_contain_text(
                    "No Documents"
                )
                assert len(workbench_state_requests) == 1
                assert page.eval_on_selector_all(
                    '[data-wb-side="left"] [data-wb-side-pane]',
                    "elements => elements.map(element => element.dataset.wbSidePane)",
                )[:3] == ["explorer", "global-templates", "inspector"]

                with page.expect_response(
                    lambda response: response.url.endswith(
                        "/api/workbench/documents/create"
                    )
                ) as create_document:
                    page.locator("#wbNewDocument").click()
                assert create_document.value.ok
                playwright.expect(page.locator(".wb-doc-tab.active")).to_contain_text(
                    "Document"
                )
                template_editor = page.locator('[data-wb-editor="template"]')
                assert "{{ section }}" in template_editor.input_value()

                before = page.evaluate("window.JawWorkbenchStore.getState()")
                original_document = before["documents"][0]
                original_template_id = original_document["template_id"]
                original_section_id = original_document["sections"][0]["id"]

                loop = r"""{% for paragraph in paragraphs %}
\CoverParagraph{
  {{ paragraph }}
}
{% endfor %}"""
                source = template_editor.input_value().replace("{{ section }}", loop)
                template_editor.fill(source)

                # Replacing an existing bound construct is intentionally pending.
                # The editor must not auto-reconcile it through checkpoint.
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
                pending = page.evaluate("window.JawWorkbenchStore.getState()")
                pending_document = pending["documents"][0]
                assert pending_document["template_id"] == original_template_id
                assert pending_document["template"]["visibility"] == "private"
                assert pending_document["template"]["owner_id"] == pending_document["id"]
                assert "system_template" not in pending_document["template"]["settings"]
                assert pending_document["sections"][0]["id"] == original_section_id
                assert pending_document["sections"][0]["reference_symbol"] == "section"
                assert all(resource["symbol"] != "paragraphs" for resource in pending["resources"])

                with page.expect_response(
                    lambda response: response.url.endswith(
                        "/api/workbench/rename-symbol"
                    )
                ) as update_reference:
                    page.locator('[data-wb-reference-update]').click()
                assert update_reference.value.ok
                page.wait_for_function(
                    """
                    args => {
                      const document = window.JawWorkbenchStore.getState().documents?.[0];
                      const section = document?.sections?.[0];
                      return document?.template_id === args.templateId
                        && document?.template?.visibility === 'private'
                        && section?.id === args.sectionId
                        && section?.reference_symbol === 'paragraphs';
                    }
                    """,
                    arg={"templateId": original_template_id, "sectionId": original_section_id},
                )

                state = page.evaluate("window.JawWorkbenchStore.getState()")
                assert len(state["documents"]) == 1
                document = state["documents"][0]
                assert document["template_id"] == original_template_id
                assert document["template"]["visibility"] == "private"
                assert "system_template" not in document["template"]["settings"]
                assert [section["reference_symbol"] for section in document["sections"]] == [
                    "paragraphs"
                ]
                assert document["sections"][0]["id"] == original_section_id
                assert all(resource["symbol"] != "paragraph" for resource in state["resources"])
                page.locator("#wbExplorer").locator(
                    f'[data-wb-expand="{document["id"]}:sections"]'
                ).click()
                playwright.expect(page.locator("#wbExplorer")).to_contain_text("paragraphs")
                playwright.expect(
                    page.locator(
                        '[data-wb-pane="template"] .wb-editor-highlight .wb-syn-private',
                        has_text="paragraphs",
                    )
                ).to_have_count(1)
                playwright.expect(
                    page.locator(
                        '[data-wb-pane="template"] .wb-editor-highlight .wb-syn-local',
                        has_text="paragraph",
                    )
                ).to_have_count(2)
                playwright.expect(page.locator("#wbGlobalTemplates")).to_contain_text(
                    "Empty"
                )

                page.goto(
                    f"{server.url}/#tracker/job/{job_id}",
                    wait_until="domcontentloaded",
                )
                playwright.expect(page.locator(".tracker-document-action")).to_be_visible()
                initial_hash = page.evaluate("location.hash")
                page.locator(".tracker-document-action").click()
                playwright.expect(page.locator(".jaw-doc-command-dialog")).to_be_visible()
                playwright.expect(page.locator(".jaw-doc-current-job")).to_contain_text(
                    "Senior SRE"
                )
                playwright.expect(page.locator(".jaw-doc-manual-grid")).to_contain_text(
                    "Document"
                )
                assert page.evaluate("location.hash") == initial_hash
                assert page_errors == []
            finally:
                browser.close()
    finally:
        server.stop()
