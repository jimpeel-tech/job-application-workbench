from __future__ import annotations

import os
from pathlib import Path

DATABASE_SCHEMA_VERSION = 7


def source_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[2]
    return candidate if (candidate / "pyproject.toml").exists() else None


def app_home() -> Path:
    """Use the checkout during development and AppData when installed."""
    override = os.environ.get("JAW_HOME")
    if override:
        return Path(override).expanduser().resolve()
    checkout = source_root()
    if checkout:
        return checkout
    local = os.environ.get("LOCALAPPDATA")
    return (Path(local) / "JAW") if local else (Path.home() / ".jaw")


def config_path() -> Path:
    return app_home() / "config.toml"


def database_path() -> Path:
    return app_home() / "data" / "jaw.db"
