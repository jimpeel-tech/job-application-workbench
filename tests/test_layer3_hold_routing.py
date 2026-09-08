from types import SimpleNamespace

from jaw.main import MainWindow


class _FakeWindow:
    def __init__(self, layer: str):
        self.layer = layer
        self._answer_search_active = False
        self.config = SimpleNamespace(
            layer2={"P": "first_name"},
            layer3={"P": "full_name"},
            matrix={"P": "portfolio"},
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

    def _dispatch_action(self, action, key, paste):
        self.calls.append(("action", action, key, paste))


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
