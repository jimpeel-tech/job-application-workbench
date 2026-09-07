from jaw.desktop.smart_capture_window import MainWindow as SmartCaptureWindow
from jaw.main import MainWindow as BaseMainWindow


def test_production_window_inherits_rolodex_cursor_renderer():
    assert SmartCaptureWindow._update_cursor_badge is BaseMainWindow._update_cursor_badge
