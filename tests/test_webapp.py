import json
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from jaw.config import ensure_config_file
from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer


def test_dashboard_assets_and_complete_export(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    ensure_config_file(tmp_path / "config.toml")
    store = UserDataStore(database_path)
    store.save_custom_fields([
        {"id": "sample", "label": "Sample", "value": "Value", "type": "single"}
    ])
    server = DashboardServer(
        JobDatabase(database_path), port=0,
        user_data_path=database_path,
    )
    server.start()
    try:
        with urlopen(f"{server.url}/", timeout=3) as response:
            html = response.read().decode("utf-8")
        assert '/dashboard.css' in html and '/dashboard.js' in html
        with urlopen(f"{server.url}/dashboard.css", timeout=3) as response:
            assert response.headers.get_content_type() == "text/css"
            assert b":root" in response.read()
        with urlopen(f"{server.url}/api/user-data/export", timeout=3) as response:
            exported = json.load(response)
        assert exported["version"] == 6
        assert "documents" not in exported
        assert "capability_model" in exported
        assert "sections" not in exported
        assert exported["custom_fields"][0]["label"] == "Sample"
        assert "keybinds" in exported
    finally:
        server.stop()


def test_retired_fixture_review_web_contract_stays_absent(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    store = UserDataStore(database_path)
    dev_id = store.create_user("Dev")
    store.switch_user(dev_id)
    server = DashboardServer(
        JobDatabase(database_path),
        port=0,
        user_data_path=database_path,
    )
    server.start()
    try:
        for path in (
            "/review?fixture=legacy",
            "/review.js",
            "/review.css",
            "/api/dev/fixtures",
            "/api/dev/fixtures/legacy",
        ):
            with pytest.raises(HTTPError) as exc_info:
                urlopen(f"{server.url}{path}", timeout=3)
            assert exc_info.value.code == 404

        with urlopen(f"{server.url}/api/keybinds", timeout=3) as response:
            keybinds = json.load(response)
        assert "dev_capture_fixture" not in keybinds["action_labels"]
        assert "dev_prepare_review" not in keybinds["action_labels"]
    finally:
        server.stop()
