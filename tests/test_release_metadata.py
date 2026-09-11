from __future__ import annotations

import tomllib
from pathlib import Path

import jaw
from jaw.application.template_release_compat import current_jaw_version

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "0.1.1"


def test_package_version_metadata_is_synchronized() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["version"] == EXPECTED_VERSION
    assert jaw.__version__ == EXPECTED_VERSION
    assert current_jaw_version() == EXPECTED_VERSION


def test_release_docs_reference_current_source_version() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f"JAW `{EXPECTED_VERSION}` is the current source version" in readme
    assert f"## {EXPECTED_VERSION} — Unreleased" in changelog
