from pathlib import Path

from jaw.config import load_config
from jaw.smart_capture import (
    default_smart_capture_settings,
    normalize_smart_capture_settings,
)


def test_smart_capture_defaults_to_parser_without_provider_dependency():
    assert default_smart_capture_settings()["analysis_mode"] == "parser"
    assert normalize_smart_capture_settings(None)["analysis_mode"] == "parser"


def test_fresh_runtime_config_serializes_parser_mode(tmp_path: Path):
    config_path = tmp_path / "config.toml"

    config = load_config(config_path)

    assert config.smart_capture_settings["analysis_mode"] == "parser"
    assert 'analysis_mode = "parser"' in config_path.read_text(encoding="utf-8")


def test_invalid_smart_capture_mode_fails_closed_to_parser():
    settings = normalize_smart_capture_settings({"analysis_mode": "broken-mode"})

    assert settings["analysis_mode"] == "parser"


def test_explicit_ai_modes_remain_available():
    for mode in ("verify", "ollama", "enhanced"):
        assert normalize_smart_capture_settings({"analysis_mode": mode})[
            "analysis_mode"
        ] == mode
