"""HTTP-route adapter for the local JAW dashboard Outlook integration."""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from typing import Any

from ...config import DEFAULT_BEHAVIOR, default_config_path
from .service import OutlookSyncService


def outlook_sync_enabled() -> bool:
    """Return whether Outlook sync is explicitly enabled in config.toml."""
    config_path = default_config_path()
    if not config_path.exists():
        return bool(DEFAULT_BEHAVIOR["outlook_sync_enabled"])
    try:
        with config_path.open("rb") as config_file:
            stored = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError, TypeError, ValueError):
        return bool(DEFAULT_BEHAVIOR["outlook_sync_enabled"])
    behavior = stored.get("behavior", {})
    return bool(
        behavior.get(
            "outlook_sync_enabled",
            DEFAULT_BEHAVIOR["outlook_sync_enabled"],
        )
    )


class OutlookWebController:
    def __init__(
        self,
        service: OutlookSyncService,
        *,
        enabled: Callable[[], bool] | None = None,
    ) -> None:
        self.service = service
        self.enabled = enabled or outlook_sync_enabled

    def get(self, path: str, user_id: int) -> tuple[dict[str, Any], int] | None:
        if path != "/api/outlook/status":
            return None
        if not self.enabled():
            return {"enabled": False}, 200
        result = self.service.status(user_id)
        result["enabled"] = True
        return result, 200

    def post(
        self,
        path: str,
        payload: dict[str, Any],
        user_id: int,
    ) -> tuple[dict[str, Any], int] | None:
        if not path.startswith("/api/outlook/"):
            return None
        if not self.enabled():
            return {
                "error": (
                    "Outlook sync is disabled in config.toml. Set "
                    "outlook_sync_enabled = true under [behavior]."
                )
            }, 403
        try:
            if path == "/api/outlook/auth/start":
                return self.service.start_auth(), 200
            if path == "/api/outlook/auth/complete":
                result = self.service.complete_auth()
                result["status"] = self.service.status(user_id)
                return result, 200
            if path == "/api/outlook/disconnect":
                self.service.disconnect()
                return {"ok": True, "status": self.service.status(user_id)}, 200
            if path == "/api/outlook/reset":
                return self.service.reset(user_id), 200
            if path == "/api/outlook/sync":
                result = self.service.sync(
                    user_id,
                    days=int(payload.get("days", 30)),
                    max_messages=int(payload.get("max_messages", 2500)),
                )
                return result, 200 if result.get("ok") else 207
        except (RuntimeError, ValueError) as error:
            return {"error": str(error)}, 503 if isinstance(error, RuntimeError) else 400
        return None


__all__ = ["OutlookWebController", "outlook_sync_enabled"]
