from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from jaw.web.assets import _DASHBOARD_JAVASCRIPT, static_asset_for

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required for JavaScript syntax checks")


def _check_javascript(source: str, path: Path) -> None:
    path.write_text(source, encoding="utf-8")
    result = subprocess.run(
        [str(NODE), "--check", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_dashboard_source_is_valid_javascript(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/jaw/dashboard.js").read_text(encoding="utf-8")
    _check_javascript(source, tmp_path / "dashboard-source.js")


def test_served_dashboard_bundle_is_valid_javascript(tmp_path: Path) -> None:
    _check_javascript(_DASHBOARD_JAVASCRIPT, tmp_path / "dashboard-served.js")


def test_custom_workspace_is_valid_javascript(tmp_path: Path) -> None:
    source = static_asset_for("/custom-workspace.js").read().decode("utf-8")
    _check_javascript(source, tmp_path / "custom-workspace.js")


def test_capability_set_dashboard_contract_is_canonical() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/jaw/dashboard.js").read_text(encoding="utf-8")
    html = (root / "src/jaw/dashboard.html").read_text(encoding="utf-8")

    assert "includeCapability Sets" not in source
    assert "renderCapability Sets" not in source
    assert "stats.roles" not in source
    assert "stats.sets" in source
    assert "filter(rel => rel.type !== 'relevant_to')" in source
    assert 'id="rolesTab"' not in html
    assert 'id="rolesView"' not in html
    assert "$('rolesView')" not in source
    assert "$('roleHelp')" not in source
    assert 'id="capSetDialog"' in html
