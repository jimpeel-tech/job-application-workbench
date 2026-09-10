from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


class FixtureExportError(RuntimeError):
    """A local Smart Capture snapshot cannot be exported safely."""


def default_fixture_repository(workspace: Path) -> Path:
    """Resolve the private fixture repository without hard-coding a user path."""
    explicit = os.getenv("JAW_FIXTURE_REPO", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (Path(workspace).resolve().parent / "jaw-fixtures").resolve()


def export_snapshot(
    workspace: Path,
    fixture_repository: Path | None = None,
    fixture_id: str | None = None,
) -> Path:
    """Copy one observation-only Smart Capture snapshot into the private inbox."""
    workspace = Path(workspace).resolve()
    snapshot_root = workspace / ".jaw-dev" / "fixtures"
    repository = _resolve_repository(workspace, fixture_repository)

    source = _select_snapshot(snapshot_root, fixture_id)
    return _export_source(source, repository)


def export_all_snapshots(
    workspace: Path,
    fixture_repository: Path | None = None,
) -> list[Path]:
    """Export every snapshot not already present in the private fixture inbox."""
    workspace = Path(workspace).resolve()
    snapshot_root = workspace / ".jaw-dev" / "fixtures"
    repository = _resolve_repository(workspace, fixture_repository)
    destination_root = repository / "inbox"
    destination_root.mkdir(parents=True, exist_ok=True)

    exported: list[Path] = []
    for _created_at, source in _snapshot_candidates(snapshot_root):
        manifest = _read_manifest(source / "manifest.json")
        fixture_id = str(manifest.get("fixture_id", ""))
        if fixture_id and (destination_root / fixture_id).exists():
            continue
        exported.append(_export_source(source, repository))
    return exported


def _resolve_repository(workspace: Path, fixture_repository: Path | None) -> Path:
    repository = (
        Path(fixture_repository).expanduser().resolve()
        if fixture_repository is not None
        else default_fixture_repository(workspace)
    )
    if not repository.exists():
        raise FixtureExportError(
            f"Fixture repository does not exist: {repository}. "
            "Clone jaw-fixtures beside JAW or set JAW_FIXTURE_REPO."
        )
    return repository


def _export_source(source: Path, repository: Path) -> Path:
    manifest = _read_manifest(source / "manifest.json")
    _validate_snapshot(source, manifest)

    resolved_id = str(manifest["fixture_id"])
    destination_root = repository / "inbox"
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / resolved_id
    if destination.exists():
        raise FixtureExportError(f"Fixture already exists in inbox: {resolved_id}")

    shutil.copytree(source, destination)

    # User identity is useful to the local application but irrelevant to parser
    # ground truth. Keep the private corpus focused on capture behavior.
    exported_manifest = dict(manifest)
    exported_manifest.pop("active_user_id", None)
    exported_manifest.pop("active_user_name", None)
    exported_manifest["status"] = "inbox"
    exported_manifest["exported_for_review"] = True
    _write_json(destination / "manifest.json", exported_manifest)
    return destination


def _select_snapshot(snapshot_root: Path, fixture_id: str | None) -> Path:
    if fixture_id and fixture_id != "latest":
        source = snapshot_root / fixture_id
        if not source.is_dir():
            raise FixtureExportError(f"Smart Capture snapshot not found: {fixture_id}")
        return source

    candidates = _snapshot_candidates(snapshot_root)
    if not candidates:
        raise FixtureExportError(
            f"No Smart Capture snapshots found under {snapshot_root}"
        )
    return candidates[-1][1]


def _snapshot_candidates(snapshot_root: Path) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    for manifest_path in snapshot_root.glob("*/manifest.json"):
        manifest = _read_manifest(manifest_path)
        if manifest.get("fixture_id"):
            candidates.append((str(manifest.get("created_at", "")), manifest_path.parent))
    candidates.sort(key=lambda item: (item[0], item[1].name))
    return candidates


def _validate_snapshot(source: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("format") != "jaw-smart-capture-snapshot":
        raise FixtureExportError(f"Unsupported fixture format in {source}")
    if not manifest.get("fixture_id"):
        raise FixtureExportError(f"Fixture manifest is missing fixture_id: {source}")
    if manifest.get("expected_values") not in (None, "not-set"):
        raise FixtureExportError(
            "Local snapshots must remain observation-only before export"
        )
    if any(source.glob("*.expected.json")) or (source / "expected.json").exists():
        raise FixtureExportError(
            "Refusing to export a local snapshot containing expected values"
        )
    if not (source / "captures.json").is_file():
        raise FixtureExportError(f"Fixture is missing captures.json: {source}")


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FixtureExportError(f"Cannot read fixture manifest: {path}") from error
    if not isinstance(value, dict):
        raise FixtureExportError(f"Fixture manifest must be a JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
