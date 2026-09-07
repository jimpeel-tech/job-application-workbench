from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QThread, Signal


class MatrixHotkeys(QThread):
    """Register single-key Windows hotkeys while JAW is running."""

    pressed = Signal(str)
    registration_failed = Signal(str)

    VK_CODES = {"SPACE": 0x20, "ENTER": 0x0D, "ESC": 0x1B}
    WM_SET_ENABLED = 0x8002
    WM_SET_SUSPENDED = 0x8003

    def __init__(
        self,
        base_keys: list[str],
        layer_keys: list[str],
        always_layer_keys: list[str] | None = None,
        special_hotkeys: dict[str, str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.base_keys = base_keys
        self.layer_keys = layer_keys
        self.always_layer_keys = set(always_layer_keys or [])
        self.special_hotkeys = dict(special_hotkeys or {})
        self._thread_id = 0
        self._enabled_requested = True
        self._suspended_requested = False

    def run(self) -> None:
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        registered: set[int] = set()
        id_to_key: dict[int, str] = {}
        offset = len(self.base_keys)
        modifier_flag = 0x0004  # Shift is JAW's fixed momentary Layer 2 key.
        special_offset = offset + len(self.layer_keys)

        def parse_hotkey(combo: str) -> tuple[str, int]:
            parts = [part.strip().upper() for part in combo.split("+") if part.strip()]
            modifiers = 0
            flags = {"ALT": 0x0001, "CTRL": 0x0002, "SHIFT": 0x0004, "WIN": 0x0008}
            for part in parts[:-1]:
                modifiers |= flags.get(part, 0)
            return (parts[-1] if parts else ""), modifiers

        def register(hotkey_id: int, key: str, modifiers: int, signal_key: str) -> None:
            if hotkey_id in registered:
                return
            vk_code = self.VK_CODES.get(key, 0x70 + int(key[1:]) - 1 if key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24 else ord(key) if len(key) == 1 else 0)
            if user32.RegisterHotKey(None, hotkey_id, 0x4000 | modifiers, vk_code):
                registered.add(hotkey_id)
                id_to_key[hotkey_id] = signal_key
            else:
                self.registration_failed.emit(signal_key)

        def unregister(hotkey_id: int) -> None:
            if hotkey_id in registered:
                user32.UnregisterHotKey(None, hotkey_id)
                registered.discard(hotkey_id)
                id_to_key.pop(hotkey_id, None)

        def set_main_registrations(enabled: bool) -> None:
            enabled = enabled and not self._suspended_requested
            for hotkey_id, key in enumerate(self.base_keys, start=1):
                if enabled:
                    register(hotkey_id, key, 0, key)
                else:
                    unregister(hotkey_id)
            for layer_index, key in enumerate(self.layer_keys, start=1):
                hotkey_id = offset + layer_index
                if enabled or key in self.always_layer_keys:
                    register(hotkey_id, key, modifier_flag, f"LAYER+{key}")
                else:
                    unregister(hotkey_id)
        def set_special_registrations() -> None:
            for index, (name, combo) in enumerate(self.special_hotkeys.items(), start=1):
                hotkey_id = special_offset + index
                unregister(hotkey_id)
                if not combo or (self._suspended_requested and name != "window"):
                    continue
                key, modifiers = parse_hotkey(combo)
                if key:
                    register(hotkey_id, key, modifiers, f"SPECIAL:{name}")

        set_main_registrations(self._enabled_requested)
        set_special_registrations()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:
                key = id_to_key.get(int(msg.wParam))
                if key:
                    self.pressed.emit(key)
            elif msg.message == self.WM_SET_ENABLED:
                self._enabled_requested = bool(msg.wParam)
                set_main_registrations(self._enabled_requested)
                set_special_registrations()
            elif msg.message == self.WM_SET_SUSPENDED:
                self._suspended_requested = bool(msg.wParam)
                set_main_registrations(self._enabled_requested)
                set_special_registrations()
        for hotkey_id in registered:
            user32.UnregisterHotKey(None, hotkey_id)

    def stop(self) -> None:
        if self._thread_id and sys.platform == "win32":
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        self.wait(1000)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled_requested = enabled
        if self._thread_id and sys.platform == "win32":
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id, self.WM_SET_ENABLED, int(enabled), 0
            )

    def set_suspended(self, suspended: bool) -> None:
        self._suspended_requested = suspended
        if self._thread_id and sys.platform == "win32":
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id, self.WM_SET_SUSPENDED, int(suspended), 0
            )


def paste_clipboard() -> None:
    """Send Ctrl+V to the currently focused Windows form control."""
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    key_up = 0x0002
    user32.keybd_event(0x11, 0, 0, 0)
    user32.keybd_event(ord("V"), 0, 0, 0)
    user32.keybd_event(ord("V"), 0, key_up, 0)
    user32.keybd_event(0x11, 0, key_up, 0)


def copy_selection() -> None:
    """Send Ctrl+C to the currently focused Windows control."""
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    key_up = 0x0002
    user32.keybd_event(0x11, 0, 0, 0)
    user32.keybd_event(ord("C"), 0, 0, 0)
    user32.keybd_event(ord("C"), 0, key_up, 0)
    user32.keybd_event(0x11, 0, key_up, 0)


def relay_key(vk_code: int) -> None:
    """Send one non-text key to the focused control."""
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    user32.keybd_event(vk_code, 0, 0, 0)
    user32.keybd_event(vk_code, 0, 0x0002, 0)
