from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from jaw.web.assets import static_asset_for

NODE = shutil.which("node")


def _site_commands() -> str:
    return static_asset_for("/site-commands.js").read().decode("utf-8")


def test_tracker_help_explains_document_routing() -> None:
    javascript = _site_commands()

    assert "Job Tracker Help" in javascript
    assert "data-tracker-help" in javascript
    assert "Ctrl" in javascript and "<kbd>P</kbd>" in javascript
    assert "Generate Document" in javascript
    assert "Document Routing" in javascript
    assert "Manage Document Routing →" in javascript
    assert "window.JawDocumentGeneration.open()" in javascript
    assert "MutationObserver(installTrackerHelpButton)" in javascript


@pytest.mark.skipif(NODE is None, reason="Node.js is required for JavaScript syntax checks")
def test_site_commands_is_valid_javascript(tmp_path: Path) -> None:
    path = tmp_path / "site-commands.js"
    path.write_text(_site_commands(), encoding="utf-8")
    result = subprocess.run(
        [str(NODE), "--check", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
