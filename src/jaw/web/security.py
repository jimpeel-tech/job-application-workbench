from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlsplit

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _is_loopback_hostname(hostname: str | None) -> bool:
    value = str(hostname or "").strip().rstrip(".").casefold()
    if value == "localhost":
        return True
    if not value:
        return False
    try:
        return ip_address(value).is_loopback
    except ValueError:
        return False


def require_loopback_bind(host: str) -> None:
    """Reject accidental exposure of JAW's unauthenticated local dashboard."""
    if not _is_loopback_hostname(host):
        raise ValueError("JAW dashboard host must resolve to a loopback address")


def _host_and_port(value: str) -> tuple[str | None, int | None]:
    try:
        parsed = urlsplit(f"//{value}")
        return parsed.hostname, parsed.port
    except ValueError:
        return None, None


def _origin_host_and_port(value: str) -> tuple[str | None, int | None] | None:
    if not value or value == "null":
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.casefold() != "http" or not parsed.hostname:
            return None
        return parsed.hostname, parsed.port or 80
    except ValueError:
        return None


class LocalRequestGuardMixin:
    """Protect JAW's loopback API from DNS rebinding and cross-site mutations."""

    def parse_request(self) -> bool:
        if not super().parse_request():
            return False

        expected_port = int(self.server.server_address[1])
        host, port = _host_and_port(self.headers.get("Host", ""))
        if not _is_loopback_hostname(host) or port != expected_port:
            self.send_error(403, "Forbidden")
            return False

        if self.command in _MUTATING_METHODS:
            origin = self.headers.get("Origin")
            if origin:
                parsed_origin = _origin_host_and_port(origin)
                if (
                    parsed_origin is None
                    or not _is_loopback_hostname(parsed_origin[0])
                    or parsed_origin[1] != expected_port
                ):
                    self.send_error(403, "Forbidden")
                    return False

        return True
