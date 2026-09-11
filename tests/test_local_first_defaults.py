from pathlib import Path

from jaw.config import AppConfig, load_config
from jaw.userdata import UserDataStore


def test_app_config_defaults_to_local_analysis():
    assert AppConfig().analysis_mode == "local"


def test_first_run_seed_defaults_to_local_analysis(tmp_path: Path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")
    data = store.read()

    assert data["active_user_name"] == "Ol Sarge"
    assert data["analysis_settings"]["mode"] == "local"


def test_first_run_seed_defaults_capability_granularity_to_balanced(tmp_path: Path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")
    hierarchy = store.read()["capability_model"]["view_preferences"]["hierarchy"]

    assert hierarchy["section_granularity"] == 3
    assert hierarchy["entity_granularity"] == 3


def test_new_blank_user_defaults_to_local_analysis(tmp_path: Path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")

    user_id = store.create_user("Second", False)
    settings = store.read(user_id=user_id)["analysis_settings"]

    assert settings == {
        "mode": "local",
        "provider": "openai",
        "model": "gpt-5.6-terra",
    }


def test_missing_analysis_settings_fall_back_to_local():
    state = UserDataStore._stored_state({"user": {}})

    assert state["analysis_settings"] == {
        "mode": "local",
        "provider": "openai",
        "model": "gpt-5.6-terra",
    }


def test_user_data_template_defaults_to_local_analysis():
    template = UserDataStore.template_data()

    assert template["analysis_settings"]["mode"] == "local"


def test_explicit_generative_setting_is_preserved(tmp_path: Path):
    data_path = tmp_path / "data" / "jaw.db"
    store = UserDataStore(data_path)
    store.save_analysis_settings("generative", "ollama", "qwen3:14b")

    persisted = UserDataStore(data_path).read()["analysis_settings"]
    config = load_config(tmp_path / "config.toml")

    assert persisted == {
        "mode": "generative",
        "provider": "ollama",
        "model": "qwen3:14b",
    }
    assert config.analysis_mode == "generative"
    assert config.analysis_provider == "ollama"
    assert config.analysis_model == "qwen3:14b"


def test_invalid_analysis_mode_fails_safe_to_local(tmp_path: Path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")
    data = store.read()
    data["analysis_settings"] = {
        "mode": "legacy-mode",
        "provider": "ollama",
        "model": "qwen3:14b",
    }
    store.write(data)

    config = load_config(tmp_path / "config.toml")

    assert config.analysis_mode == "local"
    assert config.analysis_provider == "ollama"
    assert config.analysis_model == "qwen3:14b"


def test_replace_import_preserves_explicit_generative_setting(tmp_path: Path):
    source = UserDataStore(tmp_path / "source" / "jaw.db")
    source.save_analysis_settings("generative", "openai", "gpt-5.6-sol")
    exported = source.export_data()

    target = UserDataStore(tmp_path / "target" / "jaw.db")
    target.import_data(exported, "replace")

    assert target.read()["analysis_settings"] == {
        "mode": "generative",
        "provider": "openai",
        "model": "gpt-5.6-sol",
    }
