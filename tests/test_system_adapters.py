import pytest

from jaw.adapters import SystemBrowser, SystemKeyboard, SystemWindowChrome
from jaw.adapters import system as system_adapters


def test_system_keyboard_resolves_supported_virtual_keys():
    assert SystemKeyboard.virtual_key("shift") == 0x10
    assert SystemKeyboard.virtual_key("Esc") == 0x1B
    assert SystemKeyboard.virtual_key("p") == ord("P")
    assert SystemKeyboard.virtual_key(0x26) == 0x26

    with pytest.raises(ValueError, match="Unsupported key"):
        SystemKeyboard.virtual_key("Page Up")


def test_system_adapters_are_safe_noops_off_windows(monkeypatch):
    monkeypatch.setattr(system_adapters.sys, "platform", "linux")
    keyboard = SystemKeyboard()

    assert keyboard.is_key_down("P") is False
    keyboard.copy_selection()
    keyboard.paste_clipboard()
    keyboard.relay_key(0x0D)
    SystemWindowChrome().set_hotkey_indicator(
        123,
        disabled=True,
        visible=True,
    )


def test_system_browser_delegates_to_default_browser(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        system_adapters.webbrowser,
        "open",
        lambda url: opened.append(url) or True,
    )

    assert SystemBrowser().open("https://example.test/") is True
    assert opened == ["https://example.test/"]
