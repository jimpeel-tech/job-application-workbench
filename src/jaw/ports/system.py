from __future__ import annotations

from typing import Protocol


class ClipboardPort(Protocol):
    """Read and write the system clipboard."""

    def read(self) -> str: ...

    def write(self, value: str) -> None: ...


class KeyboardPort(Protocol):
    """Observe and relay keyboard input outside JAW."""

    def is_key_down(self, key: str | int) -> bool: ...

    def copy_selection(self) -> None: ...

    def paste_clipboard(self) -> None: ...

    def relay_key(self, virtual_key: int) -> None: ...


class BrowserPort(Protocol):
    """Open a URL in the user's default browser."""

    def open(self, url: str) -> bool: ...


class WindowChromePort(Protocol):
    """Apply platform-specific state indicators to a native window."""

    def set_hotkey_indicator(
        self,
        window_id: int,
        *,
        disabled: bool,
        visible: bool,
    ) -> None: ...
