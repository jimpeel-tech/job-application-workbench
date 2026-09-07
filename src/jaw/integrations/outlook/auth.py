"""Microsoft identity authentication for JAW's Outlook integration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ...paths import app_home

GRAPH_SCOPES = ["Mail.ReadWrite"]
DEFAULT_TENANT = "common"


class OutlookAuth:
    """Small MSAL public-client wrapper with a local serialized token cache."""

    def __init__(
        self,
        client_id: str | None = None,
        tenant: str | None = None,
        cache_path: str | Path | None = None,
    ) -> None:
        self.client_id = (client_id or os.environ.get("JAW_OUTLOOK_CLIENT_ID", "")).strip()
        self.tenant = (tenant or os.environ.get("JAW_OUTLOOK_TENANT") or DEFAULT_TENANT).strip()
        self.cache_path = Path(cache_path or app_home() / "data" / "outlook-token-cache.json")
        self._app: Any | None = None
        self._cache: Any | None = None
        self._device_flow: dict[str, Any] | None = None

    @property
    def configured(self) -> bool:
        return bool(self.client_id)

    def _require_msal(self):
        try:
            import msal  # type: ignore
        except ImportError as error:
            raise RuntimeError(
                "Outlook integration requires MSAL. Run `pip install -e .` after pulling the update."
            ) from error
        return msal

    def _ensure_app(self):
        if not self.configured:
            raise RuntimeError(
                "Outlook is not configured. Set JAW_OUTLOOK_CLIENT_ID to the Microsoft Entra app client ID."
            )
        if self._app is not None:
            return self._app
        msal = self._require_msal()
        cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            try:
                cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        self._cache = cache
        authority = f"https://login.microsoftonline.com/{self.tenant}"
        self._app = msal.PublicClientApplication(
            self.client_id,
            authority=authority,
            token_cache=cache,
        )
        return self._app

    def _persist_cache(self) -> None:
        cache = self._cache
        if cache is None or not getattr(cache, "has_state_changed", False):
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(cache.serialize(), encoding="utf-8")
        try:
            self.cache_path.chmod(0o600)
        except OSError:
            pass

    def status(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "configured": False,
                "connected": False,
                "account": "",
                "message": "Set JAW_OUTLOOK_CLIENT_ID to connect Outlook.",
            }
        try:
            app = self._ensure_app()
            accounts = app.get_accounts()
        except RuntimeError as error:
            return {
                "configured": True,
                "connected": False,
                "account": "",
                "message": str(error),
            }
        account = accounts[0] if accounts else None
        username = str((account or {}).get("username", ""))
        return {
            "configured": True,
            "connected": bool(account),
            "account": username,
            "message": f"Connected as {username}" if username else "Outlook sign-in required.",
        }

    def access_token(self) -> str:
        app = self._ensure_app()
        for account in app.get_accounts():
            result = app.acquire_token_silent(GRAPH_SCOPES, account=account)
            self._persist_cache()
            if result and result.get("access_token"):
                return str(result["access_token"])
        raise RuntimeError("Outlook sign-in required.")

    def start_device_flow(self) -> dict[str, Any]:
        app = self._ensure_app()
        flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
        if "user_code" not in flow:
            detail = flow.get("error_description") or flow.get("error") or "unknown error"
            raise RuntimeError(f"Could not start Outlook sign-in: {detail}")
        self._device_flow = dict(flow)
        return {
            "user_code": str(flow.get("user_code", "")),
            "verification_uri": str(
                flow.get("verification_uri") or flow.get("verification_url") or ""
            ),
            "message": str(flow.get("message", "")),
            "expires_in": int(flow.get("expires_in", 0) or 0),
        }

    def complete_device_flow(self) -> dict[str, Any]:
        if not self._device_flow:
            raise RuntimeError("No Outlook sign-in is waiting to be completed.")
        app = self._ensure_app()
        flow = self._device_flow
        try:
            result = app.acquire_token_by_device_flow(flow)
        finally:
            self._device_flow = None
        self._persist_cache()
        if not result or "access_token" not in result:
            detail = (result or {}).get("error_description") or (result or {}).get("error")
            raise RuntimeError(f"Outlook sign-in failed: {detail or 'authorization was not completed'}")
        account = result.get("id_token_claims", {}) if isinstance(result, dict) else {}
        username = str(account.get("preferred_username") or account.get("email") or "")
        return {"ok": True, "account": username}

    def disconnect(self) -> None:
        if self.cache_path.exists():
            try:
                self.cache_path.unlink()
            except OSError as error:
                raise RuntimeError(f"Could not remove Outlook token cache: {error}") from error
        self._app = None
        self._cache = None
        self._device_flow = None


__all__ = ["DEFAULT_TENANT", "GRAPH_SCOPES", "OutlookAuth"]
