from jaw.config import (
    DEFAULT_BEHAVIOR,
    ensure_config_file,
    save_behavior_settings,
)
from jaw.integrations.outlook.web import OutlookWebController
from jaw.web.assets import DASHBOARD_PAGE


class FakeService:
    def status(self, _user_id):
        return {"auth": {"connected": True}, "sync": {}}


def test_outlook_sync_is_disabled_by_default():
    assert DEFAULT_BEHAVIOR["outlook_sync_enabled"] is False


def test_outlook_config_flag_is_written_and_preserved(tmp_path):
    config_path = tmp_path / "config.toml"
    ensure_config_file(config_path)
    text = config_path.read_text(encoding="utf-8")
    assert "outlook_sync_enabled = false" in text

    config_path.write_text(
        text.replace("outlook_sync_enabled = false", "outlook_sync_enabled = true"),
        encoding="utf-8",
    )
    ensure_config_file(config_path)
    assert "outlook_sync_enabled = true" in config_path.read_text(encoding="utf-8")

    save_behavior_settings(
        {
            "contact": False,
            "address": False,
            "links": False,
            "skills": True,
            "work_exp": True,
        },
        250,
        path=config_path,
    )
    assert "outlook_sync_enabled = true" in config_path.read_text(encoding="utf-8")


def test_dashboard_contains_hidden_outlook_sync_surface():
    dashboard = DASHBOARD_PAGE.read()
    assert b'id="outlookSyncPanel"' in dashboard
    assert b'aria-label="Outlook job mail sync" hidden' in dashboard
    assert b'id="outlookConnect"' in dashboard
    assert b'id="outlookReset"' in dashboard
    assert b'id="outlookSync"' in dashboard
    assert b"/api/outlook/status" in dashboard
    assert b"/api/outlook/reset" in dashboard
    assert b"/api/outlook/sync" in dashboard
    assert b"if (!data.enabled)" in dashboard
    assert b"9 Review" not in dashboard  # category details stay in the backend, not visual clutter


def test_outlook_controller_hides_and_blocks_feature_when_disabled():
    controller = OutlookWebController(FakeService(), enabled=lambda: False)
    assert controller.get("/api/outlook/status", 1) == ({"enabled": False}, 200)
    response = controller.post("/api/outlook/sync", {}, 1)
    assert response is not None
    payload, status = response
    assert status == 403
    assert "disabled in config.toml" in payload["error"]


def test_outlook_controller_exposes_status_when_enabled():
    controller = OutlookWebController(FakeService(), enabled=lambda: True)
    payload, status = controller.get("/api/outlook/status", 1)
    assert status == 200
    assert payload["enabled"] is True
    assert payload["auth"]["connected"] is True
