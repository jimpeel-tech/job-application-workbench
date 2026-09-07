"""Pointer-following status and iterator preview used by the desktop UI."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor, QFont, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QVBoxLayout

from .iterator_state import iterator_preview_rows

_PREVIEW_MAX_CHARS = 44


def _preview_label(value: str) -> str:
    text = " ".join(str(value).split())
    if len(text) <= _PREVIEW_MAX_CHARS:
        return text
    return text[: _PREVIEW_MAX_CHARS - 1].rstrip() + "…"


class CursorBadge(QFrame):
    """Click-through pointer overlay with compact status and iterator modes."""

    def __init__(self) -> None:
        super().__init__()
        self._content_key: object | None = None
        self._text_value = ""
        self.setObjectName("cursorBadge")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(
            "QFrame#cursorBadge { background: rgba(20, 24, 28, 205); "
            "border: 1px solid rgba(120, 168, 135, 105); border-radius: 8px; }"
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 4, 8, 4)
        self._layout.setSpacing(0)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self._plain_label = QLabel(self)
        self._plain_label.setObjectName("cursorBadgePlain")
        self._plain_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._plain_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._plain_label.setStyleSheet(
            "QLabel#cursorBadgePlain { color: #78a887; background: transparent; "
            "border: 0; padding: 0; font-weight: 700; font-size: 11px; }"
        )
        self._layout.addWidget(
            self._plain_label,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        self._context_label = QLabel(self)
        self._context_label.setObjectName("cursorIteratorContext")
        self._context_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._context_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._context_label.setFixedHeight(16)
        self._context_label.setStyleSheet(
            "QLabel#cursorIteratorContext { color: #8a939e; background: transparent; "
            "border: 0; padding: 0; font-size: 9px; font-weight: 500; }"
        )
        self._context_label.hide()
        self._layout.addWidget(self._context_label, 0, Qt.AlignmentFlag.AlignLeft)

        self._iterator_lines: list[QFrame] = []
        self._iterator_gutters: list[QLabel] = []
        self._iterator_rows: list[QLabel] = []
        for _ in range(5):
            line = QFrame(self)
            line.setObjectName("cursorIteratorLine")
            line.setStyleSheet("QFrame#cursorIteratorLine { background: transparent; border: 0; }")
            line_layout = QHBoxLayout(line)
            line_layout.setContentsMargins(0, 0, 0, 0)
            line_layout.setSpacing(4)

            gutter = QLabel(line)
            gutter.setObjectName("cursorIteratorGutter")
            gutter.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            gutter.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            gutter.setStyleSheet(
                "QLabel#cursorIteratorGutter { background: transparent; border: 0; padding: 0; }"
            )

            row = QLabel(line)
            row.setObjectName("cursorIteratorRow")
            row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            row.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

            line_layout.addWidget(gutter, 0)
            line_layout.addWidget(row, 0)
            line.hide()
            gutter.hide()
            row.hide()
            self._layout.addWidget(line, 0, Qt.AlignmentFlag.AlignLeft)
            self._iterator_lines.append(line)
            self._iterator_gutters.append(gutter)
            self._iterator_rows.append(row)

    def text(self) -> str:
        """Return the currently displayed logical value for compatibility."""
        return self._text_value

    def _hide_iterator_rows(self) -> None:
        for line, gutter, row in zip(
            self._iterator_lines,
            self._iterator_gutters,
            self._iterator_rows,
            strict=True,
        ):
            line.hide()
            gutter.hide()
            row.hide()

    @staticmethod
    def _style_iterator_row(row: QLabel, distance: int) -> int:
        depth = abs(distance)
        if depth == 0:
            color, points, weight, line_height = "#69d391", 15.0, QFont.Weight.Bold, 28
        elif depth == 1:
            color, points, weight, line_height = "#aeb5bf", 11.0, QFont.Weight.Medium, 21
        else:
            color, points, weight, line_height = "#727b86", 8.5, QFont.Weight.Normal, 17

        font = row.font()
        font.setPointSizeF(points)
        font.setWeight(weight)
        row.setFont(font)
        row.setFixedHeight(line_height)
        row.setStyleSheet(
            f"QLabel#cursorIteratorRow {{ color: {color}; background: transparent; "
            "border: 0; padding: 0; }"
        )
        return line_height

    def _active_gutter_font(self) -> QFont:
        font = self.font()
        font.setPointSizeF(15.0)
        font.setWeight(QFont.Weight.Bold)
        return font

    def _refresh_geometry(self) -> None:
        self._layout.invalidate()
        self._layout.activate()
        self.adjustSize()

    def _move_and_show(self, y_offset: int = 18) -> None:
        cursor = QCursor.pos()
        x = cursor.x() + 18
        y = cursor.y() + y_offset
        screen = QGuiApplication.screenAt(cursor)
        if screen is not None:
            bounds = screen.availableGeometry()
            x = max(bounds.left(), min(x, bounds.right() - self.width() + 1))
            y = max(bounds.top(), min(y, bounds.bottom() - self.height() + 1))
        self.move(QPoint(x, y))
        if not self.isVisible():
            self.show()

    def update_badge(self, text: str) -> None:
        """Show the original compact single-value badge, or hide for blank text."""
        if not text:
            self._content_key = None
            self._text_value = ""
            self.hide()
            return

        value = _preview_label(text)
        key = ("badge", value)
        if self._content_key != key:
            self._content_key = key
            self._text_value = value
            self._context_label.hide()
            self._hide_iterator_rows()
            self._plain_label.setText(value)
            self._plain_label.show()
            self._refresh_geometry()
        self._move_and_show(18)

    def update_iterator(
        self,
        values: Sequence[str],
        current_index: int,
        *,
        context: str = "",
        active_prefix: str = "",
    ) -> None:
        """Show neighboring iterator items with optional context or active gutter."""
        rows = iterator_preview_rows(values, current_index)
        if not rows:
            self._content_key = None
            self._text_value = ""
            self.hide()
            return

        context_value = _preview_label(context) if context else ""
        prefix_value = " ".join(str(active_prefix).split())
        key = ("iterator", context_value, prefix_value, tuple(rows))
        above_height = (16 if context_value else 0) + sum(
            21 if abs(distance) == 1 else 17
            for _value, distance in rows
            if distance < 0
        )
        if self._content_key != key:
            self._content_key = key
            self._text_value = next(
                (_preview_label(value) for value, distance in rows if distance == 0),
                "",
            )
            self._plain_label.hide()
            if context_value:
                self._context_label.setText(context_value)
                self._context_label.show()
            else:
                self._context_label.hide()
            self._hide_iterator_rows()

            gutter_font = self._active_gutter_font()
            gutter_width = 0
            if prefix_value:
                gutter_width = QFontMetrics(gutter_font).horizontalAdvance(
                    f"{prefix_value}>"
                )

            for line, gutter, label, (value, distance) in zip(
                self._iterator_lines,
                self._iterator_gutters,
                self._iterator_rows,
                rows,
                strict=False,
            ):
                rendered = _preview_label(value)
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setText(rendered)
                line_height = self._style_iterator_row(label, distance)
                line.setFixedHeight(line_height)

                if prefix_value:
                    gutter.setFont(gutter_font)
                    gutter.setFixedWidth(gutter_width)
                    gutter.setFixedHeight(line_height)
                    gutter.setTextFormat(Qt.TextFormat.RichText)
                    if distance == 0:
                        gutter.setText(
                            f'<span style="color:#69d391">{escape(prefix_value)}</span>'
                            '<span style="color:#65a6e8">&gt;</span>'
                        )
                    else:
                        gutter.setText("")
                    gutter.show()
                else:
                    gutter.hide()

                label.show()
                line.show()
            self._refresh_geometry()

        # Keep the active row adjacent to the pointer instead of anchoring the
        # pointer to the top of a taller nested preview.
        self._move_and_show(10 - above_height)
