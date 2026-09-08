from __future__ import annotations

import difflib
import sys
import time
import uuid
from dataclasses import replace
from datetime import date
from functools import partial
from urllib.parse import urlencode

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .adapters import (
    PyperclipClipboard,
    SystemBrowser,
    SystemKeyboard,
    SystemWindowChrome,
)
from .analysis.providers.ollama import (
    DEFAULT_OLLAMA_MODEL,
    OllamaAnalysisProvider,
)
from .analyzer import JobAnalyzer
from .application import CaptureService, CaptureValidationError, JobAnalysisService
from .config import (
    AppConfig,
    default_config_path,
    load_config,
    resolve_layer_binding,
    save_behavior_settings,
    split_binding,
)
from .database import JobDatabase
from .desktop.cursor_badge import CursorBadge
from .desktop.iterator_state import (
    cyclic_enabled_index,
    disabled_iterator_items,
    enabled_iterator_sequence,
    next_cyclic_index,
    ordered_iterator_sequence,
    set_iterator_order,
    toggle_iterator_item,
)
from .desktop.styles import STYLESHEET
from .desktop.widgets import (
    ChildIteratorButton,
    ClickableTextEdit,
    CollapsibleSettingsSection,
    ContentFitComboBox,
    HoverCycleStack,
    HoverIconButton,
    MatrixButton,
    Panel,
    WorkExperienceList,
    WorkExperiencePanel,
)
from .desktop.workers import (
    BriefWorker,
    CaptureVerificationWorker,
    ConnectionTestWorker,
)
from .fixture_store import FixtureStore
from .hotkeys import MatrixHotkeys
from .icons import ICON_SVGS
from .keyboard_layouts import DEFAULT_KEYBOARD_LAYOUT, resolve_keyboard_layout
from .model import DateFormat
from .paths import source_root
from .ports import BrowserPort, ClipboardPort, KeyboardPort, WindowChromePort
from .smart_capture import (
    SMART_CAPTURE_FIELD_KEYS,
    SMART_CAPTURE_FIELD_LABELS,
    capture_tone,
    collect_parser_values,
    combine_capture_text,
    merge_capture_values,
    normalize_smart_capture_settings,
)
from .userdata import (
    JOB_MATCHING_SELECTION,
    SYSTEM_SET_ALL,
    UserDataStore,
    default_user_data_path,
)
from .webapp import DashboardServer


class TwoColumnListWidget(QListWidget):
    """QListWidget that keeps checkable/draggable items in exactly two columns."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Snap)
        self.setSpacing(3)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWordWrap(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.model().rowsInserted.connect(
            lambda *_args: QTimer.singleShot(0, self._refresh_grid_size)
        )
        self.model().rowsRemoved.connect(
            lambda *_args: QTimer.singleShot(0, self._refresh_grid_size)
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_grid_size()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_grid_size()

    def _refresh_grid_size(self) -> None:
        viewport_width = max(2, self.viewport().width())
        row_height = self.sizeHintForRow(0) if self.count() else -1
        if row_height < 1:
            row_height = self.fontMetrics().height() + 8
        gutter = 12
        column_width = max(1, (viewport_width - gutter) // 2)
        target = QSize(column_width, row_height + 4)
        if self.gridSize() != target:
            self.setGridSize(target)
        rows = max(1, (self.count() + 1) // 2)
        target_height = (
            rows * target.height()
            + max(0, rows - 1) * self.spacing()
            + self.frameWidth() * 2
            + 2
        )
        if self.minimumHeight() != target_height or self.maximumHeight() != target_height:
            self.setFixedHeight(target_height)


class AnswerSearchEdit(QLineEdit):
    """Search field that temporarily yields JAW global hotkeys while typing."""

    def __init__(self, focus_changed, parent=None) -> None:
        super().__init__(parent)
        self._focus_changed = focus_changed

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._focus_changed(True)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._focus_changed(False)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        clipboard: ClipboardPort | None = None,
        keyboard: KeyboardPort | None = None,
        browser: BrowserPort | None = None,
        window_chrome: WindowChromePort | None = None,
    ) -> None:
        super().__init__()
        self.clipboard = clipboard or PyperclipClipboard()
        self.keyboard = keyboard or SystemKeyboard()
        self.browser = browser or SystemBrowser()
        self.window_chrome = window_chrome or SystemWindowChrome()
        self.setWindowTitle("Job Application Workbench")
        self.resize(480, 520)
        # Five 92px matrix columns + four 3px gaps + 4px edge spacing.
        self.setMinimumSize(480, 420)
        self._config_path = default_config_path()
        self._user_data_path = default_user_data_path()
        bootstrap_store = UserDataStore(self._user_data_path)
        bootstrap_data = bootstrap_store.read()
        self._desktop_active_user_id = int(bootstrap_data.get("active_user_id", 0))
        self.user_store = UserDataStore(self._user_data_path, user_id=self._desktop_active_user_id)
        self._keyboard_layout_name = str(
            bootstrap_data.get("keyboard_layout") or DEFAULT_KEYBOARD_LAYOUT
        )
        self._keyboard_custom_layouts = dict(
            bootstrap_data.get("keybinds", {}).get("custom_layouts", {})
        )
        self.config = config or load_config(self._config_path, user_id=self._desktop_active_user_id)
        self._desktop_set_id = self.config.active_set_id
        self._last_sync_revisions = self.user_store.read_sync_revisions()
        self._last_user_interaction = time.monotonic()
        self._sync_state = "active"
        self.layer = "Base"
        self.latched_layer = "Base"
        self._matrix_buttons: dict[str, QPushButton] = {}
        self._sequence_positions: dict[str, int] = {}
        self.job_order = list(self.config.work_history)
        self.default_field_order = ["company", "title", "start", "end", "highlights"]
        self.field_order = list(self.default_field_order)
        self.disabled_child_fields: set[str] = set()
        self._job_paste_pending = False
        self._job_paste_trigger_key = ""
        self._pending_date_values: list[str] = []
        self._pending_date_context: tuple[int, str, DateFormat] | None = None
        self._job_advance_after_paste = True
        self._keyboard_before_answers = True
        self._modifier_was_held = False
        self._escape_hold_started: float | None = None
        self._escape_hold_fired = False
        self._capture_press_started: float | None = None
        self._capture_press_key = ""
        self._capture_press_opened_pane = False
        self._capture_long_press_fired = False
        self._capture_press_can_capture = True
        self.capture_long_press_ms = 700
        self.capture_verification_worker: CaptureVerificationWorker | None = None
        self._capture_verification_generation = 0
        self._capture_ai_payload: dict | None = None
        self._capture_verification_state = "parser"
        self._capture_verification_error = ""
        self._capture_verification_model = ""
        self._capture_verification_pending = False
        self._capture_restore_keyboard: bool | None = None
        self._capture_restore_divider: bool | None = None
        self._capture_has_content_cache = False
        self.hotkeys_enabled = self.config.hotkeys_active_on_startup
        self._answer_search_active = False
        self.active_job_id: int | None = None
        self.brief_worker: BriefWorker | None = None
        self.connection_test_worker: ConnectionTestWorker | None = None
        data_path = self._user_data_path
        self.database = JobDatabase(data_path)
        self.capture_service = CaptureService(
            self.database,
            self._matching_config_answer,
        )
        workspace = source_root()
        self.fixture_store = FixtureStore(workspace) if workspace else None
        active_capture = self.database.active_capture_session(self._active_user_id())
        if active_capture and active_capture.get("job_id") is not None:
            self.active_job_id = int(active_capture["job_id"])
        self.analyzer = JobAnalyzer(
            self.config,
            self.config.openai_model,
            self.config.analysis_mode,
            self.config.analysis_provider,
        )
        self.analysis_service = JobAnalysisService(
            self.database,
            self.analyzer,
        )
        self.dashboard = DashboardServer(
            self.database,
            port=self.config.dashboard_port,
            user_data_path=self._user_data_path,
        )

        root = QWidget()
        root.setObjectName("root")
        self.root_widget = root
        self.setCentralWidget(root)
        QApplication.instance().installEventFilter(self)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(4, 7, 4, 0)
        outer.setSpacing(0)
        self._setup_status_controls()
        self.settings_panel = self._settings_panel()
        self._settings_open = False
        self._settings_previous_page = 3
        self._settings_restore_keyboard = False
        self._settings_restore_divider = True
        content = QVBoxLayout()
        content.setSpacing(0)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._workspace_panel())
        self.pages.addWidget(self._answers_panel())
        self.pages.addWidget(self._skills_panel())
        self.pages.addWidget(QWidget())
        self.custom_iterator_page_index = self.pages.addWidget(self._custom_iterator_panel())
        self.capture_page_index = self.pages.addWidget(self._capture_panel())
        self.settings_page_index = self.pages.addWidget(self.settings_panel)
        self.pages.setCurrentIndex(3)
        content.addWidget(self.pages, 1)
        self.pane_matrix_divider = QFrame()
        self.pane_matrix_divider.setObjectName("paneMatrixDivider")
        self.pane_matrix_divider.setFixedHeight(1)
        content.addWidget(self.pane_matrix_divider)
        self.keyboard_panel = self._matrix_panel()
        self.keyboard_panel.setParent(root)
        self.keyboard_panel.setMaximumHeight(270)
        content.addWidget(self.keyboard_panel, 0, Qt.AlignmentFlag.AlignBottom)
        self.keyboard_panel.setVisible(self.config.show_keyboard)
        outer.addLayout(content, 1)
        self.statusBar().clearMessage()

        self.hotkeys = self._create_hotkeys()
        self._update_hotkeys_visual_state()
        try:
            self.dashboard.start()
        except OSError as error:
            self.statusBar().showMessage(f"Dashboard unavailable: {error}")

        self.shift_visual_timer = QTimer(self)
        self.shift_visual_timer.timeout.connect(self._poll_shift_visual)
        self.shift_visual_timer.start(40)
        self.cursor_badge = CursorBadge()
        self.cursor_badge_timer = QTimer(self)
        self.cursor_badge_timer.timeout.connect(self._update_cursor_badge)
        self.cursor_badge_timer.start(35)

        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self._poll_sync_revisions)
        self._schedule_sync_timer()

    @staticmethod
    def _hotkey_signature(config: AppConfig) -> tuple:
        return (
            tuple(config.matrix.items()),
            tuple(config.layer2.items()),
            tuple(config.layer3.items()),
            repr(config.hotkey_settings),
        )

    def _create_hotkeys(self) -> MatrixHotkeys:
        settings = self.config.hotkey_settings
        layers = settings.get("layers", {})
        layer2_settings = layers.get("layer2", {})
        layer3_settings = layers.get("layer3", {})
        base_keys = [
            key
            for key, binding in self.config.matrix.items()
            if split_binding(binding)[0]
            and len(key) == 1
            and key.isalnum()
            and split_binding(binding)[0] != "layer2"
        ]
        base_keys.extend(
            key
            for key, binding in self.config.layer3.items()
            if split_binding(binding)[0]
            and len(key) == 1
            and key.isalnum()
            and layer3_settings.get("enabled", True)
        )
        base_keys.extend(
            key
            for key, binding in self.config.layer2.items()
            if split_binding(binding)[0]
            and len(key) == 1
            and key.isalnum()
            and layer2_settings.get("enabled", True)
        )
        layer_keys = [
            key
            for key, binding in self.config.layer2.items()
            if split_binding(binding)[0] not in {"", "toggle_hotkeys", "layer2", "layer3"}
            and len(key) == 1
            and key.isalnum()
            and layer2_settings.get("enabled", True)
            and layer2_settings.get("hold", True)
        ]
        base_keys = list(dict.fromkeys(base_keys))
        specials = {
            "toggle": settings.get("toggle", "SHIFT+SPACE"),
            "window": settings.get("window", "CTRL+SHIFT+F1"),
        }
        hotkeys = MatrixHotkeys(
            base_keys=base_keys,
            layer_keys=layer_keys,
            always_layer_keys=[],
            special_hotkeys=specials,
            parent=self,
        )
        hotkeys.pressed.connect(self.handle_global_key)
        hotkeys.registration_failed.connect(
            lambda key: self.statusBar().showMessage(f"Could not register global key {key}")
        )
        hotkeys.set_enabled(self.hotkeys_enabled)
        hotkeys.start()
        return hotkeys

    def _update_cursor_badge(self) -> None:
        if self.isMinimized() or not self.hotkeys_enabled:
            self.cursor_badge.update_badge("")
            return

        page_index = self.pages.currentIndex()
        if page_index == 0 and self.job_order:
            job_row = max(0, min(self.titles_list.currentRow(), len(self.job_order) - 1))
            field_labels = {
                "company": "Company",
                "title": "Title",
                "start": "Start",
                "end": "End",
                "highlights": "Bullets",
            }
            field_row = self.job_fields_list.currentRow()
            current_name = (
                self.field_order[field_row]
                if 0 <= field_row < len(self.field_order)
                else ""
            )
            values: list[str] = []
            current_index = -1
            for field_name in self.field_order:
                if field_name in self.disabled_child_fields:
                    continue
                if field_name == current_name:
                    current_index = len(values)
                values.append(field_labels.get(field_name, field_name.title()))
            self.cursor_badge.update_iterator(
                values,
                current_index,
                active_prefix=str(job_row + 1),
            )
            return

        if page_index == 2:
            values = [
                self._skill_value(self.skills_list.item(row))
                for row in range(self.skills_list.count())
            ]
            self.cursor_badge.update_iterator(values, self.skills_list.currentRow())
            return

        if page_index == self.custom_iterator_page_index:
            current = self.custom_iterator_list.currentItem()
            if current is None:
                self.cursor_badge.update_badge("")
                return
            current_id = str(current.data(Qt.ItemDataRole.UserRole) or "")
            disabled = disabled_iterator_items(
                self.config.iterator_preferences,
                self.active_custom_iterator,
            )
            values: list[str] = []
            current_index = -1
            for row in range(self.custom_iterator_list.count()):
                item = self.custom_iterator_list.item(row)
                item_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
                if item_id in disabled:
                    continue
                value = self.config.items_by_id.get(item_id)
                label = value.label if value is not None else item.text()
                if item_id == current_id:
                    current_index = len(values)
                values.append(label)
            self.cursor_badge.update_iterator(values, current_index)
            return

        text = "Capture" if page_index == self.capture_page_index else "H"
        self.cursor_badge.update_badge(text)

    def _assigned_custom_actions(self) -> set[str]:
        assigned: set[str] = set()
        custom_ids = set(self.config.custom_action_types)
        custom_ids.update(
            item.item_id for item in self.config.profile_items if item.group == "Custom"
        )
        for bindings in (self.config.matrix, self.config.layer2, self.config.layer3):
            for binding in bindings.values():
                action, _label = split_binding(str(binding))
                if action in custom_ids:
                    assigned.add(action)
        return assigned

    def _sync_is_sleeping(self) -> bool:
        return self.isMinimized() or not self.isVisible()

    def _schedule_sync_timer(self) -> None:
        if not hasattr(self, "sync_timer"):
            return
        if self._sync_is_sleeping():
            self._sync_state = "sleeping"
            self.sync_timer.stop()
            return
        idle = (time.monotonic() - self._last_user_interaction) >= 300.0
        self._sync_state = "idle" if idle else "active"
        interval = 15_000 if idle else 1_000
        if self.sync_timer.interval() != interval:
            self.sync_timer.setInterval(interval)
        if not self.sync_timer.isActive():
            self.sync_timer.start()

    def _mark_user_interaction(self) -> None:
        self._last_user_interaction = time.monotonic()
        if getattr(self, "_sync_state", "active") != "active":
            self._sync_state = "active"
            if hasattr(self, "sync_timer"):
                self.sync_timer.setInterval(1_000)
                if not self._sync_is_sleeping():
                    self.sync_timer.start()
            QTimer.singleShot(0, lambda: self._poll_sync_revisions(force=True))

    def _poll_sync_revisions(self, force: bool = False) -> None:
        if self._sync_is_sleeping() and not force:
            self._schedule_sync_timer()
            return
        try:
            current = self.user_store.read_sync_revisions()
        except (OSError, ValueError):
            self._schedule_sync_timer()
            return

        changed = {
            key for key, value in current.items() if value != self._last_sync_revisions.get(key, 0)
        }
        self._last_sync_revisions = current

        reload_needed = bool(changed & {"profile", "capabilities", "keybinds"})
        if "actions" in changed and self._assigned_custom_actions():
            reload_needed = True
        if reload_needed:
            self._load_active_user_data()

        self._schedule_sync_timer()

    def _wake_sync(self) -> None:
        self._last_user_interaction = time.monotonic()
        self._sync_state = "active"
        self._poll_sync_revisions(force=True)
        self._schedule_sync_timer()

    def _load_active_user_data(self) -> None:
        try:
            refreshed = load_config(self._config_path, user_id=self._desktop_active_user_id)
        except (OSError, ValueError):
            return
        valid_set_ids = {
            capability_set.id
            for capability_set in refreshed.capability_sets
            if capability_set.id == SYSTEM_SET_ALL
            or (not capability_set.system and capability_set.paste_enabled)
        }
        if self._desktop_set_id not in valid_set_ids:
            self._desktop_set_id = SYSTEM_SET_ALL
        refreshed = replace(refreshed, active_set_id=self._desktop_set_id)
        old_skill = self._skill_value(self.skills_list.currentItem())
        hotkeys_changed = self._hotkey_signature(self.config) != self._hotkey_signature(refreshed)
        self.config = refreshed
        self.analyzer.configure(refreshed)
        if hasattr(self, "name_format_cycle_button"):
            self.name_format_cycle_button.setText(self._name_format_label())
        if hasattr(self, "analysis_model"):
            for control in (
                self.analysis_local_radio,
                self.analysis_generative_radio,
                self.analysis_provider,
                self.analysis_model,
            ):
                control.blockSignals(True)
            self.analysis_local_radio.setChecked(refreshed.analysis_mode == "local")
            self.analysis_generative_radio.setChecked(refreshed.analysis_mode != "local")
            provider_index = self.analysis_provider.findData(refreshed.analysis_provider)
            self.analysis_provider.setCurrentIndex(max(0, provider_index))
            self._populate_analysis_models(
                refreshed.analysis_provider,
                refreshed.analysis_model,
            )
            model_index = self.analysis_model.findData(refreshed.openai_model)
            if model_index < 0:
                self.analysis_model.insertItem(0, refreshed.openai_model, refreshed.openai_model)
                model_index = 0
            self.analysis_model.setCurrentIndex(model_index)
            for control in (
                self.analysis_local_radio,
                self.analysis_generative_radio,
                self.analysis_provider,
                self.analysis_model,
            ):
                control.blockSignals(False)
            self._update_analysis_controls()
        self._rebuild_auto_return_checks(connect_signals=True)
        if hotkeys_changed:
            self.hotkeys.stop()
            self.hotkeys.deleteLater()
            self.hotkeys = self._create_hotkeys()
        self.set_selector.blockSignals(True)
        self.set_selector.clear()
        for capability_set in refreshed.capability_sets:
            if capability_set.id == JOB_MATCHING_SELECTION or not capability_set.paste_enabled:
                continue
            label = (
                "All Capabilities" if capability_set.id == SYSTEM_SET_ALL else capability_set.name
            )
            self.set_selector.addItem(label, capability_set.id)
        selected_index = self.set_selector.findData(refreshed.active_set_id)
        self.set_selector.setCurrentIndex(max(0, selected_index))
        self.set_selector.blockSignals(False)
        self.set_cycle_button.setText(self.set_selector.currentText())
        self._apply_tooltips()
        self._rebuild_skills(old_skill)
        current_job = self.titles_list.currentRow()
        self.job_order = list(refreshed.work_history)
        self._rebuild_titles(max(0, current_job))
        current_answer = self._current_answer_index()
        self._rebuild_answer_list(current_answer)
        self._refresh_user_cycle_button()
        layout_data = self.user_store.read()
        self._keyboard_layout_name = str(
            layout_data.get("keyboard_layout") or DEFAULT_KEYBOARD_LAYOUT
        )
        self._keyboard_custom_layouts = dict(
            layout_data.get("keybinds", {}).get("custom_layouts", {})
        )
        if hasattr(self, "matrix_grid"):
            self._rebuild_matrix_layout()
        else:
            self._refresh_matrix_labels()
        self._last_sync_revisions = self.user_store.read_sync_revisions()
        if self.pages.currentIndex() == self.custom_iterator_page_index:
            if self.active_custom_iterator in refreshed.sequences:
                self._show_sequence_iterator(
                    self.active_custom_iterator,
                    refreshed.sequences.get(self.active_custom_iterator, []),
                )
            elif self.active_custom_iterator in refreshed.custom_sequences:
                self._show_sequence_iterator(
                    self.active_custom_iterator,
                    refreshed.custom_sequences[self.active_custom_iterator],
                )

    def _setup_status_controls(self) -> None:
        status = self.statusBar()
        control_height = 24
        status.setFixedHeight(control_height)
        status.setContentsMargins(0, 0, 0, 0)
        status.layout().setContentsMargins(0, 0, 0, 0)
        status.layout().setSpacing(0)
        self.settings_button = HoverIconButton()
        self.settings_button.setObjectName("settingsGear")
        self.settings_button.set_state_icons(
            QIcon(self._single_icon_pixmap("gear", 20)),
            QIcon(self._single_icon_pixmap("gear", 20, "#65a6e8")),
        )
        self.settings_button.setIconSize(QSize(20, 20))
        self.settings_button.setFixedSize(control_height, control_height)
        self.settings_button.clicked.connect(self._toggle_settings)
        self.set_selector = QComboBox()
        for capability_set in self.config.capability_sets:
            if capability_set.id == JOB_MATCHING_SELECTION or not capability_set.paste_enabled:
                continue
            label = (
                "All Capabilities" if capability_set.id == SYSTEM_SET_ALL else capability_set.name
            )
            self.set_selector.addItem(label, capability_set.id)
        self.set_selector.setCurrentIndex(
            max(0, self.set_selector.findData(self.config.active_set_id))
        )
        self.set_selector.currentIndexChanged.connect(self._set_paste_set)
        self.set_selector.hide()
        self.set_cycle_button = QToolButton()
        self.set_cycle_button.setObjectName("statusCapabilitySet")
        self.set_cycle_button.setText(self.set_selector.currentText())
        collapsed_stack_width = max(54, self.set_cycle_button.sizeHint().width())
        self.set_cycle_button.resize(collapsed_stack_width, control_height)
        self.set_cycle_button.clicked.connect(self._cycle_set)
        self.date_format = QComboBox()
        for fmt in DateFormat:
            self.date_format.addItem(fmt.label, fmt)
        self.date_format.currentIndexChanged.connect(self._clear_pending_date)
        self.date_format.hide()
        self.date_cycle_button = QToolButton()
        self.date_cycle_button.setObjectName("statusDate")
        self.date_cycle_button.setText(self.date_format.currentText())
        self.date_cycle_button.setIcon(QIcon(self._single_icon_pixmap("date_format", 16)))
        self.date_cycle_button.setIconSize(QSize(16, 16))
        self.date_cycle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.date_cycle_button.clicked.connect(self._cycle_date_format_button)
        self.date_cycle_button.hide()
        self.name_format_cycle_button = QToolButton()
        self.name_format_cycle_button.setObjectName("statusName")
        self.name_format_cycle_button.setText(self._name_format_label())
        self.name_format_cycle_button.setIcon(QIcon(self._single_icon_pixmap("person", 16)))
        self.name_format_cycle_button.setIconSize(QSize(16, 16))
        self.name_format_cycle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.name_format_cycle_button.clicked.connect(self._cycle_name_format)
        self.name_format_cycle_button.hide()
        self.work_experience_cycle_button = QToolButton()
        self.work_experience_cycle_button.setObjectName("statusWorkExperience")
        self.work_experience_cycle_button.setText("Work Exp")
        self.work_experience_cycle_button.setIcon(
            QIcon(self._single_icon_pixmap("work_experience", 16))
        )
        self.work_experience_cycle_button.setIconSize(QSize(16, 16))
        self.work_experience_cycle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.work_experience_cycle_button.clicked.connect(self._toggle_work_experience_pane)
        self.work_experience_cycle_button.hide()
        self.user_cycle_button = QToolButton()
        self.user_cycle_button.setObjectName("statusUser")
        self.user_cycle_button.setText("User")
        self.user_cycle_button.setIcon(QIcon(self._single_icon_pixmap("person", 16)))
        self.user_cycle_button.setIconSize(QSize(16, 16))
        self.user_cycle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.user_cycle_button.clicked.connect(self._cycle_user)
        self._refresh_user_cycle_button()
        self.user_cycle_button.hide()
        self.layer_status_cycle_button = QToolButton()
        self.layer_status_cycle_button.setObjectName("statusLayer")
        self.layer_status_cycle_button.clicked.connect(
            lambda: self.handle_global_key("SPECIAL:toggle")
        )
        self.layer_status_cycle_button.setText("Base")
        self.layer_status_cycle_button.hide()
        expanded_stack_width = max(
            collapsed_stack_width + 36,
            self.set_selector.sizeHint().width(),
            self.date_format.sizeHint().width(),
            self.name_format_cycle_button.sizeHint().width(),
            self.work_experience_cycle_button.sizeHint().width(),
            self.user_cycle_button.sizeHint().width(),
        )
        self.status_cycle_stack = HoverCycleStack(control_height, 32)
        self.status_cycle_stack.setParent(self)
        self.status_stack_collapsed_width = collapsed_stack_width
        self.status_stack_expanded_width = expanded_stack_width
        self.status_cycle_stack.resize(collapsed_stack_width, control_height)
        self.status_cycle_stack.add_button(self.user_cycle_button)
        self.status_cycle_stack.add_button(self.work_experience_cycle_button)
        self.status_cycle_stack.set_button_enabled(
            self.work_experience_cycle_button, False
        )
        self.status_cycle_stack.add_button(self.name_format_cycle_button)
        self.status_cycle_stack.add_button(self.date_cycle_button)
        self.status_cycle_stack.add_button(self.set_cycle_button)
        self.status_cycle_stack.add_button(self.layer_status_cycle_button)
        self.status_cycle_stack.set_button_enabled(
            self.layer_status_cycle_button, self.config.show_layer_status
        )
        self.status_stack_animation = QPropertyAnimation(self.status_cycle_stack, b"geometry", self)
        self.status_stack_animation.setDuration(190)
        self.status_stack_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.status_stack_animation.finished.connect(self._status_cycle_animation_finished)
        self.status_cycle_stack.expandedChanged.connect(self._status_cycle_stack_changed)
        self.layer_badge = QPushButton("BASE LAYER")
        self.layer_badge.setCheckable(True)
        self.layer_badge.setChecked(True)
        self.layer_badge.setEnabled(False)
        self.layer_badge.setVisible(self.config.show_layer_status)
        self.layer_badge.hide()
        self.status_controls_spacer = QWidget()
        self.status_controls_spacer.setFixedSize(
            collapsed_stack_width + self.settings_button.width(), control_height
        )
        status.addPermanentWidget(self.status_controls_spacer)
        self.settings_button.setParent(status)
        self.status_cycle_stack.show()
        self.set_cycle_button.show()
        if self.config.show_layer_status:
            self.layer_status_cycle_button.show()
        self.settings_button.show()
        QTimer.singleShot(0, self._position_status_controls)
        self._apply_tooltips()

    def _position_status_controls(self) -> None:
        status = self.statusBar()
        gear_width = self.settings_button.width()
        self.settings_button.setGeometry(
            status.width() - gear_width, 0, gear_width, status.height()
        )
        self.status_stack_animation.stop()
        self.status_cycle_stack.setGeometry(self._status_cycle_target_geometry())
        self.status_cycle_stack.raise_()

    def _status_cycle_stack_changed(self, expanded: bool) -> None:
        if expanded:
            self.set_cycle_button.setIcon(QIcon(self._single_icon_pixmap("user_role", 16)))
            self.set_cycle_button.setIconSize(QSize(16, 16))
            self.set_cycle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.date_cycle_button.show()
            self.name_format_cycle_button.show()
            self.user_cycle_button.show()
            if self.layer_status_cycle_button.property("flyoutEnabled"):
                self.layer_status_cycle_button.show()
        else:
            self.set_cycle_button.setIcon(QIcon())
            self.set_cycle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.status_stack_animation.stop()
        self.status_stack_animation.setStartValue(self.status_cycle_stack.geometry())
        self.status_stack_animation.setEndValue(self._status_cycle_target_geometry(expanded))
        self.status_stack_animation.start()
        self.status_cycle_stack.raise_()

    def _status_cycle_target_geometry(self, expanded: bool | None = None) -> QRect:
        if expanded is None:
            expanded = self.status_cycle_stack.expanded
        status = self.statusBar()
        gear_width = self.settings_button.width()
        width = self.status_stack_expanded_width if expanded else self.status_stack_collapsed_width
        height = (
            self.status_cycle_stack.expanded_row_height
            * len(self.status_cycle_stack.active_buttons())
            if expanded
            else self.status_cycle_stack.row_height
        )
        right = self.width() - gear_width
        bottom = status.y() + status.height()
        return QRect(right - width, bottom - height, width, height)

    def _status_cycle_animation_finished(self) -> None:
        if not self.status_cycle_stack.expanded:
            self.date_cycle_button.hide()
            self.name_format_cycle_button.hide()
            self.work_experience_cycle_button.hide()
            self.user_cycle_button.hide()
            self.layer_status_cycle_button.setVisible(
                bool(self.layer_status_cycle_button.property("flyoutEnabled"))
            )

    def _toggle_work_experience_pane(self) -> None:
        opening = self.pages.currentIndex() != 0
        if opening:
            self._restore_keyboard_after_answers()
        self.pages.setCurrentIndex(0 if opening else 3)
        self._refresh_matrix_labels()
        self._update_cursor_badge()

    def _refresh_user_cycle_button(self) -> None:
        data = self.user_store.read()
        self._desktop_users = list(data.get("users", []))
        name = str(data.get("active_user_name", "User"))
        self.user_cycle_button.setText(name)
        self.user_cycle_button.setToolTip(f"Active user: {name}. Click to switch to the next user.")
        if hasattr(self, "status_stack_expanded_width"):
            self.status_stack_expanded_width = max(
                self.status_stack_expanded_width,
                self.user_cycle_button.sizeHint().width(),
            )
            self._position_status_controls()

    def _cycle_user(self) -> None:
        self._refresh_user_cycle_button()
        if not self._desktop_users:
            return
        ids = [int(user["id"]) for user in self._desktop_users]
        try:
            current = ids.index(self._desktop_active_user_id)
        except ValueError:
            current = -1
        next_user = self._desktop_users[(current + 1) % len(self._desktop_users)]
        next_user_id = int(next_user["id"])
        self.user_store.switch_user(next_user_id)
        self._desktop_active_user_id = next_user_id
        self.user_store.user_id = next_user_id
        self._last_sync_revisions = self.user_store.read_sync_revisions()
        next_config = load_config(self._config_path, user_id=next_user_id)
        self._desktop_set_id = next_config.active_set_id
        self._load_active_user_data()
        self._refresh_user_cycle_button()
        self.statusBar().showMessage(f"Active user: {self.user_cycle_button.text()}", 1800)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "settings_button"):
            self._position_status_controls()

    def _cycle_set(self) -> None:
        if not self.set_selector.count():
            return
        self.set_selector.setCurrentIndex(
            (self.set_selector.currentIndex() + 1) % self.set_selector.count()
        )
        self.set_cycle_button.setText(self.set_selector.currentText())
        self._apply_tooltips()

    def _cycle_date_format_button(self) -> None:
        self.date_format.setCurrentIndex(
            (self.date_format.currentIndex() + 1) % self.date_format.count()
        )
        self.date_cycle_button.setText(self.date_format.currentText())
        self._apply_tooltips()

    def _name_format_label(self) -> str:
        return "Full Name" if self.config.name_format == "full" else "First → Last"

    def _cycle_name_format(self) -> None:
        name_format = "first_last" if self.config.name_format == "full" else "full"
        self.user_store.set_name_format(name_format)
        contact_sequence = (
            ["full_name", "email", "phone"]
            if name_format == "full"
            else ["first_name", "last_name", "email", "phone"]
        )
        contact_sequence = [
            item_id
            for item_id in contact_sequence
            if self.config.items_by_id.get(item_id)
            and self.config.items_by_id[item_id].value.strip()
        ]
        sequences = dict(self.config.sequences)
        sequences["iterate_contact"] = contact_sequence
        self.config = replace(self.config, name_format=name_format, sequences=sequences)
        self._sequence_positions["iterate_contact"] = 0
        self.name_format_cycle_button.setText(self._name_format_label())
        if (
            self.pages.currentIndex() == self.custom_iterator_page_index
            and self.active_custom_iterator == "iterate_contact"
        ):
            self._show_sequence_iterator("iterate_contact", contact_sequence)
        self._update_cursor_badge()
        self._apply_tooltips()
        self.statusBar().showMessage(f"Contact name format: {self._name_format_label()}", 1800)

    def _settings_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        panel = QFrame()
        panel.setObjectName("settingsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(2, 4, 2, 6)
        layout.setSpacing(5)

        general_section = CollapsibleSettingsSection("General")
        self.hotkeys_active_on_startup_check = QCheckBox("Global hotkeys active on startup")
        self.hotkeys_active_on_startup_check.setChecked(self.config.hotkeys_active_on_startup)
        self.hotkeys_active_on_startup_check.setToolTip(
            "Enable global hotkeys automatically the next time JAW starts"
        )
        general_section.content_layout.addWidget(self.hotkeys_active_on_startup_check)
        layout.addWidget(general_section)

        display_section = CollapsibleSettingsSection("Display")
        self.show_tooltips_check = QCheckBox("Show tooltips")
        self.show_tooltips_check.setChecked(self.config.show_tooltips)
        self.show_keyboard_check = QCheckBox("Show keyboard")
        self.show_keyboard_check.setChecked(self.config.show_keyboard)
        self.show_layer_status_check = QCheckBox("Show keyboard status")
        self.show_layer_status_check.setChecked(self.config.show_layer_status)
        self.show_border_indicator_check = QCheckBox("Show border indicator · Hotkey toggle status")
        self.show_border_indicator_check.setChecked(self.config.show_border_indicator)
        for checkbox in (
            self.show_tooltips_check,
            self.show_keyboard_check,
            self.show_layer_status_check,
            self.show_border_indicator_check,
        ):
            display_section.content_layout.addWidget(checkbox)
        escape_row = QHBoxLayout()
        escape_row.setContentsMargins(0, 0, 0, 0)
        escape_row.addWidget(QLabel("Long-press Escape"))
        self.escape_long_press = QSpinBox()
        self.escape_long_press.setRange(100, 5000)
        self.escape_long_press.setSingleStep(50)
        self.escape_long_press.setSuffix(" ms")
        self.escape_long_press.setValue(self.config.escape_long_press_ms)
        self.escape_long_press.setToolTip(
            "Hold Escape this long while JAW is unfocused to close its iterator pane"
        )
        escape_row.addWidget(self.escape_long_press)
        escape_row.addStretch()
        display_section.content_layout.addLayout(escape_row)
        layout.addWidget(display_section)

        return_section = CollapsibleSettingsSection("Auto return after paste")
        delay_row = QHBoxLayout()
        delay_row.setContentsMargins(0, 0, 0, 0)
        delay_row.addWidget(QLabel("Return delay"))
        self.iterator_delay = QSpinBox()
        self.iterator_delay.setRange(0, 5000)
        self.iterator_delay.setSingleStep(25)
        self.iterator_delay.setSuffix(" ms")
        self.iterator_delay.setValue(self.config.iterator_delay_ms)
        self.iterator_delay.setToolTip("Wait after pasting before Return is sent")
        delay_row.addWidget(self.iterator_delay)
        delay_row.addStretch()
        return_section.content_layout.addLayout(delay_row)

        iterator_checks = QGridLayout()
        iterator_checks.setContentsMargins(0, 0, 0, 0)
        iterator_checks.setHorizontalSpacing(18)
        iterator_checks.setVerticalSpacing(7)
        self.auto_return_layout = iterator_checks
        self.auto_return_checks: dict[str, QCheckBox] = {}
        self._rebuild_auto_return_checks()
        return_section.content_layout.addLayout(iterator_checks)
        layout.addWidget(return_section)

        smart_capture_section = CollapsibleSettingsSection("Smart Capture")
        capture_settings = normalize_smart_capture_settings(self.config.smart_capture_settings)
        smart_capture_section.content_layout.addWidget(
            QLabel("Displayed fields · check to show · drag to reorder")
        )
        self.smart_capture_field_list = TwoColumnListWidget()
        self.smart_capture_field_list.setObjectName("smartCaptureFieldList")
        self.smart_capture_field_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.smart_capture_field_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        visible_fields = set(capture_settings["visible_fields"])
        for field in capture_settings["field_order"]:
            item = QListWidgetItem(SMART_CAPTURE_FIELD_LABELS[field])
            item.setData(Qt.ItemDataRole.UserRole, field)
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled
            )
            item.setCheckState(
                Qt.CheckState.Checked if field in visible_fields else Qt.CheckState.Unchecked
            )
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.smart_capture_field_list.addItem(item)
        smart_capture_section.content_layout.addWidget(self.smart_capture_field_list)

        self.smart_capture_show_empty_check = QCheckBox("Show empty fields")
        self.smart_capture_show_empty_check.setChecked(bool(capture_settings["show_empty_fields"]))
        self.smart_capture_focus_check = QCheckBox(
            "Capture Focus · hide keyboard while Smart Capture is open"
        )
        self.smart_capture_focus_check.setChecked(bool(capture_settings["focus_mode"]))
        smart_capture_section.content_layout.addWidget(self.smart_capture_show_empty_check)
        smart_capture_section.content_layout.addWidget(self.smart_capture_focus_check)

        capture_mode_row = QHBoxLayout()
        capture_mode_row.setContentsMargins(0, 0, 0, 0)
        capture_mode_row.addWidget(QLabel("Capture analysis"))
        self.smart_capture_analysis_mode = ContentFitComboBox()
        self.smart_capture_analysis_mode.addItem("Parser only", "parser")
        self.smart_capture_analysis_mode.addItem("Parser + Ollama verify", "verify")
        self.smart_capture_analysis_mode.addItem("AI enhanced", "enhanced")
        self.smart_capture_analysis_mode.setCurrentIndex(
            max(
                0,
                self.smart_capture_analysis_mode.findData(capture_settings["analysis_mode"]),
            )
        )
        capture_mode_row.addWidget(self.smart_capture_analysis_mode)
        capture_mode_row.addStretch()
        smart_capture_section.content_layout.addLayout(capture_mode_row)

        capture_model_row = QHBoxLayout()
        capture_model_row.setContentsMargins(0, 0, 0, 0)
        capture_model_row.addWidget(QLabel("Ollama model"))
        self.smart_capture_ollama_model = ContentFitComboBox()
        self._populate_smart_capture_ollama_models(
            str(capture_settings["ollama_model"])
        )
        capture_model_row.addWidget(self.smart_capture_ollama_model)
        self.smart_capture_ollama_refresh = QPushButton("Refresh")
        self.smart_capture_ollama_refresh.setToolTip(
            "Refresh the list of models currently installed in Ollama"
        )
        self.smart_capture_ollama_refresh.clicked.connect(
            self._refresh_smart_capture_ollama_models
        )
        capture_model_row.addWidget(self.smart_capture_ollama_refresh)
        capture_model_row.addStretch()
        smart_capture_section.content_layout.addLayout(capture_model_row)

        self.smart_capture_fill_missing_check = QCheckBox(
            "Fill parser gaps with explicit AI findings"
        )
        self.smart_capture_fill_missing_check.setChecked(bool(capture_settings["fill_missing"]))
        self.smart_capture_disagreement_check = QCheckBox("Show parser / AI disagreements")
        self.smart_capture_disagreement_check.setChecked(
            bool(capture_settings["report_disagreements"])
        )
        smart_capture_section.content_layout.addWidget(self.smart_capture_fill_missing_check)
        smart_capture_section.content_layout.addWidget(self.smart_capture_disagreement_check)

        smart_capture_section.content_layout.addWidget(QLabel("Highlight rules"))
        self.smart_capture_warn_non_remote = QCheckBox("Hybrid / on-site")
        self.smart_capture_warn_on_call = QCheckBox("On-call required")
        self.smart_capture_warn_travel = QCheckBox("Travel 25%+")
        self.smart_capture_warn_sponsorship = QCheckBox("Sponsorship not offered")
        rule_checks = (
            (self.smart_capture_warn_non_remote, "warn_non_remote"),
            (self.smart_capture_warn_on_call, "warn_on_call"),
            (self.smart_capture_warn_travel, "warn_travel"),
            (self.smart_capture_warn_sponsorship, "warn_sponsorship"),
        )
        for checkbox, setting_key in rule_checks:
            checkbox.setChecked(bool(capture_settings[setting_key]))
            smart_capture_section.content_layout.addWidget(checkbox)
        layout.addWidget(smart_capture_section)

        analysis_section = CollapsibleSettingsSection("Job Description Analysis")
        analysis_help = QPushButton("Documentation")
        analysis_help.clicked.connect(
            lambda: self.browser.open(f"{self.dashboard.url}/help/job-description-analysis")
        )
        analysis_section.content_layout.addWidget(analysis_help, 0, Qt.AlignmentFlag.AlignLeft)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.addWidget(QLabel("Analysis method"))
        self.analysis_local_radio = QPushButton("Local Analyzer")
        self.analysis_generative_radio = QPushButton("Generative AI")
        for method_button in (self.analysis_local_radio, self.analysis_generative_radio):
            method_button.setObjectName("analysisMethod")
            method_button.setCheckable(True)
            method_button.setAutoExclusive(True)
        self.analysis_local_radio.setChecked(self.config.analysis_mode == "local")
        self.analysis_generative_radio.setChecked(self.config.analysis_mode != "local")
        mode_row.addWidget(self.analysis_local_radio)
        mode_row.addWidget(self.analysis_generative_radio)
        self.analysis_method_status = QLabel("")
        self.analysis_method_status.setObjectName("status")
        mode_row.addWidget(self.analysis_method_status)
        mode_row.addStretch()
        analysis_section.content_layout.addLayout(mode_row)

        provider_row = QHBoxLayout()
        provider_row.setContentsMargins(0, 0, 0, 0)
        provider_row.addWidget(QLabel("AI provider"))
        self.analysis_provider = ContentFitComboBox()
        self.analysis_provider.addItem("OpenAI", "openai")
        self.analysis_provider.addItem("Ollama · local", "ollama")
        self.analysis_provider.setCurrentIndex(
            max(0, self.analysis_provider.findData(self.config.analysis_provider))
        )
        provider_row.addWidget(self.analysis_provider)
        provider_row.addStretch()
        analysis_section.content_layout.addLayout(provider_row)

        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.addWidget(QLabel("Model"))
        self.analysis_model = ContentFitComboBox()
        models = [
            ("GPT-5.6 Terra · balanced", "gpt-5.6-terra"),
            ("GPT-5.6 Luna · cost-sensitive", "gpt-5.6-luna"),
            ("GPT-5.6 Sol · highest capability", "gpt-5.6-sol"),
        ]
        if self.config.openai_model not in {model for _, model in models}:
            models.insert(0, (self.config.openai_model, self.config.openai_model))
        for label, model in models:
            self.analysis_model.addItem(label, model)
        self.analysis_model.setCurrentIndex(
            max(0, self.analysis_model.findData(self.config.openai_model))
        )
        self._populate_analysis_models(
            self.config.analysis_provider,
            self.config.analysis_model,
        )
        model_row.addWidget(self.analysis_model)
        model_row.addStretch()
        analysis_section.content_layout.addLayout(model_row)

        connection_row = QHBoxLayout()
        connection_row.setContentsMargins(0, 0, 0, 0)
        self.analysis_test_button = QPushButton("Test connection")
        self.analysis_connection_status = QLabel("")
        self.analysis_connection_status.setObjectName("status")
        connection_row.addWidget(self.analysis_test_button)
        connection_row.addWidget(self.analysis_connection_status, 1)
        analysis_section.content_layout.addLayout(connection_row)
        layout.addWidget(analysis_section)

        settings_sections = [
            general_section,
            display_section,
            return_section,
            smart_capture_section,
            analysis_section,
        ]

        def expand_only(opened: CollapsibleSettingsSection) -> None:
            for candidate in settings_sections:
                candidate.set_expanded(candidate is opened)

        for section in settings_sections:
            section.expanded.connect(expand_only)
            section.set_expanded(False)

        layout.addStretch()
        self.behavior_save_timer = QTimer(self)
        self.behavior_save_timer.setSingleShot(True)
        self.behavior_save_timer.setInterval(300)
        self.behavior_save_timer.timeout.connect(self._save_behavior_settings)
        for action in self.auto_return_checks.values():
            action.toggled.connect(self._auto_return_changed)
        self.iterator_delay.valueChanged.connect(self._queue_behavior_save)
        self.escape_long_press.valueChanged.connect(self._queue_behavior_save)
        self.hotkeys_active_on_startup_check.toggled.connect(self._queue_behavior_save)
        self.show_keyboard_check.toggled.connect(self._show_keyboard_changed)
        self.show_layer_status_check.toggled.connect(self._show_layer_status_changed)
        self.show_tooltips_check.toggled.connect(self._show_tooltips_changed)
        self.show_border_indicator_check.toggled.connect(self._show_border_indicator_changed)
        self.smart_capture_field_list.itemChanged.connect(self._smart_capture_settings_changed)
        self.smart_capture_field_list.model().rowsMoved.connect(
            self._smart_capture_settings_changed
        )
        for control in (
            self.smart_capture_show_empty_check,
            self.smart_capture_focus_check,
            self.smart_capture_fill_missing_check,
            self.smart_capture_disagreement_check,
            self.smart_capture_warn_non_remote,
            self.smart_capture_warn_on_call,
            self.smart_capture_warn_travel,
            self.smart_capture_warn_sponsorship,
        ):
            control.toggled.connect(self._smart_capture_settings_changed)
        self.smart_capture_analysis_mode.currentIndexChanged.connect(
            self._smart_capture_settings_changed
        )
        self.smart_capture_ollama_model.currentIndexChanged.connect(
            self._smart_capture_settings_changed
        )
        self._update_smart_capture_controls()
        self.analysis_local_radio.toggled.connect(self._analysis_mode_changed)
        self.analysis_provider.currentIndexChanged.connect(self._analysis_provider_changed)
        self.analysis_model.currentIndexChanged.connect(self._analysis_setting_changed)
        self.analysis_test_button.clicked.connect(self._test_analysis_connection)
        self._update_analysis_controls()
        scroll.setWidget(panel)
        return scroll

    def _current_smart_capture_settings(self) -> dict:
        order: list[str] = []
        visible: list[str] = []
        for row in range(self.smart_capture_field_list.count()):
            item = self.smart_capture_field_list.item(row)
            field = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if field not in SMART_CAPTURE_FIELD_KEYS:
                continue
            order.append(field)
            if item.checkState() == Qt.CheckState.Checked:
                visible.append(field)
        return normalize_smart_capture_settings(
            {
                "field_order": order,
                "visible_fields": visible,
                "show_empty_fields": self.smart_capture_show_empty_check.isChecked(),
                "focus_mode": self.smart_capture_focus_check.isChecked(),
                "analysis_mode": str(self.smart_capture_analysis_mode.currentData() or "verify"),
                "ollama_model": str(
                    self.smart_capture_ollama_model.currentData()
                    or self.smart_capture_ollama_model.currentText()
                ),
                "fill_missing": self.smart_capture_fill_missing_check.isChecked(),
                "report_disagreements": self.smart_capture_disagreement_check.isChecked(),
                "warn_non_remote": self.smart_capture_warn_non_remote.isChecked(),
                "warn_on_call": self.smart_capture_warn_on_call.isChecked(),
                "warn_travel": self.smart_capture_warn_travel.isChecked(),
                "warn_sponsorship": self.smart_capture_warn_sponsorship.isChecked(),
            }
        )

    def _smart_capture_settings_changed(self, *_args) -> None:
        settings = self._current_smart_capture_settings()
        previous_mode = str(self.config.smart_capture_settings.get("analysis_mode", "verify"))
        self.config = replace(self.config, smart_capture_settings=settings)
        self._update_smart_capture_controls()
        if self.pages.currentIndex() == self.capture_page_index:
            if settings["focus_mode"]:
                self._apply_capture_focus()
            else:
                self._restore_capture_focus()
            if settings["analysis_mode"] == "parser":
                self._capture_verification_generation += 1
                self._capture_ai_payload = None
                self._capture_verification_state = "parser"
                self._capture_verification_error = ""
                self._capture_verification_pending = False
            elif previous_mode != settings["analysis_mode"]:
                self._capture_ai_payload = None
                QTimer.singleShot(0, self._start_capture_verification)
            self._refresh_capture_pane()
        self._queue_behavior_save()

    def _update_smart_capture_controls(self) -> None:
        ai_enabled = str(self.smart_capture_analysis_mode.currentData() or "verify") != "parser"
        for control in (
            self.smart_capture_ollama_model,
            self.smart_capture_fill_missing_check,
            self.smart_capture_disagreement_check,
        ):
            control.setEnabled(ai_enabled)

    def _update_analysis_controls(self) -> None:
        generative = self.analysis_generative_radio.isChecked()
        self.analysis_provider.setEnabled(generative)
        self.analysis_model.setEnabled(generative)
        self.analysis_method_status.setText(
            "Generative AI active" if generative else "Local Analyzer active"
        )

    def _analysis_mode_changed(self, _checked: bool) -> None:
        self._update_analysis_controls()
        self._analysis_setting_changed()

    def _available_ollama_models(self, current_model: str = "") -> list[str]:
        """Return installed Ollama models while preserving the configured fallback."""
        try:
            installed = OllamaAnalysisProvider(
                DEFAULT_OLLAMA_MODEL,
            ).list_models(timeout=2)
        except RuntimeError:
            installed = []
        models: list[str] = []
        for candidate in (current_model, *installed, DEFAULT_OLLAMA_MODEL):
            model = str(candidate or "").strip()
            if model and model not in models:
                models.append(model)
        return models

    def _populate_smart_capture_ollama_models(
        self, current_model: str = ""
    ) -> None:
        if not hasattr(self, "smart_capture_ollama_model"):
            return
        selected = str(current_model or "").strip() or DEFAULT_OLLAMA_MODEL
        models = self._available_ollama_models(selected)
        self.smart_capture_ollama_model.blockSignals(True)
        self.smart_capture_ollama_model.clear()
        for model in models:
            self.smart_capture_ollama_model.addItem(model, model)
        self.smart_capture_ollama_model.setCurrentIndex(
            max(0, self.smart_capture_ollama_model.findData(selected))
        )
        self.smart_capture_ollama_model.blockSignals(False)

    def _refresh_smart_capture_ollama_models(self) -> None:
        current = str(
            self.smart_capture_ollama_model.currentData()
            or self.smart_capture_ollama_model.currentText()
            or DEFAULT_OLLAMA_MODEL
        )
        self._populate_smart_capture_ollama_models(current)
        self._smart_capture_settings_changed()

    def _populate_analysis_models(
        self,
        provider: str,
        current_model: str = "",
    ) -> None:
        """Populate models appropriate to the selected provider."""
        if not hasattr(self, "analysis_model"):
            return
        self.analysis_model.blockSignals(True)
        self.analysis_model.clear()
        if str(provider).lower() == "ollama":
            available = self._available_ollama_models(current_model)
            for model in available:
                self.analysis_model.addItem(model, model)
            selected = (
                current_model
                if current_model in available
                else (DEFAULT_OLLAMA_MODEL if DEFAULT_OLLAMA_MODEL in available else available[0])
            )
        else:
            models = [
                ("GPT-5.6 Terra · balanced", "gpt-5.6-terra"),
                ("GPT-5.6 Luna · cost-sensitive", "gpt-5.6-luna"),
                ("GPT-5.6 Sol · highest capability", "gpt-5.6-sol"),
            ]
            if current_model and current_model not in {model for _, model in models}:
                models.insert(0, (current_model, current_model))
            for label, model in models:
                self.analysis_model.addItem(label, model)
            selected = current_model or self.config.openai_model
        self.analysis_model.setCurrentIndex(max(0, self.analysis_model.findData(selected)))
        self.analysis_model.blockSignals(False)

    def _analysis_provider_changed(self, _value=None) -> None:
        provider = str(self.analysis_provider.currentData() or "openai")
        self._populate_analysis_models(provider)
        self._analysis_setting_changed()

    def _analysis_setting_changed(self, _value=None) -> None:
        if not hasattr(self, "analysis_model"):
            return
        mode = "generative" if self.analysis_generative_radio.isChecked() else "local"
        provider = str(self.analysis_provider.currentData() or "openai")
        model = str(self.analysis_model.currentData() or self.config.openai_model)
        self.user_store.save_analysis_settings(mode, provider, model)
        self.config = replace(
            self.config,
            analysis_mode=mode,
            analysis_provider=provider,
            openai_model=model,
        )
        self.analyzer.configure(self.config)
        self.analysis_connection_status.setText("Settings saved")

    def _test_analysis_connection(self) -> None:
        self._analysis_setting_changed()
        self.analysis_test_button.setEnabled(False)
        self.analysis_connection_status.setText("Testing…")
        self.connection_test_worker = ConnectionTestWorker(self.analyzer)
        self.connection_test_worker.completed.connect(self._analysis_connection_succeeded)
        self.connection_test_worker.failed.connect(self._analysis_connection_failed)
        self.connection_test_worker.start()

    def _analysis_connection_succeeded(self, message: str) -> None:
        self.analysis_test_button.setEnabled(True)
        self.analysis_connection_status.setText(message)

    def _analysis_connection_failed(self, message: str) -> None:
        self.analysis_test_button.setEnabled(True)
        self.analysis_connection_status.setText(f"Connection failed · {message}")

    def _rebuild_auto_return_checks(self, connect_signals: bool = False) -> None:
        while self.auto_return_layout.count():
            item = self.auto_return_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.auto_return_checks.clear()
        auto_return_items = sorted(
            [
                ("iter", "contact", "Contact"),
                ("iter", "address", "Address"),
                ("iter", "links", "Links"),
                ("iter", "skills", "Skills"),
                ("iter", "work_exp", "Work Exp"),
            ]
            + [
                (
                    "iter" if action_type == "iterator" else "paste",
                    action_id,
                    self.config.action_labels.get(action_id, action_id),
                )
                for action_id, action_type in self.config.custom_action_types.items()
            ],
            key=lambda item: (item[0], item[2].casefold()),
        )
        rows_per_column = (len(auto_return_items) + 1) // 2
        icons = {
            "iter": QIcon(self._single_icon_pixmap("iterate", 16)),
            "paste": QIcon(self._single_icon_pixmap("paste", 16)),
        }
        for index, (kind, category, label) in enumerate(auto_return_items):
            checkbox = QCheckBox(label)
            checkbox.setIcon(icons[kind])
            checkbox.setIconSize(QSize(16, 16))
            checkbox.setChecked(
                self.config.custom_action_auto_return.get(
                    category, self.config.auto_return.get(category, False)
                )
            )
            row = index % rows_per_column
            column = index // rows_per_column
            self.auto_return_layout.addWidget(checkbox, row, column)
            self.auto_return_checks[category] = checkbox
            if connect_signals:
                checkbox.toggled.connect(self._auto_return_changed)
        self.auto_return_layout.setColumnStretch(0, 1)
        self.auto_return_layout.setColumnStretch(1, 1)

    def _toggle_settings(self) -> None:
        if self._settings_open:
            self._close_settings()
            return
        self._settings_open = True
        self._settings_previous_page = self.pages.currentIndex()
        self._settings_restore_keyboard = self.keyboard_panel.isVisible()
        self._settings_restore_divider = self.pane_matrix_divider.isVisible()
        self.pages.setCurrentIndex(self.settings_page_index)
        self.keyboard_panel.hide()
        self.pane_matrix_divider.hide()
        self.settings_button.setProperty("open", True)
        self.settings_button.style().unpolish(self.settings_button)
        self.settings_button.style().polish(self.settings_button)

    def _close_settings(self) -> None:
        if not self._settings_open:
            return
        self._settings_open = False
        restore_page = self._settings_previous_page
        if restore_page == self.settings_page_index:
            restore_page = 3
        self.pages.setCurrentIndex(restore_page)
        self.keyboard_panel.setVisible(self._settings_restore_keyboard)
        self.pane_matrix_divider.setVisible(self._settings_restore_divider)
        self.settings_button.setProperty("open", False)
        self.settings_button.style().unpolish(self.settings_button)
        self.settings_button.style().polish(self.settings_button)

    def _show_keyboard_changed(self, visible: bool) -> None:
        if self._settings_open:
            self._settings_restore_keyboard = visible
        else:
            self.keyboard_panel.setVisible(visible)
        self._queue_behavior_save()

    def _show_layer_status_changed(self, visible: bool) -> None:
        self.layer_badge.hide()
        self.status_cycle_stack.set_button_enabled(self.layer_status_cycle_button, visible)
        if not self.status_cycle_stack.expanded:
            self.layer_status_cycle_button.setVisible(visible)
        self._refresh_layer_status_button()
        if self.status_cycle_stack.expanded:
            self._status_cycle_stack_changed(True)
        self._queue_behavior_save()

    def _show_tooltips_changed(self, visible: bool) -> None:
        self._apply_tooltips(visible)
        self._queue_behavior_save()

    def _show_border_indicator_changed(self, _visible: bool) -> None:
        self._update_hotkeys_visual_state()
        self._queue_behavior_save()

    def _apply_tooltips(self, visible: bool | None = None) -> None:
        if visible is None:
            visible = getattr(self, "show_tooltips_check", None)
            visible = visible.isChecked() if visible is not None else self.config.show_tooltips
        tips = {
            self.settings_button: "Open settings",
            self.set_cycle_button: f"Active capability set: {self.set_selector.currentText()}. Click to cycle; hover for more controls.",
            self.date_cycle_button: f"Date format: {self.date_format.currentText()}. Click to cycle.",
            self.name_format_cycle_button: (
                f"Contact name format: {self._name_format_label()}. Click to cycle."
            ),
            self.work_experience_cycle_button: "Open or close the Work Experience pane.",
            self.user_cycle_button: (
                f"Active user: {self.user_cycle_button.text()}. Click to switch to the next user."
            ),
            self.layer_status_cycle_button: "Current keyboard layer and hotkey status. Click to toggle hotkeys.",
        }
        for widget, tip in tips.items():
            widget.setToolTip(tip if visible else "")

    def _set_paste_set(self, index: int) -> None:
        set_id = str(self.set_selector.itemData(index) or "").strip()
        if not set_id:
            return
        self._desktop_set_id = set_id
        self.user_store.set_active_set_id(set_id)
        self._load_active_user_data()
        self.set_cycle_button.setText(self.set_selector.currentText())
        self._apply_tooltips()

    def _queue_behavior_save(self, _value=None) -> None:
        self.behavior_save_timer.start()

    def _auto_return_changed(self, _checked: bool) -> None:
        self._queue_behavior_save()

    def _save_behavior_settings(self) -> None:
        custom_action_ids = set(self.config.custom_action_types)
        custom_returns = {
            category: checkbox.isChecked()
            for category, checkbox in self.auto_return_checks.items()
            if category in custom_action_ids
        }
        self.user_store.set_custom_action_auto_returns(custom_returns)
        self.config.custom_action_auto_return.update(custom_returns)
        builtin_returns = {
            category: checkbox.isChecked()
            for category, checkbox in self.auto_return_checks.items()
            if category not in custom_action_ids
        }
        startup_hotkeys = self.hotkeys_active_on_startup_check.isChecked()
        smart_capture_settings = self._current_smart_capture_settings()
        self.config = replace(
            self.config,
            auto_return=builtin_returns,
            custom_action_auto_return={
                **self.config.custom_action_auto_return,
                **custom_returns,
            },
            iterator_delay_ms=self.iterator_delay.value(),
            hotkeys_active_on_startup=startup_hotkeys,
            smart_capture_settings=smart_capture_settings,
        )
        save_behavior_settings(
            auto_return=builtin_returns,
            iterator_delay_ms=self.iterator_delay.value(),
            escape_long_press_ms=self.escape_long_press.value(),
            show_keyboard=self.show_keyboard_check.isChecked(),
            show_layer_status=self.show_layer_status_check.isChecked(),
            show_tooltips=self.show_tooltips_check.isChecked(),
            show_border_indicator=self.show_border_indicator_check.isChecked(),
            hotkeys_active_on_startup=startup_hotkeys,
            smart_capture_settings=smart_capture_settings,
        )
        self.statusBar().showMessage("Settings saved", 1600)

    def _clear_pending_date(self, _index=None) -> None:
        self._pending_date_values.clear()
        self._pending_date_context = None

    def _workspace_panel(self) -> QWidget:
        workspace = WorkExperiencePanel()
        workspace.setObjectName("workExperiencePanel")
        workspace.layout.setContentsMargins(7, 7, 0, 4)
        workspace.layout.setSpacing(3)
        self.titles_list = WorkExperienceList()
        self.titles_list.setSpacing(0)
        self.titles_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.titles_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.titles_list.setDragDropOverwriteMode(False)
        self.titles_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.titles_list.currentRowChanged.connect(self._title_changed)
        self.titles_list.customContextMenuRequested.connect(self._toggle_work_entry_at)
        self.titles_list.model().rowsMoved.connect(self._work_history_reordered)
        workspace.layout.addWidget(self.titles_list, 1)
        self.field_strip = QWidget()
        field_layout = QHBoxLayout(self.field_strip)
        field_layout.setContentsMargins(0, 0, 0, 0)
        field_layout.setSpacing(3)
        self.field_buttons: list[ChildIteratorButton] = []
        labels = {
            "company": "Company",
            "title": "Title",
            "start": "Start",
            "end": "End",
            "highlights": "Bullets",
        }
        for field_name in self.field_order:
            button = ChildIteratorButton(field_name, labels[field_name])
            button.setCheckable(True)
            button.setFixedHeight(30)
            button.clicked.connect(partial(self._select_job_field_name, field_name))
            button.toggleRequested.connect(self._toggle_child_iterator)
            button.fieldDropped.connect(self._move_child_iterator)
            field_layout.addWidget(button, 1)
            self.field_buttons.append(button)
        workspace.layout.addWidget(self.field_strip)

        # Retained as the iterator model; the visible control is the horizontal strip.
        self.job_fields_list = QListWidget()
        self.job_fields_list.currentRowChanged.connect(self._field_changed)
        self.job_fields_list.hide()

        self._rebuild_titles(0)
        self._apply_tooltips()
        return workspace

    def _select_job_field_name(self, field_name: str) -> None:
        if field_name in self.disabled_child_fields:
            return
        self.job_fields_list.setCurrentRow(self.field_order.index(field_name))

    def _skills_panel(self) -> QWidget:
        panel = WorkExperiencePanel()
        panel.setObjectName("workExperiencePanel")
        panel.layout.setContentsMargins(7, 7, 0, 4)
        panel.layout.setSpacing(3)
        self.skills_list = WorkExperienceList()
        self.skills_list.setSpacing(0)
        panel.layout.addWidget(self.skills_list, 1)
        self._rebuild_skills()
        return panel

    def _custom_iterator_panel(self) -> QWidget:
        panel = WorkExperiencePanel()
        panel.setObjectName("workExperiencePanel")
        panel.layout.setContentsMargins(7, 7, 0, 4)
        panel.layout.setSpacing(3)
        self.custom_iterator_list = WorkExperienceList()
        self.custom_iterator_list.setSpacing(0)
        self.custom_iterator_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.custom_iterator_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.custom_iterator_list.setDragDropOverwriteMode(False)
        self.custom_iterator_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.custom_iterator_list.customContextMenuRequested.connect(
            self._toggle_custom_iterator_at
        )
        self.custom_iterator_list.model().rowsMoved.connect(self._custom_iterator_reordered)
        panel.layout.addWidget(self.custom_iterator_list, 1)
        self.active_custom_iterator = ""
        self.active_custom_position_key = ""
        return panel

    def _show_sequence_iterator(
        self, action: str, sequence: list[str], position_key: str | None = None
    ) -> None:
        self._restore_keyboard_after_answers()
        self._refresh_matrix_labels()
        self.active_custom_iterator = action
        sequence = ordered_iterator_sequence(self.config.iterator_preferences, action, sequence)
        self.custom_iterator_list.clear()
        self.active_custom_position_key = position_key or action
        enabled_sequence = enabled_iterator_sequence(
            self.config.iterator_preferences, action, sequence
        )
        position = self._sequence_positions.get(self.active_custom_position_key, 0) % max(
            1, len(enabled_sequence)
        )
        for row, item_id in enumerate(sequence):
            item = self.config.items_by_id.get(item_id)
            if item is None:
                continue
            entry = QListWidgetItem(f"{row + 1}: {item.label}")
            entry.setData(Qt.ItemDataRole.UserRole, item_id)
            self._style_iterator_item(
                entry,
                item_id not in disabled_iterator_items(self.config.iterator_preferences, action),
            )
            self.custom_iterator_list.addItem(entry)
        if enabled_sequence:
            self._select_custom_iterator_item(enabled_sequence[position])
        elif self.custom_iterator_list.count():
            self.custom_iterator_list.setCurrentRow(0)
        self.pages.setCurrentIndex(self.custom_iterator_page_index)
        self._update_cursor_badge()

    @staticmethod
    def _style_iterator_item(item: QListWidgetItem, enabled: bool) -> None:
        font = item.font()
        font.setStrikeOut(not enabled)
        item.setFont(font)
        item.setForeground(Qt.GlobalColor.white if enabled else Qt.GlobalColor.gray)

    def _save_iterator_preferences(self) -> None:
        self.user_store.save_iterator_preferences(self.config.iterator_preferences)

    def _toggle_custom_iterator_at(self, position: QPoint) -> None:
        item = self.custom_iterator_list.itemAt(position)
        if item is None or not self.active_custom_iterator:
            return
        item_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        preferences = toggle_iterator_item(
            self.config.iterator_preferences,
            self.active_custom_iterator,
            item_id,
        )
        disabled = disabled_iterator_items(preferences, self.active_custom_iterator)
        self.config = replace(self.config, iterator_preferences=preferences)
        self._style_iterator_item(item, item_id not in disabled)
        self._save_iterator_preferences()
        if item_id in disabled and item is self.custom_iterator_list.currentItem():
            self.move_visible_iterator(1)

    def _custom_iterator_reordered(self, *_args) -> None:
        if not self.active_custom_iterator:
            return
        order = [
            str(self.custom_iterator_list.item(row).data(Qt.ItemDataRole.UserRole))
            for row in range(self.custom_iterator_list.count())
        ]
        preferences = set_iterator_order(
            self.config.iterator_preferences,
            self.active_custom_iterator,
            order,
        )
        self.config = replace(self.config, iterator_preferences=preferences)
        current = self.custom_iterator_list.currentItem()
        if current is not None:
            current_id = str(current.data(Qt.ItemDataRole.UserRole) or "")
            configured = (
                self.config.sequences.get(self.active_custom_iterator, [])
                if self.active_custom_iterator in self.config.sequences
                else self.config.custom_sequences.get(self.active_custom_iterator, [])
            )
            enabled = enabled_iterator_sequence(
                self.config.iterator_preferences,
                self.active_custom_iterator,
                configured,
            )
            if current_id in enabled:
                self._sequence_positions[self.active_custom_position_key] = enabled.index(
                    current_id
                )
        self._save_iterator_preferences()

    def _rebuild_skills(self, selected_skill: str = "") -> None:
        self.skills_list.clear()
        selected_row = 0
        for row, skill in enumerate(self.config.effective_skills):
            item = QListWidgetItem(f"{row + 1}: {skill}")
            item.setData(Qt.ItemDataRole.UserRole, skill)
            self.skills_list.addItem(item)
            if skill == selected_skill:
                selected_row = row
        if self.skills_list.count():
            self.skills_list.setCurrentRow(selected_row)

    @staticmethod
    def _skill_value(item: QListWidgetItem | None) -> str:
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or item.text())

    def _answer_search_focus_changed(self, focused: bool) -> None:
        self._answer_search_active = focused
        if hasattr(self, "hotkeys"):
            self.hotkeys.set_suspended(focused)

    @staticmethod
    def _answer_search_score(query: str, title: str) -> float:
        query = query.strip().casefold()
        title = title.casefold()
        if not query:
            return 1.0
        if query in title:
            return 2.0 + len(query) / max(1, len(title))
        phrase_score = difflib.SequenceMatcher(None, query, title).ratio()
        query_words = query.split()
        title_words = title.split()
        if not query_words or not title_words:
            return phrase_score
        word_scores = [max(difflib.SequenceMatcher(None, word, candidate).ratio() for candidate in title_words) for word in query_words]
        return max(phrase_score, sum(word_scores) / len(word_scores))

    def _current_answer_index(self) -> int | None:
        item = self.answer_titles_list.currentItem()
        if item is None:
            return None
        try:
            return int(item.data(Qt.ItemDataRole.UserRole))
        except (TypeError, ValueError):
            return None

    def _rebuild_answer_list(self, selected_index: int | None = None) -> None:
        query = self.answer_search.text().strip() if hasattr(self, "answer_search") else ""
        matches = []
        for index, entry in enumerate(self.config.answers):
            score = self._answer_search_score(query, entry.title)
            if not query or score >= 0.58:
                matches.append((score, index))
        if query:
            matches.sort(key=lambda item: (-item[0], item[1]))
        self.answer_titles_list.blockSignals(True)
        self.answer_titles_list.clear()
        selected_row = -1
        for row, (_score, index) in enumerate(matches):
            item = QListWidgetItem(self.config.answers[index].title)
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.answer_titles_list.addItem(item)
            if index == selected_index:
                selected_row = row
        if self.answer_titles_list.count():
            self.answer_titles_list.setCurrentRow(selected_row if selected_row >= 0 else 0)
        self.answer_titles_list.blockSignals(False)
        if self.answer_titles_list.count():
            self._answer_changed(self.answer_titles_list.currentRow())
        else:
            self.answer_text.clear()

    def _filter_answers(self, _text: str = "") -> None:
        self._rebuild_answer_list(self._current_answer_index())

    def _answers_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("answersPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(3)

        self.answer_search = AnswerSearchEdit(self._answer_search_focus_changed)
        self.answer_search.setObjectName("answerSearch")
        self.answer_search.setPlaceholderText("Search questions…")
        self.answer_search.setClearButtonEnabled(True)
        self.answer_search.setToolTip("Fuzzy search saved questions · Escape clears and exits search")
        self.answer_search.textChanged.connect(self._filter_answers)
        layout.addWidget(self.answer_search)

        self.answer_titles_list = QListWidget()
        self.answer_titles_list.setObjectName("answerTitlesList")
        self.answer_titles_list.setWordWrap(True)
        self.answer_titles_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.answer_titles_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.answer_titles_list.currentRowChanged.connect(self._answer_changed)
        self.answer_titles_list.itemClicked.connect(lambda _item: self.copy_current_answer())
        layout.addWidget(self.answer_titles_list, 2)

        divider = QFrame()
        divider.setObjectName("answersDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        self.answer_text = ClickableTextEdit()
        self.answer_text.setObjectName("answerText")
        self.answer_text.setReadOnly(True)
        self.answer_text.setPlaceholderText("Select a saved Q&A entry")
        self.answer_text.clicked.connect(self.copy_current_answer)
        layout.addWidget(self.answer_text, 1)

        self._rebuild_answer_list()
        return panel

    def _answer_index_for_row(self, row: int) -> int | None:
        item = self.answer_titles_list.item(row)
        if item is None:
            return None
        try:
            return int(item.data(Qt.ItemDataRole.UserRole))
        except (TypeError, ValueError):
            return None

    def _answer_changed(self, row: int) -> None:
        index = self._answer_index_for_row(row)
        if index is not None and 0 <= index < len(self.config.answers):
            self.answer_text.setPlainText(self.config.answers[index].answer)
        else:
            self.answer_text.clear()

    def copy_current_answer(self) -> None:
        index = self._current_answer_index()
        if index is not None and 0 <= index < len(self.config.answers):
            self.clipboard.write(self.config.answers[index].answer)
            self.statusBar().showMessage("Copied to clipboard", 1600)

    def move_answer(self, direction: int) -> None:
        count = self.answer_titles_list.count()
        if count:
            self.answer_titles_list.setCurrentRow((self.answer_titles_list.currentRow() + direction) % count)

    def _rebuild_titles(self, selected_row: int) -> None:
        self.titles_list.blockSignals(True)
        self.titles_list.clear()
        for number, entry in enumerate(self.job_order, start=1):
            item = QListWidgetItem(f"{number}: {entry.title}  —  {entry.company}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self._style_work_entry_item(item, entry.enabled)
            self.titles_list.addItem(item)
        self.titles_list.setCurrentRow(max(0, min(selected_row, len(self.job_order) - 1)))
        self.titles_list.blockSignals(False)
        self._rebuild_job_fields()

    @staticmethod
    def _style_work_entry_item(item: QListWidgetItem, enabled: bool) -> None:
        font = item.font()
        font.setStrikeOut(not enabled)
        item.setFont(font)
        item.setForeground(Qt.GlobalColor.white if enabled else Qt.GlobalColor.gray)

    def _renumber_work_entries(self) -> None:
        for row in range(self.titles_list.count()):
            item = self.titles_list.item(row)
            entry = item.data(Qt.ItemDataRole.UserRole)
            item.setText(f"{row + 1}: {entry.title}  —  {entry.company}")

    def _work_history_reordered(self, *_args) -> None:
        self.job_order = [
            self.titles_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.titles_list.count())
        ]
        self._renumber_work_entries()
        self._save_work_iterator_state()
        self._update_paste_status()

    def _toggle_work_entry_at(self, position: QPoint) -> None:
        item = self.titles_list.itemAt(position)
        if item is None:
            return
        row = self.titles_list.row(item)
        entry = item.data(Qt.ItemDataRole.UserRole)
        updated = replace(entry, enabled=not entry.enabled)
        item.setData(Qt.ItemDataRole.UserRole, updated)
        self.job_order[row] = updated
        self._style_work_entry_item(item, updated.enabled)
        if not updated.enabled and row == self.titles_list.currentRow():
            next_row = self._next_enabled_job_row(row)
            if next_row is not None:
                self.titles_list.setCurrentRow(next_row)
        self._save_work_iterator_state()
        self.statusBar().showMessage(
            f"{'Enabled' if updated.enabled else 'Disabled'}: {updated.title}",
            1800,
        )

    def _save_work_iterator_state(self) -> None:
        self.user_store.save_work_history(
            [
                {
                    "title": entry.title,
                    "company": entry.company,
                    "start": entry.start,
                    "end": entry.end,
                    "highlights": entry.highlights,
                    "enabled": entry.enabled,
                }
                for entry in self.job_order
            ]
        )

    def _next_enabled_job_row(self, current: int) -> int | None:
        return next_cyclic_index(self.job_order, current, lambda entry: entry.enabled)

    def _title_changed(self, _row: int) -> None:
        self._clear_pending_date()
        self._rebuild_job_fields()

    def _rebuild_job_fields(self, selected_row: int | None = None) -> None:
        if not hasattr(self, "job_fields_list"):
            return
        if not self.job_order:
            self.job_fields_list.clear()
            return
        old_row = self.job_fields_list.currentRow()
        self.job_fields_list.blockSignals(True)
        self.job_fields_list.clear()
        labels = {
            "company": "Company",
            "title": "Title",
            "start": "Start",
            "end": "End",
            "highlights": "Bullets",
        }
        for field_name in self.field_order:
            item = QListWidgetItem(labels[field_name])
            item.setData(Qt.ItemDataRole.UserRole, field_name)
            self.job_fields_list.addItem(item)
        row = old_row if selected_row is None else selected_row
        self.job_fields_list.setCurrentRow(max(0, min(row, len(self.field_order) - 1)))
        self.job_fields_list.blockSignals(False)
        self._sync_field_strip()
        self._update_paste_status()

    def _field_changed(self, _row: int) -> None:
        self._clear_pending_date()
        self._sync_field_strip()
        self._update_paste_status()

    def _sync_field_strip(self) -> None:
        if not hasattr(self, "field_buttons"):
            return
        current = self.job_fields_list.currentRow()
        for row, button in enumerate(self.field_buttons):
            button.setChecked(row == current)
            disabled = button.field_name in self.disabled_child_fields
            button.setProperty("childDisabled", "true" if disabled else "false")
            button.style().unpolish(button)
            button.style().polish(button)

    def _toggle_child_iterator(self, field_name: str) -> None:
        if field_name in self.disabled_child_fields:
            self.disabled_child_fields.remove(field_name)
        else:
            self.disabled_child_fields.add(field_name)
        current = self.job_fields_list.currentRow()
        if current >= 0 and self.field_order[current] in self.disabled_child_fields:
            next_row = self._next_enabled_field_row(current)
            if next_row is not None:
                self.job_fields_list.setCurrentRow(next_row)
        self._sync_field_strip()

    def _move_child_iterator(self, source: str, target: str) -> None:
        if source not in self.field_order or target not in self.field_order:
            return
        current_name = self.field_order[self.job_fields_list.currentRow()]
        self.field_order.remove(source)
        self.field_order.insert(self.field_order.index(target), source)
        by_name = {button.field_name: button for button in self.field_buttons}
        layout = self.field_strip.layout()
        self.field_buttons = [by_name[name] for name in self.field_order]
        for button in self.field_buttons:
            layout.removeWidget(button)
            layout.addWidget(button, 1)
            button.setDown(False)
        QTimer.singleShot(0, lambda: [button.setDown(False) for button in self.field_buttons])
        self._rebuild_job_fields(self.field_order.index(current_name))

    def _next_enabled_field_row(self, current: int) -> int | None:
        return next_cyclic_index(
            self.field_order,
            current,
            lambda field: field not in self.disabled_child_fields,
        )

    def _update_paste_status(self) -> None:
        if not hasattr(self, "job_fields_list") or self.job_fields_list.currentRow() < 0:
            return
        field_row = self.job_fields_list.currentRow()
        field_name = self.field_order[field_row]
        if field_name in self.disabled_child_fields:
            next_field = self._next_enabled_field_row(field_row)
            if next_field is None:
                self.statusBar().showMessage("No enabled child iterators")
                return
            self.job_fields_list.setCurrentRow(next_field)
            field_row = next_field
            field_name = self.field_order[field_row]
        # The pane and cursor badge already identify the current iterator. Keeping
        # that information out of the status bar prevents it from overwriting
        # save confirmations, format changes, and actionable errors.

    def _keyboard_layout_rows(self) -> list[list[str]]:
        return resolve_keyboard_layout(
            self._keyboard_layout_name,
            self._keyboard_custom_layouts,
        )

    def _matrix_panel(self) -> QWidget:
        panel = Panel("")
        panel.setObjectName("matrixPanel")
        panel.layout.setContentsMargins(0, 4, 0, 4)
        panel.layout.setSpacing(0)
        self.base_guide_labels = {}
        self.matrix_grid = QGridLayout()
        self.matrix_grid.setContentsMargins(0, 0, 0, 0)
        self.matrix_grid.setHorizontalSpacing(3)
        self.matrix_grid.setVerticalSpacing(2)
        self.matrix_grid.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom
        )
        panel.layout.addLayout(self.matrix_grid)
        self._rebuild_matrix_layout()
        return panel

    def _rebuild_matrix_layout(self) -> None:
        while self.matrix_grid.count():
            item = self.matrix_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._matrix_buttons.clear()
        self.base_guide_labels = {}

        for row, keys in enumerate(self._keyboard_layout_rows()):
            for col, key in enumerate(keys):
                if not key:
                    continue
                config_key = self._matrix_config_key(key)
                binding = self.config.matrix.get(config_key, "")
                action, label_override = split_binding(binding)
                action_label = label_override or self._action_label(action)
                self.base_guide_labels[key] = action_label
                if len(action_label) > 12:
                    action_label = action_label[:11] + "…"
                btn = MatrixButton()
                btn.setFixedSize(92, 54)
                btn.setText(action_label)
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                btn.setProperty("class", "matrix")
                btn.setProperty("assigned", "true")
                key_label = QLabel(key, btn)
                key_label.setObjectName("matrixKey")
                key_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                key_label.adjustSize()
                key_label.move(8, 5)
                key_label.raise_()
                if action:
                    btn.clicked.connect(partial(self.handle_global_key, config_key))
                self.matrix_grid.addWidget(btn, row, col)
                self._matrix_buttons[key] = btn
        self._refresh_matrix_labels()

    @staticmethod
    def _matrix_config_key(key: str) -> str:
        return "ENTER" if key == "Return" else key.upper()

    def _action_label(self, action: str) -> str:
        if not action:
            return ""
        item = self.config.items_by_id.get(action)
        if item:
            return item.label
        return self.config.action_labels.get(action, action.replace("_", " ").title())

    def _action_icon(self, action: str) -> tuple[QIcon, QSize]:
        display = self.config.action_displays.get(action, {})
        icons = [name for name in display.get("icons", []) if name in ICON_SVGS][:2]
        if not icons:
            return QIcon(), QSize()
        icon_size = 16
        pixmap = QPixmap(icon_size * len(icons), icon_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        for index, name in enumerate(icons):
            svg = ICON_SVGS[name].replace("currentColor", "#e7eaf0")
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            renderer.render(painter, QRectF(index * icon_size, 0, icon_size, icon_size))
        painter.end()
        return QIcon(pixmap), pixmap.size()

    @staticmethod
    def _single_icon_pixmap(name: str, size: int = 12, color: str = "#e7eaf0") -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        svg = ICON_SVGS[name].replace("currentColor", color)
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        return pixmap

    def _poll_shift_visual(self) -> None:
        self._poll_capture_press()
        if sys.platform != "win32":
            return
        self._poll_escape_long_press()
        layer2_enabled = (
            self.config.hotkey_settings.get("layers", {}).get("layer2", {}).get("enabled", True)
        )
        layer2_hold_enabled = (
            self.config.hotkey_settings.get("layers", {}).get("layer2", {}).get("hold", True)
        )
        layer3_enabled = (
            self.config.hotkey_settings.get("layers", {}).get("layer3", {}).get("enabled", True)
        )
        shift_held = self.keyboard.is_key_down("SHIFT")
        layer3_hold_keys = [
            key
            for bindings in (self.config.matrix, self.config.layer2, self.config.layer3)
            for key, binding in bindings.items()
            if split_binding(binding)[0] == "layer3_hold" and len(key) == 1 and key.isalnum()
        ]
        layer3_held = layer3_enabled and any(
            self.keyboard.is_key_down(key) for key in layer3_hold_keys
        )
        held_layer = (
            "Layer 3"
            if layer3_held
            else "Layer 2"
            if layer2_enabled and layer2_hold_enabled and shift_held
            else self.latched_layer
        )
        if self.pages.currentIndex() == 1:
            layer2_held = held_layer == "Layer 2"
            if layer2_held and not self._modifier_was_held and not self.isActiveWindow():
                self.copy_current_answer()
            self._modifier_was_held = layer2_held
            return
        self._modifier_was_held = held_layer != "Base"
        if self.layer != held_layer:
            self.layer = held_layer
            self._update_matrix_layer_name()

    def _poll_escape_long_press(self) -> None:
        if self.isActiveWindow():
            self._escape_hold_started = None
            self._escape_hold_fired = False
            return
        escape_held = self.keyboard.is_key_down("ESC")
        if not escape_held:
            self._escape_hold_started = None
            self._escape_hold_fired = False
            return
        if self._escape_hold_started is None:
            self._escape_hold_started = time.monotonic()
            return
        threshold_ms = (
            self.escape_long_press.value()
            if hasattr(self, "escape_long_press")
            else self.config.escape_long_press_ms
        )
        elapsed_ms = (time.monotonic() - self._escape_hold_started) * 1000
        if not self._escape_hold_fired and elapsed_ms >= threshold_ms:
            self._escape_hold_fired = True
            self._close_iterator_pane()

    def _close_iterator_pane(self) -> None:
        if self._settings_open or self.pages.currentIndex() == 3:
            return
        if self.pages.currentIndex() == 1:
            self._restore_keyboard_after_answers()
        if self.pages.currentIndex() == self.capture_page_index:
            self._restore_capture_focus()
        self.pages.setCurrentIndex(3)
        self._refresh_matrix_labels()
        self._update_cursor_badge()

    def _capture_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("settingsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self.capture_session_status = QLabel("No active capture session")

        self.capture_content_section = CollapsibleSettingsSection("Captured content (0)")
        self.capture_list = QListWidget()
        self.capture_list.setObjectName("captureList")
        self.capture_list.setWordWrap(True)
        self.capture_content_section.content_layout.addWidget(self.capture_list)
        layout.addWidget(self.capture_content_section)

        self.capture_company_label = QLabel("")
        self.capture_company_label.setObjectName("captureCompany")
        self.capture_company_label.setWordWrap(True)
        self.capture_title_label = QLabel("")
        self.capture_title_label.setObjectName("captureTitle")
        self.capture_title_label.setWordWrap(True)
        layout.addWidget(self.capture_company_label)
        layout.addWidget(self.capture_title_label)

        self.capture_fields_list = QListWidget()
        self.capture_fields_list.setObjectName("captureFieldsList")
        self.capture_fields_list.setWordWrap(True)
        layout.addWidget(self.capture_fields_list, 1)

        self.capture_analysis_status = QLabel("Parser ready")
        self.capture_analysis_status.setObjectName("captureAnalysisStatus")
        self.capture_analysis_status.setWordWrap(True)
        layout.addWidget(self.capture_analysis_status)

        self.capture_job_section = CollapsibleSettingsSection("Job details")
        self.capture_job_identity = QLabel("No analyzed job selected")
        self.capture_job_identity.setWordWrap(True)
        self.capture_open_analysis = QPushButton("Open Tracker")
        self.capture_open_analysis.clicked.connect(self.open_dashboard)
        self.capture_job_section.content_layout.addWidget(self.capture_job_identity)
        self.capture_job_section.content_layout.addWidget(
            self.capture_open_analysis, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.capture_job_section.set_expanded(False)
        self.capture_job_section.hide()
        layout.addWidget(self.capture_job_section)

        self.capture_questions_section = CollapsibleSettingsSection("Application Q&A (0)")
        self.capture_questions_list = QListWidget()
        self.capture_questions_list.setObjectName("captureQuestionsList")
        self.capture_questions_list.setWordWrap(True)
        self.capture_questions_section.content_layout.addWidget(self.capture_questions_list)
        layout.addWidget(self.capture_questions_section)

        self.capture_content_section.set_expanded(False)
        self.capture_content_section.setMaximumHeight(
            self.capture_content_section.header.height() + 2
        )
        self.capture_content_section.header.toggled.connect(
            lambda expanded: self.capture_content_section.setMaximumHeight(
                16777215 if expanded else self.capture_content_section.header.height() + 2
            )
        )
        self.capture_questions_section.set_expanded(False)
        self.capture_questions_section.hide()
        return panel

    def _active_user_id(self) -> int:
        return int(self._desktop_active_user_id)

    def _show_capture_pane(self) -> None:
        self.database.get_or_create_capture_session(self._active_user_id())
        self._refresh_capture_pane()
        self.pages.setCurrentIndex(self.capture_page_index)
        self._apply_capture_focus()
        self._refresh_matrix_labels()
        self._update_cursor_badge()
        if self._capture_has_content_cache:
            QTimer.singleShot(0, self._start_capture_verification)

    def _refresh_capture_pane(self) -> None:
        session = self.capture_service.refresh_session(self._active_user_id())
        events = session.get("events", [])
        self._capture_has_content_cache = bool(events)
        self.capture_content_section.title = f"Captured content ({len(events)})"
        self.capture_content_section._update_header()
        self._refresh_capture_journal(events)
        application_phase = session.get("phase") == "application"
        self.capture_content_section.setVisible(not application_phase)
        self.capture_fields_list.setVisible(not application_phase)
        if application_phase:
            self.capture_company_label.hide()
            self.capture_title_label.hide()
        self.capture_analysis_status.setVisible(not application_phase)
        self.capture_job_section.setVisible(application_phase)
        self.capture_questions_section.setVisible(application_phase)
        if application_phase:
            job_id = session.get("job_id") or self.active_job_id
            job = self.database.get_job(int(job_id)) if job_id else None
            if job:
                company = str(job.get("company") or "Unknown company")
                title = str(job.get("title") or "Unknown title")
                self.capture_job_identity.setText(f"Q&A for:\n{company}\n{title}\nJob #{job_id}")
                self.capture_open_analysis.setEnabled(True)
            else:
                self.capture_job_identity.setText("No analyzed job selected")
                self.capture_open_analysis.setEnabled(False)
        self.capture_session_status.setText(
            f"{('Application' if session.get('phase') == 'application' else 'Job')} "
            f"session #{session['id']} · {len(events)} captured selection"
            f"{'s' if len(events) != 1 else ''}"
        )
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
            empty = QListWidgetItem("No selections captured yet")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.capture_list.addItem(empty)
        if hasattr(self, "_matrix_buttons"):
            self._refresh_matrix_labels()

    def _refresh_capture_journal(self, events: list[dict]) -> None:
        self._populate_capture_summary(events)
        return

    def _parser_capture_values(
        self,
        events: list[dict],
    ) -> tuple[dict[str, tuple[str, ...]], str]:
        extractions: list[dict] = []
        for event in events:
            metadata = self._capture_metadata(event)
            extraction = metadata.get("extraction", {})
            if isinstance(extraction, dict):
                extractions.append(extraction)
        combined = combine_capture_text(events)
        return collect_parser_values(extractions, combined), combined

    @staticmethod
    def _capture_source_badge(source: str) -> str:
        return {
            "ai": "  · AI",
            "both": "  · ✓",
            "conflict": "  · ⚠ review",
        }.get(source, "")

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
            value = field.display_value or "—"
            item = QListWidgetItem(
                f"{field.label}: {value}{self._capture_source_badge(field.source)}"
            )
            item.setToolTip(self._capture_field_tooltip(field))
            tone = capture_tone(field, settings)
            if tone in tone_colors:
                item.setForeground(tone_colors[tone])
            self.capture_fields_list.addItem(item)

        if insights:
            for insight in insights:
                item = QListWidgetItem(f"AI insight: {insight}")
                item.setForeground(QColor("#9fcaf0"))
                self.capture_fields_list.addItem(item)

        if not self.capture_fields_list.count():
            item = QListWidgetItem("No selected fields detected yet")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.capture_fields_list.addItem(item)

        nonempty = [field for field in fields.values() if field.values]
        reviews = sum(1 for field in nonempty if field.conflict)
        ai_verified = sum(1 for field in nonempty if field.source in {"ai", "both", "conflict"})
        if settings["analysis_mode"] == "parser":
            status = "Parser complete"
        elif self._capture_verification_state == "checking":
            status = "Parser complete · AI checking…"
        elif self._capture_verification_state == "verified":
            status = f"Parser complete · AI verified {ai_verified}/{len(nonempty)}"
            if reviews:
                status += f" · {reviews} review"
            if self._capture_verification_model:
                status += f" · {self._capture_verification_model}"
        elif self._capture_verification_state == "failed":
            status = f"Parser complete · AI unavailable: {self._capture_verification_error}"
        else:
            status = "Parser complete · AI ready"
        self.capture_analysis_status.setText(status)

        questions: list[str] = []
        for event in events:
            extraction = self._capture_metadata(event).get("extraction", {})
            if not isinstance(extraction, dict):
                continue
            for question in extraction.get("application_questions", []):
                normalized = str(question).strip()
                if normalized and normalized not in questions:
                    questions.append(normalized)
        self.capture_questions_list.clear()
        self.capture_questions_section.title = f"Application Q&A ({len(questions)})"
        self.capture_questions_section._update_header()
        for number, question in enumerate(questions, start=1):
            self.capture_questions_list.addItem(f"{number}. {question}")
        if not questions:
            item = QListWidgetItem("No application questions detected")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.capture_questions_list.addItem(item)

    @staticmethod
    def _capture_field_tooltip(field) -> str:
        source = {
            "parser": "Parser",
            "ai": "Ollama",
            "both": "Parser + Ollama",
            "conflict": "Parser / Ollama disagreement",
            "none": "No source",
        }.get(field.source, field.source)
        details = [f"Source: {source}", f"Confidence: {field.confidence:.0%}"]
        if field.evidence:
            details.append(f"AI evidence: {field.evidence}")
        return "\n".join(details)

    def _apply_capture_focus(self) -> None:
        settings = normalize_smart_capture_settings(self.config.smart_capture_settings)
        if not settings["focus_mode"] or not hasattr(self, "keyboard_panel"):
            return
        if self._capture_restore_keyboard is None:
            self._capture_restore_keyboard = self.keyboard_panel.isVisible()
            self._capture_restore_divider = self.pane_matrix_divider.isVisible()
        self.keyboard_panel.hide()
        self.pane_matrix_divider.hide()

    def _restore_capture_focus(self) -> None:
        if self._capture_restore_keyboard is None:
            return
        self.keyboard_panel.setVisible(
            bool(self._capture_restore_keyboard) and self.config.show_keyboard
        )
        self.pane_matrix_divider.setVisible(bool(self._capture_restore_divider))
        self._capture_restore_keyboard = None
        self._capture_restore_divider = None

    def _start_capture_verification(self) -> None:
        settings = normalize_smart_capture_settings(self.config.smart_capture_settings)
        if settings["analysis_mode"] == "parser":
            self._capture_verification_state = "parser"
            self._capture_ai_payload = None
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

    def _capture_verification_completed(
        self,
        generation: int,
        payload: dict,
        model: str,
    ) -> None:
        current = generation == self._capture_verification_generation
        self.capture_verification_worker = None
        if current:
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
            self._capture_has_content_cache = False
            self._refresh_capture_pane()
            self.statusBar().showMessage("Capture cleared · New session started")
        if not held:
            self._finish_capture_press()

    def _finish_capture_press(self) -> None:
        if self._capture_press_started is None:
            return
        opened_pane = self._capture_press_opened_pane
        long_fired = self._capture_long_press_fired
        capture_allowed = self._capture_press_can_capture
        self._capture_press_started = None
        self._capture_press_key = ""
        self._capture_press_opened_pane = False
        self._capture_long_press_fired = False
        self._capture_press_can_capture = True
        if long_fired or opened_pane or not capture_allowed:
            return
        self._copy_capture_selection()

    def _copy_capture_selection(self) -> None:
        sentinel = f"__JAW_CAPTURE_{uuid.uuid4().hex}__"
        self.clipboard.write(sentinel)
        self.keyboard.copy_selection()
        QTimer.singleShot(
            180,
            lambda: self._accept_capture_selection(
                "" if self.clipboard.read() == sentinel else self.clipboard.read()
            ),
        )

    def _accept_capture_selection(self, content: str) -> None:
        try:
            normalized = self.capture_service.normalize_selection(content)
        except CaptureValidationError as error:
            self.statusBar().showMessage(str(error))
            return
        acceptance = self.capture_service.accept_text(
            self._active_user_id(),
            normalized,
        )
        self._capture_ai_payload = None
        self._capture_verification_state = "parser"
        self._capture_verification_error = ""
        self._refresh_capture_pane()
        QTimer.singleShot(0, self._start_capture_verification)
        label = acceptance.classification.content_type.replace("_", " ").title()
        self.statusBar().showMessage(f"Smart Capture · {label}", 1800)

    @staticmethod
    def _capture_metadata(event: dict) -> dict:
        return CaptureService.capture_metadata(event)

    def _update_matrix_layer(self, layer2: bool) -> None:
        self.layer = "Layer 2" if layer2 else "Base"
        if layer2:
            self.layer_badge.setText("LAYER 2")
        else:
            self.layer_badge.setText("BASE LAYER" if self.hotkeys_enabled else "HOTKEYS OFF")
        self._refresh_matrix_labels()
        self._refresh_layer_status_button()

    def _refresh_matrix_labels(self) -> None:
        active_bindings = (
            self.config.layer2
            if self.layer == "Layer 2"
            else self.config.layer3
            if self.layer == "Layer 3"
            else None
        )
        for key, button in self._matrix_buttons.items():
            config_key = self._matrix_config_key(key)
            binding = self.config.matrix.get(config_key, "")
            assignment, label_override = split_binding(binding)
            label = label_override or self._action_label(assignment)
            if active_bindings is not None:
                binding = active_bindings.get(config_key, "")
                assignment, label_override = split_binding(binding)
                if assignment:
                    label = label_override or self._action_label(assignment)
                elif key not in {"Shift"}:
                    label = ""
            runtime_bindings = active_bindings or self.config.matrix
            resolved_assignment = self._resolve_layer_binding(config_key, runtime_bindings)
            if resolved_assignment != assignment:
                assignment = resolved_assignment
                label = self._action_label(assignment)
            if len(label) > 12:
                label = label[:11] + "…"
            icon, icon_size = self._action_icon(assignment)
            button.setIcon(icon)
            if not icon_size.isEmpty():
                button.setIconSize(icon_size)
            button.setText(label)
            button.setEnabled(
                self._capture_has_content_cache if assignment == "analyze_job" else True
            )
            if isinstance(button, MatrixButton):
                button.corner_icon.hide()

    def trigger_matrix(self, key: str) -> None:
        bindings = (
            self.config.layer2
            if self.layer == "Layer 2"
            else self.config.layer3
            if self.layer == "Layer 3"
            else self.config.matrix
        )
        assignment = self._resolve_layer_binding(key, bindings)
        self._dispatch_action(assignment, key, paste=False)

    def _resolve_layer_binding(self, key: str, bindings: dict[str, str]) -> str:
        """Keep layer cycle/toggle controls reachable from every active layer."""
        return resolve_layer_binding(
            key,
            bindings,
            (self.config.matrix, self.config.layer2, self.config.layer3),
        )

    def trigger_sequence(self, action: str, paste: bool = True) -> None:
        configured_sequence = self.config.sequences.get(action, [])
        if not configured_sequence:
            return
        if (
            self.pages.currentIndex() != self.custom_iterator_page_index
            or self.active_custom_iterator != action
        ):
            self._show_sequence_iterator(action, configured_sequence)
            return
        sequence = enabled_iterator_sequence(
            self.config.iterator_preferences, action, configured_sequence
        )
        if not sequence:
            self.statusBar().showMessage(f"{self._action_label(action)}: no enabled iterator items")
            return
        position = self._sequence_positions.get(action, 0) % len(sequence)
        item = self.config.items_by_id.get(sequence[position])
        if not item or not item.value:
            self.statusBar().showMessage(f"{self._action_label(action)}: configured value is empty")
            return
        self._sequence_positions[action] = position + 1
        self.clipboard.write(item.value)
        if paste:
            self._paste_then_maybe_return(action.removeprefix("iterate_"))
        next_item_id = sequence[self._sequence_positions[action] % len(sequence)]
        self._select_custom_iterator_item(next_item_id)

    def trigger_custom_sequence(self, action: str, paste: bool = True) -> None:
        configured_sequence = self.config.custom_sequences.get(action, [])
        if not configured_sequence:
            self.statusBar().showMessage(f"{self._action_label(action)}: no Custom Data selected")
            return
        if (
            self.pages.currentIndex() != self.custom_iterator_page_index
            or self.active_custom_iterator != action
        ):
            self._show_sequence_iterator(action, configured_sequence)
            return
        sequence = enabled_iterator_sequence(
            self.config.iterator_preferences, action, configured_sequence
        )
        if not sequence:
            self.statusBar().showMessage(f"{self._action_label(action)}: no enabled iterator items")
            return
        position = self._sequence_positions.get(action, 0) % len(sequence)
        item = self.config.items_by_id.get(sequence[position])
        if not item or not item.value:
            self.statusBar().showMessage(f"{self._action_label(action)}: configured value is empty")
            return
        self._sequence_positions[action] = position + 1
        self.clipboard.write(item.value)
        if paste:
            self._paste_then_maybe_return(action)
        next_item_id = sequence[self._sequence_positions[action] % len(sequence)]
        self._select_custom_iterator_item(next_item_id)

    def _select_custom_iterator_item(self, item_id: str) -> None:
        for row in range(self.custom_iterator_list.count()):
            item = self.custom_iterator_list.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == item_id:
                self.custom_iterator_list.setCurrentRow(row)
                return

    def show_mode(self, mode: int) -> None:
        if mode != 3:
            return
        self._refresh_matrix_labels()
        if self.pages.currentIndex() == 1:
            self.pages.setCurrentIndex(0)
            self.keyboard_panel.setVisible(self._keyboard_before_answers)
        else:
            self._keyboard_before_answers = self.keyboard_panel.isVisible()
            self.pages.setCurrentIndex(1)
            self.keyboard_panel.hide()

    def _restore_keyboard_after_answers(self) -> None:
        if self.pages.currentIndex() == 1:
            self.keyboard_panel.setVisible(self._keyboard_before_answers)

    def trigger_layer2(self, key: str) -> None:
        assignment = self._resolve_layer_binding(key, self.config.layer2)
        if assignment == "toggle_hotkeys":
            self.hotkeys_enabled = not self.hotkeys_enabled
            self.hotkeys.set_enabled(self.hotkeys_enabled)
            self.statusBar().showMessage(
                "Hotkeys enabled"
                if self.hotkeys_enabled
                else "Hotkeys disabled · Shift+Space remains active",
                1600,
            )
            if self.layer != "Layer 2":
                self.layer_badge.setText("BASE LAYER" if self.hotkeys_enabled else "HOTKEYS OFF")
            return
        if assignment == "previous_iterator":
            self.move_visible_iterator(-1)
            return
        if assignment == "next_iterator":
            self.move_visible_iterator(1)
            return
        if assignment in {"cycle_layers", "layer3_hold"}:
            self._dispatch_action(assignment, key, paste=True)
            return
        if (
            assignment in self.config.action_labels
            or assignment in self.config.sequences
            or assignment in self.config.custom_sequences
        ):
            self._dispatch_action(assignment, key, paste=True)
            return
        if self.isActiveWindow():
            self.statusBar().showMessage("Paste actions are paused while JAW has focus")
            return
        item = self.config.items_by_id.get(assignment)
        if not item or not item.value:
            self.statusBar().showMessage(f"Shift+{key}: no Layer 2 binding")
            return
        self.clipboard.write(item.value)
        QTimer.singleShot(20, self._paste_clipboard_if_unfocused)
        self._schedule_iterator_return("name")

    def paste_current_work_exp(self, trigger_key: str = "") -> None:
        if self._job_paste_pending or not self.job_order or self.job_fields_list.currentRow() < 0:
            return
        job_row = max(0, self.titles_list.currentRow())
        entry = self.job_order[job_row]
        if not entry.enabled:
            next_row = self._next_enabled_job_row(job_row)
            if next_row is None:
                self.statusBar().showMessage("No enabled Work Experience entries")
                return
            self.titles_list.setCurrentRow(next_row)
            job_row = next_row
            entry = self.job_order[job_row]
        field_name = self.field_order[self.job_fields_list.currentRow()]
        raw_value = getattr(entry, field_name)
        value = raw_value
        self._job_advance_after_paste = True
        if field_name in {"start", "end"}:
            date_format: DateFormat = self.date_format.currentData()
            context = (job_row, field_name, date_format)
            if self._pending_date_context != context or not self._pending_date_values:
                try:
                    month_text, year_text = raw_value.split("/", 1)
                    date_value = date(int(year_text), int(month_text), 1)
                    values = date_format.values_for(date_value)
                except (TypeError, ValueError):
                    values = [raw_value]
                value = values[0]
                self._pending_date_values = values[1:]
                self._pending_date_context = context
            else:
                value = self._pending_date_values.pop(0)
            self._job_advance_after_paste = not self._pending_date_values
            if self._job_advance_after_paste:
                self._pending_date_context = None
        else:
            self._clear_pending_date()
        self.clipboard.write(value)
        self._job_paste_trigger_key = str(trigger_key).upper()
        self._job_paste_pending = True
        self._paste_work_exp_after_key_release()

    def _paste_work_exp_after_key_release(self) -> None:
        if (
            self._job_paste_trigger_key
            and self.keyboard.is_key_down(self._job_paste_trigger_key)
        ):
            QTimer.singleShot(10, self._paste_work_exp_after_key_release)
            return
        QTimer.singleShot(25, self._finish_work_exp_paste)

    def _finish_work_exp_paste(self) -> None:
        if self.isActiveWindow():
            self._job_paste_pending = False
            self._job_paste_trigger_key = ""
            self.statusBar().showMessage("Paste canceled because JAW has focus")
            return
        self.keyboard.paste_clipboard()
        self._schedule_iterator_return("work_exp")
        if self._job_advance_after_paste:
            current_row = self.job_fields_list.currentRow()
            next_row = self._next_enabled_field_row(current_row)
            if next_row is not None:
                self.job_fields_list.setCurrentRow(next_row)
            if next_row is not None and next_row <= current_row:
                next_job = self._next_enabled_job_row(self.titles_list.currentRow())
                if next_job is not None:
                    self.titles_list.setCurrentRow(next_job)
        self._job_paste_pending = False
        self._job_paste_trigger_key = ""

    def show_skills(self) -> None:
        self._restore_keyboard_after_answers()
        self._refresh_matrix_labels()
        self.pages.setCurrentIndex(2)

    def move_skill_iterator(self, direction: int) -> None:
        if self.pages.currentIndex() != 2:
            self.show_skills()
            return
        count = self.skills_list.count()
        if not count:
            return
        self.skills_list.setCurrentRow((self.skills_list.currentRow() + direction) % count)

    def move_work_field_iterator(self, direction: int) -> None:
        if not self.field_order or self.job_fields_list.currentRow() < 0:
            return
        row = cyclic_enabled_index(
            self.field_order,
            self.job_fields_list.currentRow(),
            direction,
            lambda field: field not in self.disabled_child_fields,
        )
        if row is not None:
            self.job_fields_list.setCurrentRow(row)

    def move_work_experience_iterator(self, direction: int) -> None:
        if not self.job_order:
            return
        current = max(0, self.titles_list.currentRow())
        row = cyclic_enabled_index(
            self.job_order,
            current,
            direction,
            lambda entry: entry.enabled,
        )
        if row is not None:
            self.titles_list.setCurrentRow(row)

    def move_visible_iterator(self, direction: int) -> None:
        if self.pages.currentIndex() == 0:
            self.move_work_field_iterator(direction)
        elif self.pages.currentIndex() == 2:
            self.move_skill_iterator(direction)
        elif self.pages.currentIndex() == self.custom_iterator_page_index:
            count = self.custom_iterator_list.count()
            if count:
                current = self.custom_iterator_list.currentRow()
                disabled = disabled_iterator_items(
                    self.config.iterator_preferences,
                    self.active_custom_iterator,
                )
                for offset in range(1, count + 1):
                    row = (current + direction * offset) % count
                    item = self.custom_iterator_list.item(row)
                    item_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
                    if item_id not in disabled:
                        self.custom_iterator_list.setCurrentRow(row)
                        configured = (
                            self.config.sequences.get(self.active_custom_iterator, [])
                            if self.active_custom_iterator in self.config.sequences
                            else self.config.custom_sequences.get(self.active_custom_iterator, [])
                        )
                        enabled = enabled_iterator_sequence(
                            self.config.iterator_preferences,
                            self.active_custom_iterator,
                            configured,
                        )
                        if item_id in enabled:
                            self._sequence_positions[self.active_custom_position_key] = (
                                enabled.index(item_id)
                            )
                        self._update_cursor_badge()
                        break
        elif self.pages.currentIndex() == 0:
            count = self.job_fields_list.count()
            if count:
                current = self.job_fields_list.currentRow()
                for offset in range(1, count + 1):
                    row = (current + direction * offset) % count
                    if self.field_order[row] not in self.disabled_child_fields:
                        self.job_fields_list.setCurrentRow(row)
                        break
                self._update_paste_status()

    def iterate_skill(self) -> None:
        if self.pages.currentIndex() != 2:
            self.show_skills()
            return
        item = self.skills_list.currentItem()
        if item is None:
            return
        skill = self._skill_value(item)
        self.clipboard.write(skill)
        self._paste_then_maybe_return("skills")
        self.move_skill_iterator(1)

    def _auto_return_enabled(self, category: str | None) -> bool:
        if not category:
            return False
        checkbox = self.auto_return_checks.get(category)
        if checkbox is not None:
            return checkbox.isChecked()
        return self.config.custom_action_auto_return.get(
            category, self.config.auto_return.get(category, False)
        )

    def _paste_then_maybe_return(self, category: str | None) -> None:
        """Paste first, then optionally send Return after the configured delay."""
        paste_delay_ms = 20
        QTimer.singleShot(paste_delay_ms, self._paste_clipboard_if_unfocused)
        if self._auto_return_enabled(category):
            QTimer.singleShot(
                paste_delay_ms + self.iterator_delay.value(),
                self._return_if_unfocused,
            )

    def _schedule_iterator_return(self, category: str) -> None:
        if self._auto_return_enabled(category):
            QTimer.singleShot(self.iterator_delay.value(), self._return_if_unfocused)

    def _paste_clipboard_if_unfocused(self) -> None:
        if not self.isActiveWindow():
            self.keyboard.paste_clipboard()

    def _return_if_unfocused(self) -> None:
        if not self.isActiveWindow():
            self.keyboard.relay_key(0x0D)

    def _capture_selection(self, trigger_key: str, callback) -> None:
        if self.keyboard.is_key_down(trigger_key):
            QTimer.singleShot(10, lambda: self._capture_selection(trigger_key, callback))
            return
        self.keyboard.copy_selection()
        QTimer.singleShot(180, lambda: callback(self.clipboard.read().strip()))

    def start_brief(self) -> None:
        if self.brief_worker and self.brief_worker.isRunning():
            self.statusBar().showMessage("Brief analysis already running")
            return
        self.statusBar().showMessage("Brief: copying highlighted job description…")
        self._capture_selection("B", self._analyze_captured_job)

    def _analyze_captured_job(self, description: str) -> None:
        if len(description) < 40:
            self.statusBar().showMessage(
                "Brief canceled: highlight the complete job description first"
            )
            return
        user_id = self._active_user_id()
        self.brief_worker = BriefWorker(
            self.analysis_service,
            description,
            user_id,
        )
        self.brief_worker.completed.connect(self._brief_completed)
        self.brief_worker.failed.connect(self._brief_failed)
        self.brief_worker.start()
        source = self.config.openai_model if self.analyzer.uses_generative_ai else "Local Analyzer"
        self.statusBar().showMessage(f"Brief: analyzing with {source}…")

    def _enter_application_capture_mode(self) -> None:
        """Hook for Smart Capture UI after job analysis completes."""

    def _brief_completed(self, job_id: int, model: str) -> None:
        self.active_job_id = job_id
        self.database.set_capture_phase(self._active_user_id(), "application", job_id)
        if self.pages.currentIndex() == self.capture_page_index:
            self._refresh_capture_pane()
        self._enter_application_capture_mode()
        self.open_dashboard()
        self.statusBar().showMessage(f"Analysis complete · job #{job_id} · {model}", 2400)

    def _brief_failed(self, job_id: int, message: str) -> None:
        if job_id:
            self.active_job_id = job_id
        self.statusBar().showMessage(f"Brief captured, analysis failed: {message}")

    def open_dashboard(self) -> None:
        suffix = f"/?job={self.active_job_id}" if self.active_job_id else ""
        self.browser.open(f"{self.dashboard.url}{suffix}")

    def find_company_in_tracker(self, trigger_key: str) -> None:
        """Search Tracker for the company name currently selected on screen."""
        self.statusBar().showMessage("Tracker lookup: copying highlighted company…")
        self._capture_selection(trigger_key, self._open_company_in_tracker)

    def _open_company_in_tracker(self, company: str) -> None:
        normalized = " ".join(company.split())
        if not normalized:
            self.statusBar().showMessage(
                "Tracker lookup canceled: highlight a company name first"
            )
            return
        if len(normalized) > 120:
            self.statusBar().showMessage(
                "Tracker lookup canceled: select only the company name"
            )
            return
        query = urlencode({"q": normalized})
        self.browser.open(f"{self.dashboard.url}/?{query}#tracker")
        self.statusBar().showMessage(f"Tracker search · {normalized}", 2400)

    def _analyze_capture_journal(self) -> None:
        session = self.capture_service.refresh_session(self._active_user_id())
        if session.get("phase") == "application" and session.get("job_id"):
            self.active_job_id = int(session["job_id"])
            self.statusBar().showMessage(
                f"Capture already analyzed · job #{self.active_job_id}",
                1800,
            )
            return
        description = "\n\n".join(
            str(event.get("content", "")).strip()
            for event in session.get("events", [])
            if str(event.get("content", "")).strip()
        )
        if not description:
            self.statusBar().showMessage(
                "Analysis canceled · Capture journal is empty",
                1800,
            )
            return
        self._analyze_captured_job(description)

    def _matching_config_answer(self, question: str) -> str:
        if not self.config.answers:
            return ""
        normalized = question.casefold()
        best = max(
            self.config.answers,
            key=lambda entry: difflib.SequenceMatcher(
                None, normalized, entry.title.casefold()
            ).ratio(),
        )
        ratio = difflib.SequenceMatcher(None, normalized, best.title.casefold()).ratio()
        return best.answer if ratio >= 0.45 else ""

    def handle_global_key(self, key: str) -> None:
        self._poll_sync_revisions(force=True)
        if self._answer_search_active and key != "SPECIAL:window":
            return
        if key == "SPECIAL:toggle":
            self.hotkeys_enabled = not self.hotkeys_enabled
            self.hotkeys.set_enabled(self.hotkeys_enabled)
            self._update_hotkeys_visual_state()
            self.layer_badge.setText("BASE LAYER" if self.hotkeys_enabled else "HOTKEYS OFF")
            self.statusBar().showMessage(
                "Hotkeys enabled" if self.hotkeys_enabled else "Hotkeys disabled",
                1600,
            )
            return
        if key == "SPECIAL:window":
            if self.isMinimized():
                self.showNormal()
                self.raise_()
                self.activateWindow()
                self.hotkeys.set_suspended(False)
                self._wake_sync()
            else:
                self.cursor_badge.update_badge("")
                self.showMinimized()
                if self.config.hotkey_settings.get("disable_when_minimized"):
                    self.hotkeys.set_suspended(True)
            return
        if key.startswith("LAYER+"):
            layer_key = key.removeprefix("LAYER+")
            if self.layer == "Layer 3":
                self._dispatch_layer_action(
                    self.config.layer3, layer_key, "Layer 3"
                )
            else:
                self.trigger_layer2(layer_key)
        else:
            bindings = (
                self.config.layer2
                if self.layer == "Layer 2"
                else self.config.layer3
                if self.layer == "Layer 3"
                else self.config.matrix
            )
            action = self._resolve_layer_binding(key, bindings)
            self._dispatch_action(action, key, paste=True)

    def _update_matrix_layer_name(self) -> None:
        self.layer_badge.setText(self.layer.upper() if self.hotkeys_enabled else "HOTKEYS OFF")
        self._refresh_matrix_labels()
        self._refresh_layer_status_button()

    def _update_hotkeys_visual_state(self) -> None:
        self._set_native_border(not self.hotkeys_enabled)
        self._refresh_layer_status_button()

    def _refresh_layer_status_button(self) -> None:
        if not hasattr(self, "layer_status_cycle_button"):
            return
        disabled = not self.hotkeys_enabled
        short_name = {
            "Base": "Base",
            "Layer 2": "L1",
            "Layer 3": "L2",
        }.get(self.layer, "Base")
        self.layer_status_cycle_button.setText("Off" if disabled else short_name)
        self.layer_status_cycle_button.setProperty("disabledState", "true" if disabled else "false")
        self.layer_status_cycle_button.style().unpolish(self.layer_status_cycle_button)
        self.layer_status_cycle_button.style().polish(self.layer_status_cycle_button)

    def _set_native_border(self, disabled: bool) -> None:
        try:
            show_indicator = (
                self.show_border_indicator_check.isChecked()
                if hasattr(self, "show_border_indicator_check")
                else self.config.show_border_indicator
            )
            self.window_chrome.set_hotkey_indicator(
                int(self.winId()),
                disabled=disabled,
                visible=show_indicator,
            )
        except (AttributeError, OSError):
            pass

    def _dispatch_layer_action(self, bindings: dict[str, str], key: str, layer: str) -> None:
        action = self._resolve_layer_binding(key, bindings)
        if action in {"previous_iterator", "next_iterator"}:
            self.move_visible_iterator(-1 if action == "previous_iterator" else 1)
            return
        self._dispatch_action(action, key, paste=True)

    def _dispatch_action(self, action: str, key: str, paste: bool) -> None:
        if not action:
            return
        if action in {"previous_iterator", "next_iterator"}:
            self.move_visible_iterator(-1 if action == "previous_iterator" else 1)
            return
        if action in {"previous_work_exp", "next_work_exp"}:
            if self.pages.currentIndex() == 0:
                self.move_work_experience_iterator(
                    -1 if action == "previous_work_exp" else 1
                )
            return
        if action == "layer3_hold":
            if (
                not self.config.hotkey_settings.get("layers", {})
                .get("layer3", {})
                .get("enabled", True)
            ):
                return
            self.layer = "Layer 3"
            self._update_matrix_layer_name()
            return
        if action == "cycle_layers":
            layer_settings = self.config.hotkey_settings.get("layers", {})
            layer2_enabled = layer_settings.get("layer2", {}).get("enabled", True)
            layer3_enabled = layer_settings.get("layer3", {}).get("enabled", True)
            layers = ["Base"]
            if layer2_enabled:
                layers.append("Layer 2")
            if layer3_enabled:
                layers.append("Layer 3")
            current = self.latched_layer if self.latched_layer in layers else "Base"
            self.latched_layer = layers[(layers.index(current) + 1) % len(layers)]
            self.layer = self.latched_layer
            self._update_matrix_layer_name()
            return
        if self.isActiveWindow() and (
            action.startswith("sequence:") or action in self.config.custom_sequences
        ):
            if action.startswith("sequence:"):
                sequence_key = action.partition(":")[2].upper()
                sequence = self.config.sequences.get(sequence_key, [])
                self._show_sequence_iterator(action, sequence, sequence_key)
            else:
                self._show_sequence_iterator(action, self.config.custom_sequences.get(action, []))
            return
        if self.isActiveWindow() and action in {
            "iterate_work_exp",
            "iterate_skills",
            "smart_capture",
        }:
            if action == "iterate_work_exp":
                self.pages.setCurrentIndex(0)
                self._refresh_matrix_labels()
            elif action == "iterate_skills":
                self.pages.setCurrentIndex(2)
            elif action == "smart_capture":
                self._begin_capture_press(key, capture_allowed=False)
                self.statusBar().showMessage(
                    "Capture pane opened · Hold to reset session; capture is paused while JAW has focus"
                )
            self._update_cursor_badge()
            return
        if action == "toggle_answers":
            self.show_mode(3)
        elif action == "move_up_or_relay":
            if self.pages.currentIndex() == 1:
                self.move_answer(-1)
            else:
                self.keyboard.relay_key(0x26)
        elif action == "move_down_or_relay":
            if self.pages.currentIndex() == 1:
                self.move_answer(1)
            else:
                self.keyboard.relay_key(0x28)
        elif action == "iterate_work_exp":
            if self.pages.currentIndex() != 0:
                self._restore_keyboard_after_answers()
                self.pages.setCurrentIndex(0)
                self._refresh_matrix_labels()
            else:
                self.paste_current_work_exp(key)
        elif action == "iterate_skills":
            self.iterate_skill()
        elif action == "cycle_date_format":
            self._cycle_date_format_button()
            self.statusBar().showMessage(f"Date format: {self.date_format.currentText()}", 1800)
        elif action == "cycle_name_format":
            self._cycle_name_format()
        elif action == "toggle_keyboard":
            if self.pages.currentIndex() != 1:
                self.keyboard_panel.setVisible(not self.keyboard_panel.isVisible())
        elif action == "smart_capture":
            self._begin_capture_press(key, capture_allowed=True)
        elif action == "open_dashboard":
            self.open_dashboard()
        elif action == "find_company":
            self.find_company_in_tracker(key)
        elif action == "analyze_job":
            self._analyze_capture_journal()
        elif action in self.config.sequences:
            self.trigger_sequence(action, paste=paste)
        elif action in self.config.custom_sequences:
            self.trigger_custom_sequence(action, paste=paste)
        else:
            item = self.config.items_by_id.get(action)
            if item:
                if self.isActiveWindow():
                    self.statusBar().showMessage(
                        "Copy and paste actions are paused while JAW has focus"
                    )
                    return
                if paste:
                    self.clipboard.write(item.value)
                    category = action if action in self.config.custom_action_types else None
                    self._paste_then_maybe_return(category)
                else:
                    self.clipboard.write(item.value)
            else:
                self.statusBar().showMessage(f"Unknown action '{action}' bound to {key}")

    def eventFilter(self, watched, event) -> bool:
        if self.isActiveWindow() and event.type() in {
            QEvent.Type.KeyPress,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel,
            QEvent.Type.TouchBegin,
        }:
            self._mark_user_interaction()
        if (
            event.type() == QEvent.Type.KeyPress
            and self.isActiveWindow()
            and not self._answer_search_active
            and hasattr(self, "_matrix_buttons")
        ):
            key = event.text().upper()
            if key in self._matrix_buttons:
                self.trigger_matrix(key)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "hotkeys"):
            if self.isMinimized() and hasattr(self, "cursor_badge"):
                self.cursor_badge.update_badge("")
            suspend = bool(
                self.isMinimized() and self.config.hotkey_settings.get("disable_when_minimized")
            )
            self.hotkeys.set_suspended(suspend)
            if self.isMinimized():
                self._schedule_sync_timer()
            else:
                self._wake_sync()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "sync_timer"):
            self._wake_sync()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if hasattr(self, "sync_timer"):
            self._schedule_sync_timer()

    def closeEvent(self, event) -> None:
        if hasattr(self, "sync_timer"):
            self.sync_timer.stop()
        self.cursor_badge_timer.stop()
        self.cursor_badge.close()
        self.hotkeys.stop()
        self.dashboard.stop()
        if self.brief_worker and self.brief_worker.isRunning():
            if not self.brief_worker.wait(1000):
                self.brief_worker.terminate()
                self.brief_worker.wait()
        if self.capture_verification_worker and self.capture_verification_worker.isRunning():
            if not self.capture_verification_worker.wait(800):
                self.capture_verification_worker.terminate()
                self.capture_verification_worker.wait()
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._settings_open:
                self._close_settings()
                return
            if self.pages.currentIndex() != 3:
                self._close_iterator_pane()
                return
        modifier_key = Qt.Key.Key_Shift
        if event.key() == modifier_key:
            layer2 = self.config.hotkey_settings.get("layers", {}).get("layer2", {})
            if layer2.get("enabled", True) and layer2.get("hold", True):
                self._set_layer("Shift")
            return
        key = event.text().upper()
        if key in self._matrix_buttons:
            self.trigger_matrix(key)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        modifier_key = Qt.Key.Key_Shift
        if event.key() == modifier_key:
            self.layer = self.latched_layer
            self._update_matrix_layer_name()
            return
        key = event.text().upper()
        if len(key) == 1 and split_binding(self.config.matrix.get(key, ""))[0] == "layer3_hold":
            self.layer = self.latched_layer
            self._update_matrix_layer_name()
            return
        super().keyReleaseEvent(event)

    def _set_layer(self, layer: str) -> None:
        if layer == "Shift":
            self._update_matrix_layer(True)
        elif layer == "Base":
            self._update_matrix_layer(False)
        else:
            self.layer = layer
            self.layer_badge.setText(f"{layer.upper()} LAYER")


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
