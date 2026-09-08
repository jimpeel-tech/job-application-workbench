from datetime import date

from jaw.config import (
    load_config,
    resolve_layer_binding,
    save_behavior_settings,
    split_binding,
)
from jaw.model import DateFormat


def test_date_formats():
    value = date(2024, 11, 1)
    assert DateFormat.NUMERIC.values_for(value) == ["11/2024"]
    assert DateFormat.NUMERIC_SPLIT.values_for(value) == ["11", "2024"]
    assert DateFormat.SHORT_SPLIT.values_for(value) == ["Nov", "2024"]
    assert DateFormat.LONG_SPLIT.values_for(value) == ["November", "2024"]


def test_missing_config_is_created_from_read_only_defaults(tmp_path):
    config_path = tmp_path / "clean-install" / "config.toml"
    assert not config_path.exists()
    config = load_config(config_path)
    assert config_path.exists()
    assert config.dashboard_port == 8765
    assert config.hotkeys_active_on_startup is False
    assert "iterate_contact" in {
        split_binding(binding)[0] for binding in config.matrix.values()
    }
    text = config_path.read_text(encoding="utf-8")
    assert "your-key" not in text
    assert "Jim" not in text
    assert "[behavior]" in text
    assert "hotkeys_active_on_startup = false" in text
    assert "[matrix" not in text
    assert "[action_labels]" not in text
    assert split_binding(config.matrix["G"])[0] == "smart_capture"


def test_hotkey_startup_preference_round_trips(tmp_path):
    config_path = tmp_path / "config.toml"
    save_behavior_settings(
        auto_return={},
        iterator_delay_ms=250,
        hotkeys_active_on_startup=True,
        path=config_path,
    )

    config = load_config(config_path)

    assert config.hotkeys_active_on_startup is True
    assert "hotkeys_active_on_startup = true" in config_path.read_text(
        encoding="utf-8"
    )


def test_legacy_config_is_cleaned_without_losing_behavior(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[matrix.base]
q = "old_action"
[action_labels]
old_action = "Old"
[dashboard]
port = 9999
[behavior]
iterator_delay_ms = 410
show_keyboard = false
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.iterator_delay_ms == 410
    assert config.show_keyboard is False
    assert config.hotkeys_active_on_startup is False
    assert config.dashboard_port == 8765
    assert "old_action" not in config.action_labels
    cleaned = config_path.read_text(encoding="utf-8")
    assert "[matrix" not in cleaned
    assert "[dashboard]" not in cleaned


def test_layer_controls_remain_reachable_from_every_layer():
    base = {"D": "cycle_layers"}
    layer2 = {"D": "cycle_date_format", "T": "iterate_skills"}
    layer3 = {"D": "", "T": "iterate_links"}
    layers = (base, layer2, layer3)

    assert resolve_layer_binding("D", layer2, layers) == "cycle_layers"
    assert resolve_layer_binding("D", layer3, layers) == "cycle_layers"
