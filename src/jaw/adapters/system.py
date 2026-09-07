from __future__ import annotations

import ctypes
import sys
import webbrowser

import pyperclip


class PyperclipClipboard:
    def read(self) -> str:
        return str(pyperclip.paste())

    def write(self, value: str) -> None:
        pyperclip.copy(value)


class SystemKeyboard:
    """Windows keyboard adapter with harmless no-ops on other platforms."""

    _NAMED_KEYS = {
        "SHIFT": 0x10,
        "ESC": 0x1B,
        "ESCAPE": 0x1B,
        "ENTER": 0x0D,
        "RETURN": 0x0D,
        "SPACE": 0x20,
    }

    @classmethod
    def virtual_key(cls, key: str | int) -> int:
        if isinstance(key, int):
            return key
        normalized = key.strip().upper()
        if normalized in cls._NAMED_KEYS:
            return cls._NAMED_KEYS[normalized]
        if len(normalized) == 1:
            return ord(normalized)
        raise ValueError(f"Unsupported key: {key}")

    def is_key_down(self, key: str | int) -> bool:
        if sys.platform != "win32":
            return False
        return bool(
            ctypes.windll.user32.GetAsyncKeyState(self.virtual_key(key))
            & 0x8000
        )

    def copy_selection(self) -> None:
        self._modified_key(0x11, ord("C"))

    def paste_clipboard(self) -> None:
        self._modified_key(0x11, ord("V"))

    def relay_key(self, virtual_key: int) -> None:
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        user32.keybd_event(virtual_key, 0, 0, 0)
        user32.keybd_event(virtual_key, 0, 0x0002, 0)

    @staticmethod
    def _modified_key(modifier: int, key: int) -> None:
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        key_up = 0x0002
        user32.keybd_event(modifier, 0, 0, 0)
        user32.keybd_event(key, 0, 0, 0)
        user32.keybd_event(key, 0, key_up, 0)
        user32.keybd_event(modifier, 0, key_up, 0)


class SystemBrowser:
    def open(self, url: str) -> bool:
        return bool(webbrowser.open(url))


class SystemWindowChrome:
    """Windows DWM border indicator used for JAW's hotkey state."""

    def set_hotkey_indicator(
        self,
        window_id: int,
        *,
        disabled: bool,
        visible: bool,
    ) -> None:
        if sys.platform != "win32":
            return
        # Windows 11 DWM border color. COLORREF uses 0x00BBGGRR.
        color = ctypes.c_uint(
            0x003F3F7F if disabled and visible else 0xFFFFFFFF
        )
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            window_id,
            34,
            ctypes.byref(color),
            ctypes.sizeof(color),
        )
