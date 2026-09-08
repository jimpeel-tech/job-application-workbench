from types import SimpleNamespace

from jaw.main import MainWindow


class _FakeKeyboard:
    def __init__(self, *down: str):
        self.down = {key.upper() for key in down}

    def is_key_down(self, key: str) -> bool:
        return key.upper() in self.down


class _FakeWindow:
    def __init__(self, layer: str):
        self.layer = layer
        self.latched_layer = "Base"
        self._answer_search_active = False
        self._layer3_hold_key = ""
        self._layer3_hold_requires_shift = False
        self.keyboard = _FakeKeyboard()
        self.config = SimpleNamespace(
            layer2={"P": "first_name"},
            layer3={"P": "full_name"},
            matrix={"P": "portfolio"},
            hotkey_settings={
                "layers": {
                    "layer2": {"enabled": True, "hold": True},
                    "layer3": {"enabled": True},
                }
            },
        )
        self.calls: list[tuple] = []

    def _poll_sync_revisions(self, *, force: bool = False):
        self.calls.append(("sync", force))

    def trigger_layer2(self, key: str):
        self.calls.append(("layer2", key))

    def _dispatch_layer_action(self, bindings, key: str, layer: str):
        self.calls.append(("dispatch", bindings, key, layer))

    def _resolve_layer_binding(self, key, bindings):
        return bindings.get(key, "")

    def _dispatch_action(self, action, key, paste, source_layer=None):
        self.calls.append(("action", action, key, paste, source_layer))

    def _update_matrix_layer_name(self):
        self.calls.append(("layer", self.layer))


def test_shift_signal_uses_layer3_while_layer3_hold_is_active():
    window = _FakeWindow("Layer 3")

    MainWindow.handle_global_key(window, "LAYER+P")

    assert window.calls == [
        ("sync", True),
        ("dispatch", window.config.layer3, "P", "Layer 3"),
    ]


def test_shift_signal_still_uses_layer2_without_layer3_hold():
    window = _FakeWindow("Layer 2")

    MainWindow.handle_global_key(window, "LAYER+P")

    assert window.calls == [("sync", True), ("layer2", "P")]


def test_shift_registration_includes_layer3_only_targets():
    window = _FakeWindow("Base")
    window.config.matrix = {"A": "portfolio"}
    window.config.layer2 = {"A": "layer3_hold", "S": "city"}
    window.config.layer3 = {"P": "full_name"}

    base_keys, shifted_keys = MainWindow._matrix_hotkey_keys(window)

    assert base_keys == ["A", "P"]
    assert shifted_keys == ["A", "S", "P"]


def test_layer2_only_key_is_not_registered_as_bare_key():
    window = _FakeWindow("Base")
    window.config.matrix = {}
    window.config.layer2 = {"A": "layer3_hold"}
    window.config.layer3 = {}

    base_keys, shifted_keys = MainWindow._matrix_hotkey_keys(window)

    assert base_keys == []
    assert shifted_keys == ["A"]


def test_base_layer3_hold_does_not_require_shift():
    window = _FakeWindow("Base")
    window.keyboard = _FakeKeyboard("A")

    MainWindow._activate_layer3_hold(window, "A", "Base")

    assert window.layer == "Layer 3"
    assert window._layer3_hold_key == "A"
    assert window._layer3_hold_requires_shift is False
    assert MainWindow._layer3_hold_is_active(window, False) is True


def test_layer2_layer3_hold_requires_shift_chord_to_remain_active():
    window = _FakeWindow("Layer 2")
    window.keyboard = _FakeKeyboard("SHIFT", "A")

    MainWindow._activate_layer3_hold(window, "A", "Layer 2")

    assert window.layer == "Layer 3"
    assert window._layer3_hold_requires_shift is True
    assert MainWindow._layer3_hold_is_active(window, True) is True
    assert MainWindow._layer3_hold_is_active(window, False) is False


def test_layer3_hold_ends_when_trigger_key_is_released():
    window = _FakeWindow("Base")
    window.keyboard = _FakeKeyboard("A")
    MainWindow._activate_layer3_hold(window, "A", "Base")
    window.keyboard.down.clear()

    assert MainWindow._layer3_hold_is_active(window, False) is False
