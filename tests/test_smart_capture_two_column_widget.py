import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QListWidgetItem

from jaw.main import TwoColumnListWidget


def test_smart_capture_field_widget_renders_two_columns_without_inner_scrollbar():
    app = QApplication.instance() or QApplication([])
    widget = TwoColumnListWidget()
    widget.resize(420, 200)
    for index in range(8):
        widget.addItem(QListWidgetItem(f"Field {index}"))

    widget.show()
    app.processEvents()
    widget._refresh_grid_size()
    app.processEvents()

    first = widget.visualItemRect(widget.item(0))
    second = widget.visualItemRect(widget.item(1))
    third = widget.visualItemRect(widget.item(2))

    assert first.y() == second.y()
    assert second.x() > first.x()
    assert third.y() > first.y()
    assert widget.verticalScrollBar().maximum() == 0

    widget.close()
