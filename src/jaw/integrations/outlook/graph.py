"""Minimal Microsoft Graph mail client used by JAW Outlook sync."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .auth import OutlookAuth

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"

JAW_CATEGORIES = (
    "1 Application",
    "2 Rejected",
    "3 Recruiter",
    "4 Interview",
    "5 Offer",
    "9 Review",
)


def managed_categories(existing: list[str] | None, category: str) -> list[str]:
    """Replace JAW-managed categories while preserving the user's other categories."""
    kept = [value for value in (existing or []) if value not in JAW_CATEGORIES]
    if category and category not in kept:
        kept.append(category)
    return kept


class OutlookGraphClient:
    def __init__(self, auth: OutlookAuth, timeout: int = 30) -> None:
        self.auth = auth
        self.timeout = timeout

    @staticmethod
    def _prefer_header(*, text_body: bool = False) -> str:
        values = ['IdType="ImmutableId"']
        if text_body:
            values.insert(0, 'outlook.body-content-type="text"')
        return ", ".join(values)

    def _request(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        text_body: bool = False,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.auth.access_token()}",
            "Accept": "application/json",
            "Prefer": self._prefer_header(text_body=text_body),
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Microsoft Graph error {error.code}: {detail or error.reason}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            reason = getattr(error, "reason", error)
            raise RuntimeError(f"Could not reach Microsoft Graph: {reason}") from error
        if not payload:
            return {}
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as error:
            raise RuntimeError("Microsoft Graph returned invalid JSON") from error
        return decoded if isinstance(decoded, dict) else {}

    def list_messages(
        self,
        since: datetime,
        *,
        max_messages: int = 2500,
        page_size: int = 50,
    ) -> tuple[list[dict[str, Any]], bool]:
        since_text = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        query = urllib.parse.urlencode(
            {
                "$select": (
                    "id,internetMessageId,subject,from,receivedDateTime,"
                    "bodyPreview,categories,webLink"
                ),
                "$filter": f"receivedDateTime ge {since_text}",
                "$orderby": "receivedDateTime desc",
                "$top": str(max(1, min(int(page_size), 1000))),
            }
        )
        url = f"{GRAPH_ROOT}/me/messages?{query}"
        messages: list[dict[str, Any]] = []
        truncated = False
        while url:
            payload = self._request("GET", url)
            values = payload.get("value", [])
            if isinstance(values, list):
                for index, value in enumerate(values):
                    if isinstance(value, dict):
                        messages.append(value)
                        if len(messages) >= max_messages:
                            truncated = (
                                index < len(values) - 1 or bool(payload.get("@odata.nextLink"))
                            )
                            return messages[:max_messages], truncated
            next_link = payload.get("@odata.nextLink")
            url = str(next_link) if next_link else ""
        return messages, truncated

    def get_message(self, message_id: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(message_id, safe="")
        query = urllib.parse.urlencode(
            {
                "$select": (
                    "id,internetMessageId,subject,from,receivedDateTime,body,"
                    "bodyPreview,categories,webLink"
                )
            }
        )
        return self._request(
            "GET",
            f"{GRAPH_ROOT}/me/messages/{encoded}?{query}",
            text_body=True,
        )

    def set_category(
        self,
        message_id: str,
        existing: list[str] | None,
        category: str,
    ) -> list[str]:
        categories = managed_categories(existing, category)
        encoded = urllib.parse.quote(message_id, safe="")
        self._request(
            "PATCH",
            f"{GRAPH_ROOT}/me/messages/{encoded}",
            body={"categories": categories},
        )
        return categories


__all__ = ["GRAPH_ROOT", "JAW_CATEGORIES", "OutlookGraphClient", "managed_categories"]
