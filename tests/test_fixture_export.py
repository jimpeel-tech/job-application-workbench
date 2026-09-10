import json

import pytest

from jaw.fixture_export import FixtureExportError, export_snapshot


def _write_snapshot(root, fixture_id, created_at):
    folder = root / ".jaw-dev" / "fixtures" / fixture_id
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "format": "jaw-smart-capture-snapshot",
                "version": 4,
                "fixture_id": fixture_id,
                "status": "captured",
                "created_at": created_at,
                "active_user_id": 7,
                "active_user_name": "Any User",
                "expected_values": "not-set",
            }
        ),
        encoding="utf-8",
    )
    (folder / "captures.json").write_text(
        json.dumps({"captures": [{"number": 1, "content": "Senior Platform Engineer"}]}),
        encoding="utf-8",
    )
    return folder


def test_export_snapshot_copies_latest_to_private_inbox_and_removes_identity(tmp_path):
    workspace = tmp_path / "job-application-workbench"
    fixture_repo = tmp_path / "jaw-fixtures"
    workspace.mkdir()
    fixture_repo.mkdir()
    _write_snapshot(workspace, "older", "2026-09-10T10:00:00-05:00")
    _write_snapshot(workspace, "newer", "2026-09-10T11:00:00-05:00")

    destination = export_snapshot(workspace, fixture_repo)

    assert destination == fixture_repo / "inbox" / "newer"
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["fixture_id"] == "newer"
    assert manifest["status"] == "inbox"
    assert manifest["exported_for_review"] is True
    assert "active_user_id" not in manifest
    assert "active_user_name" not in manifest
    assert (destination / "captures.json").is_file()


def test_export_snapshot_refuses_expected_values(tmp_path):
    workspace = tmp_path / "job-application-workbench"
    fixture_repo = tmp_path / "jaw-fixtures"
    workspace.mkdir()
    fixture_repo.mkdir()
    source = _write_snapshot(workspace, "fixture-1", "2026-09-10T10:00:00-05:00")
    (source / "expected.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FixtureExportError, match="expected values"):
        export_snapshot(workspace, fixture_repo, "fixture-1")


def test_export_snapshot_refuses_to_overwrite_existing_inbox_fixture(tmp_path):
    workspace = tmp_path / "job-application-workbench"
    fixture_repo = tmp_path / "jaw-fixtures"
    workspace.mkdir()
    fixture_repo.mkdir()
    _write_snapshot(workspace, "fixture-1", "2026-09-10T10:00:00-05:00")
    existing = fixture_repo / "inbox" / "fixture-1"
    existing.mkdir(parents=True)

    with pytest.raises(FixtureExportError, match="already exists"):
        export_snapshot(workspace, fixture_repo, "fixture-1")
