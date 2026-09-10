from pathlib import Path

from jaw.config import BUILTIN_ACTION_LABELS, load_config, save_behavior_settings
from jaw.smart_capture import normalize_smart_capture_settings
from jaw.userdata import normalize_layer_bindings


def test_analysis_action_is_first_class_without_mutating_custom_keybinds(tmp_path: Path):
    assert BUILTIN_ACTION_LABELS["analyze_job"] == "Analysis"
    normalized = normalize_layer_bindings(
        {
            "base": {"1": "cycle_layers", "B": "open_dashboard"},
            "layer2": {},
            "layer3": {},
            "action_displays": {},
        }
    )
    assert normalized["base"] == {"1": "cycle_layers", "B": "open_dashboard"}

    config = load_config(tmp_path / "config.toml")
    assert config.matrix["2"].partition("|")[0] == "analyze_job"
    assert config.action_displays["analyze_job"]["icons"] == ["brief"]


def test_smart_capture_settings_round_trip_through_runtime_config(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config = load_config(config_path)
    settings = normalize_smart_capture_settings(
        {
            **config.smart_capture_settings,
            "analysis_mode": "ollama",
            "dev": True,
        }
    )
    save_behavior_settings(
        config.auto_return,
        config.iterator_delay_ms,
        smart_capture_settings=settings,
        path=config_path,
    )
    loaded = load_config(config_path)
    assert loaded.smart_capture_settings["analysis_mode"] == "ollama"
    assert loaded.smart_capture_settings["dev"] is True
    assert loaded.smart_capture_settings["focus_mode"] is False
    assert "company" in loaded.smart_capture_settings["visible_fields"]
    assert "title" in loaded.smart_capture_settings["visible_fields"]


def test_production_smart_capture_uses_flat_tabs_and_retires_fixture_mode():
    source = Path("src/jaw/desktop/smart_capture_window.py").read_text(encoding="utf-8")
    assert "self.capture_tabs = QTabBar()" in source
    assert '"Parsed"' in source
    assert '"Captured (0)"' in source
    assert '"Review (0)"' in source
    assert '"Fixtures"' in source
    assert '"Ollama only"' in source
    assert 'settings["dev"]' in source
    assert "snapshot_session(" in source
    assert "resolve_parser_evidence(" in source
    assert "parser_resolution=parser_resolution" in source
    assert "merge_resolution=merge_resolution" in source
    assert "true conflict" in source
    assert "AI uncertain" in source
    assert "parser gap" in source
    assert "expected values remain unset" in source
    assert "Q&A ({len(questions)})" in source
    assert 'event.get("content_type", "")' in source
    assert '"application_question"' in source
    assert 'QPushButton("Open Tracker")' not in source
    assert "capture_fixture_list" not in source
    assert "list_snapshots(" not in source
    assert "_CAPTURE_FIXTURE_STATUS_DEFAULT" in source
    assert "def _reset_capture_fixture_status" in source
    refresh = source.split("def _refresh_capture_pane", 1)[1].split(
        "def _populate_capture_summary", 1
    )[0]
    assert "if not events:" in refresh
    assert "self._reset_capture_fixture_status()" in refresh
    accept = source.split("def _accept_capture_selection", 1)[1].split(
        "def _reset_capture_fixture_status", 1
    )[0]
    assert "self._reset_capture_fixture_status()" in accept
    assert "_show_fixture_pane" not in source
    assert "_prepare_fixture_review" not in source
    # Cursor rendering belongs to BaseMainWindow. Keeping this subclass free of
    # its own badge updater prevents it from overwriting iterator/rolodex state.
    assert "def _update_cursor_badge" not in source


def test_hotkey_disabled_status_is_persistent_and_uses_configured_toggle():
    source = Path("src/jaw/desktop/smart_capture_window.py").read_text(encoding="utf-8")
    assert 'self.hotkeys_status_label = QLabel()' in source
    assert 'self.statusBar().insertWidget(0, self.hotkeys_status_label, 1)' in source
    assert 'self.config.hotkey_settings.get("toggle", "SHIFT+SPACE")' in source
    assert 'f"Hotkeys disabled · {shortcut} to enable"' in source
    assert '"SPACE": "Spacebar"' in source
    assert "def _update_hotkeys_visual_state" in source
    assert "self._refresh_hotkeys_status()" in source


def test_tracker_and_analysis_desktop_dispatch_remain_separate():
    base_source = Path("src/jaw/main.py").read_text(encoding="utf-8")
    product_source = Path("src/jaw/desktop/smart_capture_window.py").read_text(encoding="utf-8")
    assert "_tracker_press" not in base_source
    assert 'elif action == "open_dashboard":\n            self.open_dashboard()' in base_source
    assert (
        'elif action == "analyze_job":\n            self._analyze_capture_journal()' in base_source
    )
    assert 'if action == "smart_capture":' in product_source
    assert (
        "_analyze_capture_journal"
        not in product_source.split('if action == "smart_capture":', 1)[1].split(
            "super()._dispatch_action", 1
        )[0]
    )


def test_legacy_fixture_capture_and_web_review_surface_are_removed():
    base_source = Path("src/jaw/main.py").read_text(encoding="utf-8")
    product_source = Path("src/jaw/desktop/smart_capture_window.py").read_text(encoding="utf-8")
    web_source = Path("src/jaw/webapp.py").read_text(encoding="utf-8")

    for retired in (
        "_fixture_capture_mode",
        "_show_fixture_pane",
        "_prepare_fixture_review",
        "dev_capture_fixture",
        "dev_prepare_review",
    ):
        assert retired not in base_source
        assert retired not in product_source

    assert "/api/dev/fixtures" not in web_source
    assert 'parsed.path == "/review"' not in web_source
    assert "REVIEW_PAGE" not in web_source
    assert "FixtureStore" not in web_source


def test_analysis_completion_opens_selected_tracker_job_and_focuses_application_capture():
    base_source = Path("src/jaw/main.py").read_text(encoding="utf-8")
    product_source = Path("src/jaw/desktop/smart_capture_window.py").read_text(encoding="utf-8")

    brief = base_source.split("def _brief_completed", 1)[1].split("def _brief_failed", 1)[0]
    assert "self._enter_application_capture_mode()" in brief
    assert "self.open_dashboard()" in brief
    assert 'suffix = f"/?job={self.active_job_id}"' in base_source
    assert "self.capture_tabs.setCurrentIndex(self.capture_qna_tab)" in product_source
