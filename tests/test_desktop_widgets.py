from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QToolButton

from jaw.desktop.cursor_badge import CursorBadge
from jaw.desktop.styles import STYLESHEET
from jaw.desktop.widgets import (
    ChildIteratorButton,
    CollapsibleSettingsSection,
    ContentFitComboBox,
    HoverCycleStack,
    MatrixButton,
    Panel,
    WorkExperienceList,
)


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_desktop_leaf_components_remain_available_from_main() -> None:
    from jaw import main

    assert main.STYLESHEET == STYLESHEET
    assert main.Panel is Panel
    assert main.MatrixButton is MatrixButton
    assert main.CursorBadge is CursorBadge


def test_panel_and_collapsible_section_preserve_presentation(qt_app) -> None:
    panel = Panel("Heading", "Supporting text")
    labels = panel.findChildren(QLabel)

    assert [label.text() for label in labels] == ["Heading", "Supporting text"]
    assert [label.objectName() for label in labels] == ["heading", "eyebrow"]

    section = CollapsibleSettingsSection("Display")
    assert section.header.text() == "▾  Display"
    section.set_expanded(False)
    assert section.header.text() == "▸  Display"
    assert section.content.isHidden()

    expanded = []
    section.expanded.connect(expanded.append)
    section.header.click()
    assert section.header.text() == "▾  Display"
    assert expanded == [section]


def test_content_combo_sizes_to_selected_text(qt_app) -> None:
    combo = ContentFitComboBox()
    combo.addItems(["Local", "A substantially longer provider name"])

    combo.setCurrentIndex(0)
    short_width = combo.sizeHint().width()
    combo.setCurrentIndex(1)

    assert combo.sizeHint().width() > short_width
    assert combo.minimumSizeHint() == combo.sizeHint()


def test_matrix_and_iterator_widgets_keep_their_properties(qt_app) -> None:
    matrix = MatrixButton()
    matrix.resize(100, 50)
    assert matrix.corner_icon.objectName() == "matrixCornerIcon"
    assert matrix.corner_icon.size().width() == 18

    child = ChildIteratorButton("company", "Company")
    assert child.field_name == "company"
    assert child.acceptDrops()
    assert child.property("childIterator") == "true"

    work_list = WorkExperienceList()
    assert work_list.objectName() == "workExperienceList"
    assert (
        work_list.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert work_list.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn


def test_hover_stack_tracks_enabled_buttons_and_expansion(qt_app) -> None:
    stack = HoverCycleStack(24, 32)
    first = QToolButton()
    second = QToolButton()
    stack.add_button(first)
    stack.add_button(second)

    changes = []
    stack.expandedChanged.connect(changes.append)
    stack.set_expanded(True)
    stack.set_expanded(True)

    assert stack.active_buttons() == [first, second]
    assert changes == [True]

    stack.set_button_enabled(first, False)
    assert stack.active_buttons() == [second]
    assert first.isHidden()


def test_capability_set_cycle_wraps_visible_choices(qt_app) -> None:
    from jaw.main import MainWindow

    class CycleHarness:
        def __init__(self) -> None:
            self.set_selector = QComboBox()
            self.set_selector.addItem("All Capabilities", "__all__")
            self.set_selector.addItem("Platform & SRE", "set_sre")
            self.set_cycle_button = QToolButton()
            self.tooltip_refreshes = 0

        def _apply_tooltips(self) -> None:
            self.tooltip_refreshes += 1

    harness = CycleHarness()
    harness.set_selector.setCurrentIndex(0)

    MainWindow._cycle_set(harness)
    assert harness.set_selector.currentData() == "set_sre"
    assert harness.set_cycle_button.text() == "Platform & SRE"

    MainWindow._cycle_set(harness)
    assert harness.set_selector.currentData() == "__all__"
    assert harness.set_cycle_button.text() == "All Capabilities"
    assert harness.tooltip_refreshes == 2


def test_cursor_badge_updates_and_clears_text(qt_app) -> None:
    badge = CursorBadge()
    try:
        assert badge.windowFlags() & Qt.WindowType.WindowTransparentForInput
        badge.update_badge("H")
        assert badge.text() == "H"
        badge.update_badge("")
        assert badge.isHidden()
    finally:
        badge.close()


def test_cursor_badge_renders_iterator_as_visible_rolodex(qt_app) -> None:
    badge = CursorBadge()
    try:
        badge.update_iterator(
            ["LinkedIn", "Portfolio", "GitHub", "Facebook", "X"],
            2,
        )
        qt_app.processEvents()

        rows = [
            row
            for row in badge.findChildren(QLabel, "cursorIteratorRow")
            if not row.isHidden()
        ]
        assert [row.text() for row in rows] == [
            "LinkedIn",
            "Portfolio",
            "GitHub",
            "Facebook",
            "X",
        ]
        sizes = [row.font().pointSizeF() for row in rows]
        assert sizes[2] > sizes[1] > sizes[0]
        assert sizes[2] > sizes[3] > sizes[4]
        assert badge.text() == "GitHub"
        assert badge.height() > max(row.height() for row in rows)
    finally:
        badge.close()


def test_cursor_badge_renders_nested_iterator_context(qt_app) -> None:
    badge = CursorBadge()
    try:
        badge.update_iterator(
            ["Company", "Title", "Start", "End", "Bullets"],
            1,
            context="Oracle · Cloud Solutions Architect",
        )
        qt_app.processEvents()

        context = badge.findChild(QLabel, "cursorIteratorContext")
        assert context is not None
        assert context.text() == "Oracle · Cloud Solutions Architect"
        assert not context.isHidden()
        assert context.alignment() & Qt.AlignmentFlag.AlignLeft
        rows = [
            row
            for row in badge.findChildren(QLabel, "cursorIteratorRow")
            if not row.isHidden()
        ]
        assert [row.text() for row in rows] == [
            "Company",
            "Title",
            "Start",
            "End",
        ]
        assert all(row.alignment() & Qt.AlignmentFlag.AlignLeft for row in rows)
        assert badge.text() == "Title"
    finally:
        badge.close()


def test_cursor_badge_renders_active_iterator_prefix_as_fixed_gutter(qt_app) -> None:
    badge = CursorBadge()
    try:
        badge.update_iterator(
            ["Company", "Title", "Start", "End", "Bullets"],
            1,
            active_prefix="1",
        )
        qt_app.processEvents()

        rows = [
            row
            for row in badge.findChildren(QLabel, "cursorIteratorRow")
            if not row.isHidden()
        ]
        gutters = [
            gutter
            for gutter in badge.findChildren(QLabel, "cursorIteratorGutter")
            if not gutter.isHidden()
        ]

        assert [row.text() for row in rows] == ["Company", "Title", "Start", "End"]
        assert len(gutters) == len(rows)
        assert gutters[0].text() == ""
        assert gutters[1].text() == (
            '<span style="color:#69d391">1</span>'
            '<span style="color:#65a6e8">&gt;</span>'
        )
        assert gutters[2].text() == ""
        assert gutters[3].text() == ""
        assert len({gutter.width() for gutter in gutters}) == 1

        row_x = [row.mapTo(badge, QPoint(0, 0)).x() for row in rows]
        assert len(set(row_x)) == 1
        assert badge.text() == "Title"
    finally:
        badge.close()
