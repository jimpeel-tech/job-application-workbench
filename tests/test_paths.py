from pathlib import Path

from jaw import paths


def test_jaw_home_override(monkeypatch, tmp_path: Path):
    home = tmp_path / "portable-jaw"
    monkeypatch.setenv("JAW_HOME", str(home))
    assert paths.app_home() == home.resolve()
    assert paths.config_path() == home.resolve() / "config.toml"
    assert paths.database_path() == home.resolve() / "data" / "jaw.db"
    assert paths.user_fonts_path() == home.resolve() / "fonts"


def test_installed_jaw_uses_local_app_data_for_user_fonts(monkeypatch, tmp_path: Path):
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.delenv("JAW_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(paths, "source_root", lambda: None)

    assert paths.app_home() == local_app_data / "JAW"
    assert paths.user_fonts_path() == local_app_data / "JAW" / "fonts"
