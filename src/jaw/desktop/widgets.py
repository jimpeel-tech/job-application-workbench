"""Reusable native desktop widgets."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QDrag, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class Panel(QFrame):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("panel")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 14, 16, 16)
        self.layout.setSpacing(10)
        if title:
            heading = QLabel(title)
            heading.setObjectName("heading")
            self.layout.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("eyebrow")
            sub.setWordWrap(True)
            self.layout.addWidget(sub)


class WorkExperiencePanel(Panel):
    def __init__(self) -> None:
        super().__init__("")
        self.menu_button: QToolButton | None = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.menu_button is not None:
            self.menu_button.move(self.width() - self.menu_button.width() - 7, 0)
            self.menu_button.raise_()


class CollapsibleSettingsSection(QFrame):
    expanded = Signal(object)

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("settingsSection")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(4)
        self.header = QPushButton()
        self.header.setObjectName("settingsSectionHeader")
        self.header.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.header.setFixedHeight(27)
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.clicked.connect(self._toggle_content)
        layout.addWidget(self.header)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(5, 2, 5, 4)
        self.content_layout.setSpacing(7)
        layout.addWidget(self.content)
        self.title = title
        self._update_header()

    def _toggle_content(self, expanded: bool) -> None:
        self.content.setVisible(expanded)
        self._update_header()
        if expanded:
            self.expanded.emit(self)

    def set_expanded(self, expanded: bool) -> None:
        self.header.setChecked(expanded)
        self.content.setVisible(expanded)
        self._update_header()

    def _update_header(self) -> None:
        marker = "▾" if self.header.isChecked() else "▸"
        self.header.setText(f"{marker}  {self.title}")


class ContentFitComboBox(QComboBox):
    """Fit the closed control to its selection and its popup to all options."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.currentTextChanged.connect(lambda _text: self.updateGeometry())

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        text_width = self.fontMetrics().horizontalAdvance(self.currentText())
        return QSize(text_width + 42, hint.height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def showPopup(self) -> None:
        longest = max(
            (
                self.fontMetrics().horizontalAdvance(self.itemText(index))
                for index in range(self.count())
            ),
            default=0,
        )
        self.view().setMinimumWidth(longest + 34)
        super().showPopup()


class ClickableTextEdit(QTextEdit):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


class MatrixButton(QToolButton):
    def __init__(self) -> None:
        super().__init__()
        self.corner_icon = QLabel(self)
        self.corner_icon.setObjectName("matrixCornerIcon")
        self.corner_icon.setStyleSheet("background: transparent; border: none;")
        self.corner_icon.setFixedSize(18, 18)
        self.corner_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.corner_icon.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.corner_icon.move(self.width() - self.corner_icon.width() - 5, 5)
        self.corner_icon.raise_()


class HoverIconButton(QToolButton):
    def __init__(self) -> None:
        super().__init__()
        self.normal_icon = QIcon()
        self.hover_icon = QIcon()

    def set_state_icons(self, normal: QIcon, hover: QIcon) -> None:
        self.normal_icon = normal
        self.hover_icon = hover
        self.setIcon(normal)

    def enterEvent(self, event) -> None:
        self.setIcon(self.hover_icon)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setIcon(self.normal_icon)
        super().leaveEvent(event)


class HoverCycleStack(QFrame):
    """Bottom-anchored button stack that remains open while hovered."""

    expandedChanged = Signal(bool)

    def __init__(self, row_height: int, expanded_row_height: int = 32) -> None:
        super().__init__()
        self.setObjectName("statusCycleStack")
        self.row_height = row_height
        self.expanded_row_height = expanded_row_height
        self.expanded = False
        self.buttons: list[QToolButton] = []
        self.expand_timer = QTimer(self)
        self.expand_timer.setSingleShot(True)
        self.expand_timer.setInterval(90)
        self.expand_timer.timeout.connect(lambda: self.set_expanded(True))
        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.setInterval(170)
        self.collapse_timer.timeout.connect(self._collapse_if_pointer_left)
        self.resize(self.width(), row_height)

    def add_button(self, button: QToolButton) -> None:
        button.setParent(self)
        button.setProperty("flyoutEnabled", True)
        self.buttons.append(button)
        self._position_buttons()

    def set_button_enabled(self, button: QToolButton, enabled: bool) -> None:
        button.setProperty("flyoutEnabled", enabled)
        if not enabled:
            button.hide()
        self._position_buttons()

    def active_buttons(self) -> list[QToolButton]:
        return [button for button in self.buttons if button.property("flyoutEnabled")]

    def set_expanded(self, expanded: bool) -> None:
        if self.expanded == expanded:
            return
        self.expanded = expanded
        self.expandedChanged.emit(expanded)

    def enterEvent(self, event) -> None:
        self.collapse_timer.stop()
        self.expand_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.expand_timer.stop()
        self.collapse_timer.start()
        super().leaveEvent(event)

    def _collapse_if_pointer_left(self) -> None:
        if not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self.set_expanded(False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_buttons()

    def _position_buttons(self) -> None:
        row_height = self.expanded_row_height if self.expanded else self.row_height
        for offset, button in enumerate(reversed(self.active_buttons()), 1):
            button.setGeometry(
                0,
                self.height() - row_height * offset,
                self.width(),
                row_height,
            )


class ChildIteratorButton(QPushButton):
    toggleRequested = Signal(str)
    fieldDropped = Signal(str, str)

    def __init__(self, field_name: str, label: str) -> None:
        super().__init__(label)
        self.field_name = field_name
        self._drag_start = QPoint()
        self.setAcceptDrops(True)
        self.setProperty("childIterator", "true")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.toggleRequested.emit(self.field_name)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not event.buttons() & Qt.MouseButton.LeftButton:
            return super().mouseMoveEvent(event)
        if (
            event.position().toPoint() - self._drag_start
        ).manhattanLength() < QApplication.startDragDistance():
            return
        mime = QMimeData()
        mime.setData("application/x-jaw-child-iterator", self.field_name.encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)
        self.setDown(False)
        self.update()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-jaw-child-iterator"):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        source = bytes(
            event.mimeData().data("application/x-jaw-child-iterator")
        ).decode()
        if source and source != self.field_name:
            self.fieldDropped.emit(source, self.field_name)
        event.acceptProposedAction()


class WorkExperienceList(QListWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("workExperienceList")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.text() and event.text().isprintable():
            event.accept()
            return
        super().keyPressEvent(event)
