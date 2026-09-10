from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


class FixtureStore:
    """Local developer snapshots captured from the normal Smart Capture session.

    Snapshots preserve raw captures and deterministic parser observations, but
    intentionally never create or approve expected corpus values. Human-reviewed
    golden fixtures remain a separate concern.
    """

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.snapshot_root = self.workspace / ".jaw-dev" / "fixtures"
        self.snapshot_root.mkdir(parents=True, exist_ok=True)

    @property
    def available(self) -> bool:
        return (self.workspace / "pyproject.toml").exists()

    def snapshot_session(
        self,
        events: list[dict[str, Any]],
        parser_values: dict[str, tuple[str, ...]],
        ai_payload: dict[str, Any] | None,
        settings: dict[str, Any],
        *,
        active_user_id: int,
        active_user_name: str,
        parser_resolution: dict[str, Any] | None = None,
        merge_resolution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_events = [
            event
            for event in events
            if str(event.get("content", "")).strip()
        ]
        capture_count = len(source_events)
        captures = []
        for number, event in enumerate(source_events, start=1):
            metadata = self._event_metadata(event)
            captures.append(
                {
                    "number": number,
                    "event_id": event.get("id"),
                    "content_type": str(event.get("content_type", "unclassified")),
                    "classification_status": str(event.get("classification_status", "")),
                    "content": str(event.get("content", "")).strip(),
                    "metadata": metadata,
                    "session_position": {
                        "sequence": number,
                        "capture_count": capture_count,
                        "is_first": number == 1,
                        "is_last": number == capture_count,
                    },
                }
            )
        if not captures:
            raise ValueError("Capture at least one selection before saving a fixture")

        now = datetime.now().astimezone()
        fixture_id = f"{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        folder = self.snapshot_root / fixture_id
        folder.mkdir(parents=True, exist_ok=False)
        combined = "\n\n".join(item["content"] for item in captures).strip()
        manifest = {
            "format": "jaw-smart-capture-snapshot",
            "version": 4,
            "fixture_id": fixture_id,
            "status": "captured",
            "created_at": now.isoformat(timespec="seconds"),
            "active_user_id": int(active_user_id),
            "active_user_name": str(active_user_name),
            "analysis_mode": str(settings.get("analysis_mode", "parser")),
            "ollama_model": str(settings.get("ollama_model", "")),
            "capture_count": len(captures),
            "expected_values": "not-set",
        }
        parser_document = {key: list(values) for key, values in parser_values.items() if values}

        self._write_json(folder / "manifest.json", manifest)
        self._write_json(folder / "captures.json", {"captures": captures})
        self._write_json(folder / "parser.json", parser_document)
        if parser_resolution:
            self._write_json(folder / "parser_resolution.json", dict(parser_resolution))
        if merge_resolution:
            self._write_json(folder / "merge_resolution.json", dict(merge_resolution))
        if ai_payload:
            self._write_json(folder / "ollama.json", dict(ai_payload))
        (folder / "combined.txt").write_text(combined + "\n", encoding="utf-8")

        return {
            "manifest": manifest,
            "captures": captures,
            "parser": parser_document,
            "parser_resolution": dict(parser_resolution or {}),
            "merge_resolution": dict(merge_resolution or {}),
            "ollama": dict(ai_payload or {}),
            "path": str(folder),
        }

    def list_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        items = [self._read_json(path) for path in self.snapshot_root.glob("*/manifest.json")]
        items = [item for item in items if item.get("fixture_id")]
        return sorted(
            items,
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )[: max(0, int(limit))]

    @staticmethod
    def _event_metadata(event: dict[str, Any]) -> dict[str, Any]:
        raw = event.get("metadata", {})
        if isinstance(raw, dict):
            return dict(raw)
        try:
            parsed = json.loads(str(raw))
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
