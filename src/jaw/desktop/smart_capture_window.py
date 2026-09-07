from __future__ import annotations

import sys
import time

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from ..application import CaptureValidationError
from ..main import MainWindow as BaseMainWindow
from ..parser_resolution import resolve_parser_evidence
from ..smart_capture import (
    capture_tone,
    merge_capture_values,
    normalize_smart_capture_settings,
)
from .styles import STYLESHEET
from .workers import CaptureVerificationWorker


class MainWindow(BaseMainWindow):
    """Production desktop window with the flat, tabbed Smart Capture workspace."""

    _CAPTURE_FIXTURE_STATUS_DEFAULT = (
        "Snapshots stay local · expected corpus values are never auto-approved"
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._capture_verification_started_at: float | None = None
        self._capture_verification_elapsed_s: float | None = None

    def _settings_panel(self) -> QWidget:
        scroll = super()._settings_panel()

        # The field selector is one flat, compact two-column surface. InternalMove
        # still preserves the user's configured field order.
        self.smart_capture_field_list.setFlow(QListView.Flow.LeftToRight)
        self.smart_capture_field_list.setWrapping(True)
        self.smart_capture_field_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.smart_capture_field_list.setMovement(QListView.Movement.Snap)
        self.smart_capture_field_list.setUniformItemSizes(True)
        self.smart_capture_field_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.smart_capture_field_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.smart_capture_field_list.setFixedHeight(158)
        QTimer.singleShot(0, self._resize_smart_capture_field_grid)

        mode = self.smart_capture_analysis_mode
        mode.blockSignals(True)
        if mode.findData("ollama") < 0:
            enhanced_index = mode.findData("enhanced")
            mode.insertItem(
                enhanced_index if enhanced_index >= 0 else mode.count(),
                "Ollama only",
                "ollama",
            )
        enhanced_index = mode.findData("enhanced")
        if enhanced_index >= 0:
            mode.setItemText(enhanced_index, "Ollama enhanced")
        selected = normalize_smart_capture_settings(self.config.smart_capture_settings)[
            "analysis_mode"
        ]
        mode.setCurrentIndex(max(0, mode.findData(selected)))
        mode.blockSignals(False)
        self._update_smart_capture_controls()
        return scroll

    def _current_smart_capture_settings(self) -> dict:
        settings = super()._current_smart_capture_settings()
        current = normalize_smart_capture_settings(self.config.smart_capture_settings)
        settings["dev"] = bool(current["dev"])
        return normalize_smart_capture_settings(settings)

    def _update_smart_capture_controls(self) -> None:
        if not hasattr(self, "smart_capture_analysis_mode"):
            return
        mode = str(self.smart_capture_analysis_mode.currentData() or "verify")
        self.smart_capture_ollama_model.setEnabled(mode != "parser")
        self.smart_capture_fill_missing_check.setEnabled(mode == "verify")
        self.smart_capture_disagreement_check.setEnabled(mode in {"verify", "enhanced"})

    def _resize_smart_capture_field_grid(self) -> None:
        if not hasattr(self, "smart_capture_field_list"):
            return
        width = max(300, self.smart_capture_field_list.viewport().width())
        self.smart_capture_field_list.setGridSize(QSize(max(145, width // 2), 26))

    def _capture_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("settingsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        self.capture_session_status = QLabel("")
        self.capture_session_status.hide()

        self.capture_company_label = QLabel("")
        self.capture_company_label.setObjectName("captureCompany")
        self.capture_company_label.setWordWrap(True)
        self.capture_title_label = QLabel("")
        self.capture_title_label.setObjectName("captureTitle")
        self.capture_title_label.setWordWrap(True)
        layout.addWidget(self.capture_company_label)
        layout.addWidget(self.capture_title_label)

        self.capture_tabs = QTabBar()
        self.capture_tabs.setObjectName("captureTabs")
        self.capture_tabs.setExpanding(False)
        self.capture_tabs.setDrawBase(False)
        self.capture_tabs.setElideMode(Qt.TextElideMode.ElideRight)
        layout.addWidget(self.capture_tabs)

        self.capture_tab_pages = QStackedWidget()
        self.capture_tab_pages.setObjectName("captureTabPages")
        layout.addWidget(self.capture_tab_pages, 1)

        parsed_page = QWidget()
        parsed_layout = QVBoxLayout(parsed_page)
        parsed_layout.setContentsMargins(0, 0, 0, 0)
        parsed_layout.setSpacing(0)
        self.capture_fields_list = QListWidget()
        self.capture_fields_list.setObjectName("captureFieldsList")
        self.capture_fields_list.setWordWrap(True)
        parsed_layout.addWidget(self.capture_fields_list, 1)
        self.capture_parsed_tab = self._add_capture_tab("Parsed", parsed_page)

        captured_page = QWidget()
        captured_layout = QVBoxLayout(captured_page)
        captured_layout.setContentsMargins(0, 0, 0, 0)
        captured_layout.setSpacing(0)
        self.capture_list = QListWidget()
        self.capture_list.setObjectName("captureList")
        self.capture_list.setWordWrap(True)
        captured_layout.addWidget(self.capture_list, 1)
        self.capture_captured_tab = self._add_capture_tab("Captured (0)", captured_page)

        review_page = QWidget()
        review_layout = QVBoxLayout(review_page)
        review_layout.setContentsMargins(0, 0, 0, 0)
        review_layout.setSpacing(0)
        self.capture_review_list = QListWidget()
        self.capture_review_list.setObjectName("captureReviewList")
        self.capture_review_list.setWordWrap(True)
        review_layout.addWidget(self.capture_review_list, 1)
        self.capture_review_tab = self._add_capture_tab("Review (0)", review_page)

        self.capture_fixture_tab: int | None = None
        if self._dev_fixtures_available():
            fixture_page = QWidget()
            fixture_layout = QVBoxLayout(fixture_page)
            fixture_layout.setContentsMargins(2, 2, 2, 2)
            fixture_layout.setSpacing(5)
            fixture_header = QHBoxLayout()
            fixture_header.setContentsMargins(0, 0, 0, 0)
            self.capture_fixture_status = QLabel(self._CAPTURE_FIXTURE_STATUS_DEFAULT)
            self.capture_fixture_status.setWordWrap(True)
            self.capture_fixture_save = QPushButton("Save Fixture")
            self.capture_fixture_save.clicked.connect(self._save_capture_fixture)
            fixture_header.addWidget(self.capture_fixture_status, 1)
            fixture_header.addWidget(self.capture_fixture_save)
            fixture_layout.addLayout(fixture_header)
            self.capture_fixture_tab = self._add_capture_tab("Fixtures", fixture_page)

        qna_page = QWidget()
        qna_layout = QVBoxLayout(qna_page)
        qna_layout.setContentsMargins(2, 2, 2, 2)
        qna_layout.setSpacing(4)
        self.capture_job_identity = QLabel("No analyzed job selected")
        self.capture_job_identity.setWordWrap(True)
        qna_layout.addWidget(self.capture_job_identity)
        self.capture_questions_list = QListWidget()
        self.capture_questions_list.setObjectName("captureQuestionsList")
        self.capture_questions_list.setWordWrap(True)
        qna_layout.addWidget(self.capture_questions_list, 1)
        self.capture_qna_tab = self._add_capture_tab("Q&A", qna_page)
        self.capture_tabs.setTabVisible(self.capture_qna_tab, False)

        self.capture_tabs.currentChanged.connect(self.capture_tab_pages.setCurrentIndex)
        self.capture_tabs.setCurrentIndex(self.capture_parsed_tab)
        self.capture_tab_pages.setCurrentIndex(self.capture_parsed_tab)

        self.capture_analysis_status = QLabel("Parser ready")
        self.capture_analysis_status.setObjectName("captureAnalysisStatus")
        self.capture_analysis_status.setWordWrap(True)
        layout.addWidget(self.capture_analysis_status)
        return panel

    def _add_capture_tab(self, label: str, page: QWidget) -> int:
        index = self.capture_tabs.addTab(label)
        self.capture_tab_pages.addWidget(page)
        return index

    def _dev_fixtures_available(self) -> bool:
        settings = normalize_smart_capture_settings(self.config.smart_capture_settings)
        return bool(
            settings["dev"] and self.fixture_store is not None and self.fixture_store.available
        )

    def _show_capture_pane(self) -> None:
        self.database.get_or_create_capture_session(self._active_user_id())
        self._refresh_capture_pane()
        session = self.database.active_capture_session(self._active_user_id())
        if session and session.get("phase") == "application":
            self._enter_application_capture_mode()
        self.pages.setCurrentIndex(self.capture_page_index)
        self._apply_capture_focus()
        self._refresh_matrix_labels()
        self._update_cursor_badge()
        if self._capture_has_content_cache:
            QTimer.singleShot(0, self._start_capture_verification)

    def _refresh_capture_pane(self) -> None:
        session = self.capture_service.refresh_session(self._active_user_id())
        events = list(session.get("events", []))
        self._capture_has_content_cache = bool(events)
        self.capture_tabs.setTabText(self.capture_captured_tab, f"Captured ({len(events)})")

        self.capture_list.clear()
        for number, event in enumerate(events, start=1):
            content = str(event.get("content", ""))
            preview = " ".join(content.split())
            if len(preview) > 180:
                preview = preview[:177] + "…"
            content_type = str(event.get("content_type", "unclassified"))
            item = QListWidgetItem(f"{number}. [{content_type.title()}] {preview}")
            item.setToolTip(content)
            self.capture_list.addItem(item)
        if not events:
            item = QListWidgetItem("No selections captured yet")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.capture_list.addItem(item)

        self._populate_capture_summary(events)

        application_phase = session.get("phase") == "application"
        self._set_capture_qna_visibility(application_phase)
        if application_phase:
            job_id = session.get("job_id") or self.active_job_id
            job = self.database.get_job(int(job_id)) if job_id else None
            if job:
                company = str(job.get("company") or "Unknown company")
                title = str(job.get("title") or "Unknown title")
                self.capture_job_identity.setText(f"Q&A for {company} · {title} · Job #{job_id}")
            else:
                self.capture_job_identity.setText("No analyzed job selected")
        else:
            self.capture_job_identity.setText("No analyzed job selected")

        if self.capture_fixture_tab is not None:
            self.capture_fixture_save.setEnabled(bool(events))
            if not events:
                self._reset_capture_fixture_status()

        if hasattr(self, "_matrix_buttons"):
            self._refresh_matrix_labels()

    def _set_capture_qna_visibility(self, visible: bool) -> None:
        was_qna_active = self.capture_tabs.currentIndex() == self.capture_qna_tab
        self.capture_tabs.setTabVisible(self.capture_qna_tab, visible)
        if not visible and was_qna_active:
            self.capture_tabs.setCurrentIndex(self.capture_parsed_tab)
            self.capture_tab_pages.setCurrentIndex(self.capture_parsed_tab)

    def _populate_capture_summary(self, events: list[dict]) -> None:
        parser_values, _combined = self._parser_capture_values(events)
        settings = normalize_smart_capture_settings(self.config.smart_capture_settings)
        fields, insights = merge_capture_values(
            parser_values,
            self._capture_ai_payload,
            settings,
        )
        visible = set(settings["visible_fields"])
        show_empty = bool(settings["show_empty_fields"])

        def render_identity(field_name: str, widget: QLabel) -> None:
            field = fields[field_name]
            should_show = bool(field_name in visible and (field.values or show_empty))
            widget.setVisible(should_show)
            if not should_show:
                return
            value = field.display_value or "—"
            widget.setText(value + self._capture_source_badge(field.source))
            widget.setToolTip(self._capture_field_tooltip(field))

        render_identity("company", self.capture_company_label)
        render_identity("title", self.capture_title_label)

        self.capture_fields_list.clear()
        tone_colors = {
            "positive": QColor("#85d6b5"),
            "warning": QColor("#e1ad62"),
        }
        for field_name in settings["field_order"]:
            if field_name in {"company", "title"} or field_name not in visible:
                continue
            field = fields[field_name]
            if not field.values and not show_empty:
                continue
            item = QListWidgetItem(
                f"{field.label}: {field.display_value or '—'}"
                f"{self._capture_source_badge(field.source)}"
            )
            item.setToolTip(self._capture_field_tooltip(field))
            tone = capture_tone(field, settings)
            if tone in tone_colors:
                item.setForeground(tone_colors[tone])
            self.capture_fields_list.addItem(item)

        for insight in insights:
            item = QListWidgetItem(f"AI insight: {insight}")
            item.setForeground(QColor("#9fcaf0"))
            self.capture_fields_list.addItem(item)

        if not self.capture_fields_list.count():
            item = QListWidgetItem("No selected fields detected yet")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.capture_fields_list.addItem(item)

        review_count = self._populate_capture_reviews(parser_values, fields, settings)
        self.capture_tabs.setTabText(self.capture_review_tab, f"Review ({review_count})")
        self._populate_capture_questions(events)
        self._update_capture_analysis_status(fields, settings, review_count)

    def _populate_capture_reviews(self, parser_values, fields, settings) -> int:
        self.capture_review_list.clear()
        mode = str(settings["analysis_mode"])
        if mode == "ollama":
            item = QListWidgetItem("Ollama-only mode · parser comparison is intentionally disabled")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.capture_review_list.addItem(item)
            return 0

        count = 0
        for field_name in settings["field_order"]:
            field = fields[field_name]
            parser = tuple(parser_values.get(field_name, ()))
            parser_text = " | ".join(parser) or "—"
            status = str(field.review_status)

            if status == "true_conflict":
                if not settings["report_disagreements"]:
                    continue
                count += 1
                item = QListWidgetItem(
                    f"{field.label} · true conflict\nParser: {parser_text}\nOllama: {field.ai_value or '—'}"
                )
                item.setForeground(QColor("#e1ad62"))
            elif status == "parser_gap":
                count += 1
                item = QListWidgetItem(
                    f"{field.label} · parser gap\nOllama: {field.ai_value or field.display_value or '—'}"
                )
                item.setForeground(QColor("#9fcaf0"))
            elif status == "ai_uncertain":
                count += 1
                item = QListWidgetItem(
                    f"{field.label} · AI uncertain\nParser: {parser_text}\nOllama: {field.ai_value or '—'}\nEvidence: missing"
                )
                item.setForeground(QColor("#e1ad62"))
            elif status == "parser_conflict":
                count += 1
                item = QListWidgetItem(
                    f"{field.label} · parser conflict\nParser: {parser_text}"
                )
                item.setForeground(QColor("#e1ad62"))
            else:
                continue

            item.setToolTip(self._capture_field_tooltip(field))
            self.capture_review_list.addItem(item)

        if not count:
            item = QListWidgetItem("No parser / Ollama reviews")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.capture_review_list.addItem(item)
        return count

    def _populate_capture_questions(self, events: list[dict]) -> None:
        questions: list[str] = []
        for event in events:
            if str(event.get("content_type", "")) == "application_question":
                normalized = str(event.get("content", "")).strip()
                if normalized and normalized not in questions:
                    questions.append(normalized)
            extraction = self._capture_metadata(event).get("extraction", {})
            if not isinstance(extraction, dict):
                continue
            for question in extraction.get("application_questions", []):
                normalized = str(question).strip()
                if normalized and normalized not in questions:
                    questions.append(normalized)
        self.capture_questions_list.clear()
        self.capture_tabs.setTabText(self.capture_qna_tab, f"Q&A ({len(questions)})")
        for number, question in enumerate(questions, start=1):
            self.capture_questions_list.addItem(f"{number}. {question}")
        if not questions:
            item = QListWidgetItem("No application questions detected")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.capture_questions_list.addItem(item)

    def _update_capture_analysis_status(self, fields, settings, reviews: int) -> None:
        mode = str(settings["analysis_mode"])
        nonempty = [field for field in fields.values() if field.values]
        ai_fields = sum(1 for field in nonempty if field.source in {"ai", "both", "conflict"})
        elapsed = (
            f" · {self._capture_verification_elapsed_s:.1f}s"
            if self._capture_verification_elapsed_s is not None
            else ""
        )
        model = f" · {self._capture_verification_model}" if self._capture_verification_model else ""

        if mode == "parser":
            status = "Parser complete"
        elif self._capture_verification_state == "checking":
            status = "Ollama checking…" if mode == "ollama" else "Parser complete · AI checking…"
        elif self._capture_verification_state == "verified":
            if mode == "ollama":
                status = f"Ollama complete · {len(nonempty)} fields{elapsed}{model}"
            else:
                status = f"Parser complete · AI verified {ai_fields}/{len(nonempty)}"
                if reviews:
                    status += f" · {reviews} review"
                status += elapsed + model
        elif self._capture_verification_state == "failed":
            prefix = (
                "Ollama unavailable" if mode == "ollama" else "Parser complete · AI unavailable"
            )
            status = f"{prefix}: {self._capture_verification_error}{elapsed}"
        else:
            status = "Ollama ready" if mode == "ollama" else "Parser complete · AI ready"
        self.capture_analysis_status.setText(status)

    def _start_capture_verification(self) -> None:
        settings = normalize_smart_capture_settings(self.config.smart_capture_settings)
        if settings["analysis_mode"] == "parser":
            self._capture_verification_state = "parser"
            self._capture_ai_payload = None
            self._capture_verification_elapsed_s = None
            if self.pages.currentIndex() == self.capture_page_index:
                self._refresh_capture_pane()
            return

        session = self.capture_service.refresh_session(self._active_user_id())
        events = list(session.get("events", []))
        parser_values, description = self._parser_capture_values(events)
        if not description.strip():
            return
        if self.capture_verification_worker and self.capture_verification_worker.isRunning():
            self._capture_verification_generation += 1
            self._capture_verification_pending = True
            self._capture_verification_state = "checking"
            self._populate_capture_summary(events)
            return

        self._capture_verification_generation += 1
        generation = self._capture_verification_generation
        self._capture_verification_pending = False
        self._capture_verification_state = "checking"
        self._capture_verification_error = ""
        self._capture_verification_elapsed_s = None
        self._capture_verification_started_at = time.monotonic()
        self._populate_capture_summary(events)
        self.capture_verification_worker = CaptureVerificationWorker(
            description,
            parser_values,
            str(settings["analysis_mode"]),
            str(settings["ollama_model"]),
            generation,
        )
        self.capture_verification_worker.completed.connect(self._capture_verification_completed)
        self.capture_verification_worker.failed.connect(self._capture_verification_failed)
        self.capture_verification_worker.start()

    def _capture_verification_completed(self, generation: int, payload: dict, model: str) -> None:
        current = generation == self._capture_verification_generation
        self.capture_verification_worker = None
        if current:
            if self._capture_verification_started_at is not None:
                self._capture_verification_elapsed_s = (
                    time.monotonic() - self._capture_verification_started_at
                )
            self._capture_verification_started_at = None
            self._capture_ai_payload = dict(payload)
            self._capture_verification_state = "verified"
            self._capture_verification_model = str(model)
            self._capture_verification_error = ""
            if self.pages.currentIndex() == self.capture_page_index:
                self._refresh_capture_pane()
        if self._capture_verification_pending or not current:
            self._capture_verification_pending = False
            QTimer.singleShot(0, self._start_capture_verification)

    def _capture_verification_failed(self, generation: int, message: str) -> None:
        current = generation == self._capture_verification_generation
        self.capture_verification_worker = None
        if current:
            if self._capture_verification_started_at is not None:
                self._capture_verification_elapsed_s = (
                    time.monotonic() - self._capture_verification_started_at
                )
            self._capture_verification_started_at = None
            self._capture_verification_state = "failed"
            self._capture_verification_error = str(message)
            if self.pages.currentIndex() == self.capture_page_index:
                self._refresh_capture_pane()
        if self._capture_verification_pending or not current:
            self._capture_verification_pending = False
            QTimer.singleShot(0, self._start_capture_verification)

    def _begin_capture_press(self, trigger_key: str, *, capture_allowed: bool = True) -> None:
        if self._capture_press_started is not None:
            return
        was_open = self.pages.currentIndex() == self.capture_page_index
        if not was_open:
            self._show_capture_pane()
        self._capture_press_started = time.monotonic()
        self._capture_press_key = trigger_key.upper()
        self._capture_press_opened_pane = not was_open
        self._capture_long_press_fired = False
        self._capture_press_can_capture = bool(capture_allowed)
        if not self.keyboard.is_key_down(self._capture_press_key):
            QTimer.singleShot(0, self._finish_capture_press)

    def _poll_capture_press(self) -> None:
        if self._capture_press_started is None:
            return
        held = self.keyboard.is_key_down(self._capture_press_key)
        elapsed_ms = (time.monotonic() - self._capture_press_started) * 1000
        if held and not self._capture_long_press_fired and elapsed_ms >= self.capture_long_press_ms:
            self._capture_long_press_fired = True
            self.capture_service.reset_session(self._active_user_id())
            self.active_job_id = None
            self._capture_verification_generation += 1
            self._capture_ai_payload = None
            self._capture_verification_state = "parser"
            self._capture_verification_error = ""
            self._capture_verification_pending = False
            self._capture_verification_elapsed_s = None
            self._capture_has_content_cache = False
            self._refresh_capture_pane()
            self.statusBar().showMessage("Capture cleared · New session started")
        if not held:
            self._finish_capture_press()

    def _accept_capture_selection(self, content: str) -> None:
        try:
            normalized = self.capture_service.normalize_selection(content)
        except CaptureValidationError as error:
            self.statusBar().showMessage(str(error))
            return
        acceptance = self.capture_service.accept_text(self._active_user_id(), normalized)
        self._reset_capture_fixture_status()
        self._capture_ai_payload = None
        self._capture_verification_state = "parser"
        self._capture_verification_error = ""
        self._capture_verification_elapsed_s = None
        self._refresh_capture_pane()
        QTimer.singleShot(0, self._start_capture_verification)
        label = acceptance.classification.content_type.replace("_", " ").title()
        self.statusBar().showMessage(f"Smart Capture · {label}", 1800)

    def _reset_capture_fixture_status(self) -> None:
        if hasattr(self, "capture_fixture_status"):
            self.capture_fixture_status.setText(self._CAPTURE_FIXTURE_STATUS_DEFAULT)

    def _save_capture_fixture(self) -> None:
        if not self._dev_fixtures_available() or self.fixture_store is None:
            return
        session = self.capture_service.refresh_session(self._active_user_id())
        events = list(session.get("events", []))
        parser_values, description = self._parser_capture_values(events)
        extractions: list[dict] = []
        for event in events:
            extraction = self._capture_metadata(event).get("extraction", {})
            if isinstance(extraction, dict) and extraction:
                extractions.append(extraction)
        parser_resolution = resolve_parser_evidence(extractions, description).as_dict()
        settings = normalize_smart_capture_settings(self.config.smart_capture_settings)
        merged_fields, _insights = merge_capture_values(
            parser_values, self._capture_ai_payload, settings
        )
        merge_resolution = {
            key: {
                "values": list(field.values),
                "source": field.source,
                "confidence": field.confidence,
                "evidence": field.evidence,
                "conflict": field.conflict,
                "review_status": field.review_status,
                "ai_value": field.ai_value,
            }
            for key, field in merged_fields.items()
        }
        user_data = self.user_store.read()
        try:
            package = self.fixture_store.snapshot_session(
                events,
                parser_values,
                self._capture_ai_payload,
                settings,
                active_user_id=self._active_user_id(),
                active_user_name=str(user_data.get("active_user_name", "")),
                parser_resolution=parser_resolution,
                merge_resolution=merge_resolution,
            )
        except ValueError as error:
            self.statusBar().showMessage(str(error), 2200)
            return
        fixture_id = str(package["manifest"]["fixture_id"])
        self.capture_fixture_status.setText(f"Saved {fixture_id} · expected values remain unset")
        self.statusBar().showMessage(f"Fixture snapshot saved · {fixture_id}", 2200)

    def _enter_application_capture_mode(self) -> None:
        if not hasattr(self, "capture_tabs"):
            return
        self.capture_tabs.setTabVisible(self.capture_qna_tab, True)
        self.capture_tabs.setCurrentIndex(self.capture_qna_tab)
        self.capture_tab_pages.setCurrentIndex(self.capture_qna_tab)

    def _dispatch_action(self, action: str, key: str, paste: bool) -> None:
        if action == "smart_capture":
            self._begin_capture_press(
                key,
                capture_allowed=not self.isActiveWindow(),
            )
            if self.isActiveWindow():
                self.statusBar().showMessage(
                    "Capture pane opened · Hold to reset session; capture is paused while JAW has focus"
                )
            self._update_cursor_badge()
            return
        super()._dispatch_action(action, key, paste)

    def eventFilter(self, watched, event) -> bool:
        if (
            hasattr(self, "smart_capture_field_list")
            and watched is self.smart_capture_field_list
            and event.type() == QEvent.Type.Resize
        ):
            QTimer.singleShot(0, self._resize_smart_capture_field_grid)
        return super().eventFilter(watched, event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("JAW")
    app.setApplicationDisplayName("Job Application Workbench")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
