from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QStackedWidget, QTabBar, QWidget

from jaw.desktop.smart_capture_window import MainWindow


def test_hiding_active_qna_returns_capture_to_parsed() -> None:
    app = QApplication.instance() or QApplication([])
    tabs = QTabBar()
    pages = QStackedWidget()
    for label in ("Parsed", "Captured", "Review", "Fixtures", "Q&A"):
        tabs.addTab(label)
        pages.addWidget(QWidget())
    harness = type("Harness", (), {})()
    harness.capture_tabs = tabs
    harness.capture_tab_pages = pages
    harness.capture_parsed_tab = 0
    harness.capture_qna_tab = 4
    tabs.setCurrentIndex(4)
    pages.setCurrentIndex(4)

    MainWindow._set_capture_qna_visibility(harness, False)
    app.processEvents()

    assert not tabs.isTabVisible(4)
    assert tabs.currentIndex() == 0
    assert pages.currentIndex() == 0


def test_hiding_inactive_qna_preserves_current_capture_tab() -> None:
    app = QApplication.instance() or QApplication([])
    tabs = QTabBar()
    pages = QStackedWidget()
    for label in ("Parsed", "Captured", "Review", "Fixtures", "Q&A"):
        tabs.addTab(label)
        pages.addWidget(QWidget())
    harness = type("Harness", (), {})()
    harness.capture_tabs = tabs
    harness.capture_tab_pages = pages
    harness.capture_parsed_tab = 0
    harness.capture_qna_tab = 4
    tabs.setCurrentIndex(2)
    pages.setCurrentIndex(2)

    MainWindow._set_capture_qna_visibility(harness, False)
    app.processEvents()

    assert tabs.currentIndex() == 2
    assert pages.currentIndex() == 2
