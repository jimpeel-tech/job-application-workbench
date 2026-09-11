from pathlib import Path

from jaw import paths


def test_jaw_home_override(monkeypatch, tmp_path: Path):
    home = tmp_path / "portable-jaw"
    monkeypatch.setenv("JAW_HOME", str(home))
    assert paths.app_home() == home.resolve()
    assert paths.config_path() == home.resolve() / "config.toml"
    assert paths.database_path() == home.resolve() / "data" / "jaw.db"
    assert paths.user_fonts_path() == home.resolve() / "fonts"
