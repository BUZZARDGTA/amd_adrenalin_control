"""Main application window and UI behavior."""

import contextlib
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import NamedTuple

import psutil
from PyQt6.QtCore import (
    QCoreApplication,
    QItemSelectionModel,
    QModelIndex,
    QPoint,
    Qt,
    QTimer,
)
from PyQt6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QKeySequence,
)
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from ._report_helpers import (
    build_stop_all_report_sections,
    capture_process_info,
    to_report_entry,
)
from ._stylesheet import MAIN_STYLESHEET
from .constants import (
    COMPANION_NAMES,
    PROCESS_TOOLTIPS,
    RADEON_SOFTWARE_PATH,
    SERVICE_NAMES,
    STATUS_COLORS,
)
from .dialogs import NotificationDialog, ProcessReportDialog
from .process_ops import get_pid_by_path, launch_detached, terminate_process_tree
from .refresh_snapshot import RefreshBridge, collect_refresh_snapshot
from .uac import is_debug_session, is_running_as_admin, request_self_elevation
from .ui_helpers import (
    COPY_TEXT_ROLE,
    copy_selected_cells,
    copy_selected_rows,
    select_all_cells,
    select_column,
    select_row,
)

PATH_COLUMN_INDEX = 1
PID_COLUMN_INDEX = 2
STATUS_COLUMN_INDEX = 5
NAME_COLUMN_INDEX = 0
EVEN_ROW_REMAINDER = 0
PROCESS_CREATE_TIME_EPSILON = 0.001

_COLOR_ROW_EVEN = QColor('#111827')
_COLOR_ROW_ODD = QColor('#0d1220')
_COLOR_MUTED = QColor('#94a3b8')
_COLOR_EMPTY = QColor('#64748b')
_STATUS_QCOLORS: dict[str, QColor] = {
    status: QColor(color) for status, color in STATUS_COLORS.items()
}

_ALIGNS = (
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignCenter,
)

_EMPTY_VALUES = ('No active processes', '-', '-', '-', '-', 'idle')
_EMPTY_ALIGNS = (
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignCenter,
)


class _SectionPair(NamedTuple):
    """A process-monitor section widget paired with its tree widget."""

    section: QWidget
    tree: QTreeWidget


class _Sections(NamedTuple):
    """All three process-monitor section pairs."""

    managed: _SectionPair
    companion: _SectionPair
    service: _SectionPair


class _StatusWidgets(NamedTuple):
    """Status indicator widgets shown in the monitor header."""

    label: QLabel
    badge: QLabel


@dataclass(slots=True)
class _ManagedTreeUiState:
    """Mutable UI state for the managed process tree."""

    expanded: dict[int, bool] = field(default_factory=dict)
    selected_cells: dict[int, set[int]] = field(default_factory=dict)


@dataclass(slots=True)
class _RefreshState:
    """Mutable state for the background refresh mechanism."""

    bridge: RefreshBridge
    in_flight: bool = False
    pending: bool = False


class MainWindow(QMainWindow):
    """Main application window for controlling and monitoring AMD Adrenalin."""

    def __init__(self) -> None:
        """Initialise the main window, build the UI, and start the refresh timer."""
        super().__init__()
        self.process_path = RADEON_SOFTWARE_PATH
        self.setWindowTitle(f'AMD Adrenalin Control v{__version__}')
        self.setMinimumSize(1012, 705)
        self.resize(1152, 825)

        _label = QLabel('', self)
        _label.hide()
        _badge = QLabel('● NOT RUNNING', self)
        _badge.setObjectName('badge_stopped')
        self._status = _StatusWidgets(label=_label, badge=_badge)

        managed_pair = self._create_managed_section(
            self,
            'Radeon Software Managed',
            'Main RadeonSoftware.exe process and any child processes spawned from it.',
        )
        companion_pair = self._create_process_section(
            self,
            'AMD Companion Processes',
            'Supporting user-space AMD helper executables'
            ' that assist telemetry and features.',
        )
        service_pair = self._create_process_section(
            self,
            'AMD System Services',
            'Background service executables that provide'
            ' driver and system-level AMD functionality.',
        )
        self._sections = _Sections(
            managed=_SectionPair(*managed_pair),
            companion=_SectionPair(*companion_pair),
            service=_SectionPair(*service_pair),
        )
        self._managed_tree_ui_state = _ManagedTreeUiState()

        bridge = RefreshBridge(self)
        bridge.snapshot_ready.connect(  # pyright: ignore[reportUnknownMemberType]
            self._apply_refresh_snapshot,
        )
        self._refresh = _RefreshState(bridge)

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(  # pyright: ignore[reportUnknownMemberType]
            self._refresh_process_info,
        )
        self._timer.start()
        self._refresh_process_info()

    def closeEvent(  # noqa: N802  # pylint: disable=invalid-name
        self,
        a0: QCloseEvent | None,
    ) -> None:
        """Handle window close and let daemon refresh worker exit naturally."""
        super().closeEvent(a0)

    # ------------------------------------------------------------------
    # Properties that delegate to grouped containers so the rest of the
    # code can keep using the original attribute names unchanged.
    # ------------------------------------------------------------------

    @property
    def status_label(self) -> QLabel:
        """Hidden label used for status text storage."""
        return self._status.label

    @property
    def status_badge(self) -> QLabel:
        """Visible running/stopped badge in the monitor header."""
        return self._status.badge

    @property
    def managed_section(self) -> QWidget:
        """Section widget for the managed process group."""
        return self._sections.managed.section

    @property
    def managed_tree(self) -> QTreeWidget:
        """Tree widget for the managed process group."""
        return self._sections.managed.tree

    @property
    def companion_section(self) -> QWidget:
        """Section widget for companion processes."""
        return self._sections.companion.section

    @property
    def companion_tree(self) -> QTreeWidget:
        """Tree widget for companion processes."""
        return self._sections.companion.tree

    @property
    def service_section(self) -> QWidget:
        """Section widget for AMD system services."""
        return self._sections.service.section

    @property
    def service_tree(self) -> QTreeWidget:
        """Tree widget for AMD system services."""
        return self._sections.service.tree

    @property
    def _process_tables(self) -> list[QTreeWidget]:
        """All three process tree widgets for cross-table operations."""
        return [
            self._sections.managed.tree,
            self._sections.companion.tree,
            self._sections.service.tree,
        ]

    @property
    def _process_path_str(self) -> str:
        """Absolute path string for the target executable."""
        return str(self.process_path.absolute())

    def _build_ui(self) -> None:
        """Construct and lay out all widgets in the main window."""
        central = QWidget(self)
        central.setObjectName('central_widget')
        layout = QGridLayout(central)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)

        self._build_top_controls(layout)
        self._build_monitor_header(layout)
        self._build_monitor_sections(layout)

        self.setCentralWidget(central)
        self._apply_stylesheet()
        self._show_process_sections()

    def _create_action_button(
        self,
        text: str,
        tooltip: str,
        callback: Callable[[], None],
        *,
        obj_name: str | None = None,
    ) -> QPushButton:
        """Create a styled action button wired to a callback."""
        btn = QPushButton(text, self)
        btn.setMinimumHeight(40)
        btn.setToolTip(tooltip)
        if obj_name is not None:
            btn.setObjectName(obj_name)
        btn.clicked.connect(  # pyright: ignore[reportUnknownMemberType]
            callback,
        )
        return btn

    def _build_top_controls(self, layout: QGridLayout) -> None:
        """Build status labels and top action buttons."""
        restart_btn = self._create_action_button(
            'Restart Adrenalin',
            'Stops Radeon Software if running,'
            ' then starts a fresh instance.',
            self.restart_software,
        )
        start_btn = self._create_action_button(
            'Start Adrenalin',
            'Starts Radeon Software if it is not already running.',
            self.start_only,
            obj_name='start_btn',
        )
        stop_btn = self._create_action_button(
            'Stop Adrenalin',
            'Stops the main Radeon Software process'
            ' and its child processes.',
            self.stop_only,
            obj_name='stop_btn',
        )
        stop_all_btn = self._create_action_button(
            'Stop all AMD processes',
            'Stops Radeon Software and all monitored'
            ' AMD helper/service processes,'
            ' including their child processes.',
            self.stop_all,
            obj_name='stop_all_btn',
        )
        stop_all_btn.setMinimumHeight(38)

        layout.addWidget(restart_btn, 0, 0)
        layout.addWidget(start_btn, 0, 1)
        layout.addWidget(stop_btn, 0, 2)
        layout.addWidget(stop_all_btn, 1, 0, 1, 3)

    def _build_monitor_header(self, layout: QGridLayout) -> None:
        """Build the live monitor heading and status badge row."""
        monitor_header = QWidget(self)
        monitor_header.setObjectName('monitor_header')
        header_layout = QHBoxLayout(monitor_header)
        header_layout.setContentsMargins(0, 4, 0, 0)
        header_layout.setSpacing(10)

        monitor_label = QLabel('Live Process Monitor', self)
        monitor_label.setObjectName('monitor_label')
        header_layout.addWidget(monitor_label)
        header_layout.addWidget(self.status_badge)
        header_layout.addStretch()
        layout.addWidget(monitor_header, 2, 0, 1, 3)

    def _build_monitor_sections(self, layout: QGridLayout) -> None:
        """Build the process monitor scroll area and section tables."""
        monitor_scroll = QScrollArea(self)
        monitor_scroll.setObjectName('monitor_scroll')
        monitor_scroll.setWidgetResizable(True)
        monitor_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        if viewport := monitor_scroll.viewport():
            viewport.setObjectName('monitor_viewport')

        monitor_content = QWidget(monitor_scroll)
        monitor_content.setObjectName('monitor_content')
        monitor_layout = QVBoxLayout(monitor_content)
        monitor_layout.setContentsMargins(0, 0, 0, 0)
        monitor_layout.setSpacing(14)

        monitor_layout.addWidget(self.managed_section)
        monitor_layout.addWidget(self.companion_section)
        monitor_layout.addWidget(self.service_section)
        monitor_layout.addStretch()

        monitor_scroll.setWidget(monitor_content)
        layout.addWidget(monitor_scroll, 3, 0, 1, 3)

    def _apply_stylesheet(self) -> None:
        """Apply the main window stylesheet."""
        self.setStyleSheet(MAIN_STYLESHEET)

    def _show_process_sections(self) -> None:
        """Ensure all process sections are visible after UI construction."""
        self.managed_section.show()
        self.companion_section.show()
        self.service_section.show()

    def _configure_common_view_interactions(
        self,
        view: QTreeWidget,
    ) -> None:
        """Apply shared selection, copy, and tracking settings to a view."""
        view.setMouseTracking(True)
        if viewport := view.viewport():
            viewport.setMouseTracking(True)
        view.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        view.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        view.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectItems)
        view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        copy_action = QAction(view)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        copy_action.triggered.connect(  # pyright: ignore[reportUnknownMemberType]
            lambda _, current_view=view: copy_selected_cells(current_view),
        )
        view.addAction(copy_action)
        view.itemSelectionChanged.connect(  # pyright: ignore[reportUnknownMemberType]
            lambda current_view=view:
                self._enforce_single_table_selection(current_view),
        )

    def _configure_process_tree_interactions(self, tree: QTreeWidget) -> None:
        """Enable selection, copy, and context menu on a process tree."""
        self._configure_common_view_interactions(tree)
        _ctx_signal = tree.customContextMenuRequested
        _ctx_signal.connect(  # pyright: ignore[reportUnknownMemberType]
            lambda pos, current_tree=tree:
                self._show_tree_context_menu(
                    current_tree, pos,
                ),
        )
        tree.expanded.connect(  # pyright: ignore[reportUnknownMemberType]
            lambda _idx, t=tree: self._resize_tree_widget(t),
        )
        tree.collapsed.connect(  # pyright: ignore[reportUnknownMemberType]
            lambda _idx, t=tree: self._resize_tree_widget(t),
        )

    def _enforce_single_table_selection(
        self,
        active_table: QTreeWidget,
    ) -> None:
        """Clear selections in other process tables when active_table has selection."""
        if not active_table.selectedIndexes():
            return

        for table in self._process_tables:
            if table is active_table:
                continue

            if table.selectedIndexes():
                table.clearSelection()

    def _create_process_section(
        self,
        parent: QWidget,
        title: str,
        description: str,
    ) -> tuple[QWidget, QTreeWidget]:
        """Create a labeled process section with a dedicated tree widget."""
        section = QWidget(parent)
        section.setObjectName('process_section')
        section.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(12, 12, 12, 12)
        section_layout.setSpacing(8)

        label = QLabel(title, section)
        label.setObjectName('section_header')
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        count_label = QLabel('(0)', section)
        count_label.setObjectName('section_count')
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        description_label = QLabel(description, section)
        description_label.setObjectName('section_description')
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        tree = QTreeWidget(section)
        tree.setObjectName('process_tree')
        tree.setColumnCount(6)
        tree.setHeaderLabels(  # pyright: ignore[reportUnknownMemberType]
            ['Name', 'Path', 'PID', 'CPU %', 'Memory', 'Status'],
        )
        if header := tree.header():
            self._configure_section_header_resize(header)
        tree.setRootIsDecorated(True)
        tree.setIndentation(20)
        tree.setUniformRowHeights(True)
        tree.setAnimated(False)
        self._configure_process_tree_interactions(tree)
        tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        header_row = QWidget(section)
        header_row_layout = QHBoxLayout(header_row)
        header_row_layout.setContentsMargins(0, 0, 0, 0)
        header_row_layout.setSpacing(6)
        header_row_layout.addStretch()
        header_row_layout.addWidget(label)
        header_row_layout.addWidget(count_label)
        header_row_layout.addStretch()

        section_layout.addWidget(header_row)
        section_layout.addWidget(description_label)
        section_layout.addWidget(tree)
        return section, tree

    def _create_managed_section(
        self,
        parent: QWidget,
        title: str,
        description: str,
    ) -> tuple[QWidget, QTreeWidget]:
        """Create the managed process section with a tree widget for hierarchy."""
        section = QWidget(parent)
        section.setObjectName('process_section')
        section.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(12, 12, 12, 12)
        section_layout.setSpacing(8)

        label = QLabel(title, section)
        label.setObjectName('section_header')
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        count_label = QLabel('(0)', section)
        count_label.setObjectName('section_count')
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        description_label = QLabel(description, section)
        description_label.setObjectName('section_description')
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        tree = QTreeWidget(section)
        tree.setObjectName('process_tree')
        tree.setColumnCount(6)
        tree.setHeaderLabels(  # pyright: ignore[reportUnknownMemberType]
            ['Name', 'Path', 'PID', 'CPU %', 'Memory', 'Status'],
        )
        if header := tree.header():
            self._configure_section_header_resize(header)
        tree.setRootIsDecorated(True)
        tree.setIndentation(20)
        tree.setUniformRowHeights(True)
        tree.setAnimated(False)
        self._configure_managed_tree_interactions(tree)
        tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        header_row = QWidget(section)
        header_row_layout = QHBoxLayout(header_row)
        header_row_layout.setContentsMargins(0, 0, 0, 0)
        header_row_layout.setSpacing(6)
        header_row_layout.addStretch()
        header_row_layout.addWidget(label)
        header_row_layout.addWidget(count_label)
        header_row_layout.addStretch()

        section_layout.addWidget(header_row)
        section_layout.addWidget(description_label)
        section_layout.addWidget(tree)
        return section, tree

    def _configure_managed_tree_interactions(self, tree: QTreeWidget) -> None:
        """Enable selection, copy, expand/collapse and context menu on the tree."""
        self._configure_common_view_interactions(tree)
        _ctx_signal = tree.customContextMenuRequested
        _ctx_signal.connect(  # pyright: ignore[reportUnknownMemberType]
            self._show_managed_tree_context_menu,
        )
        tree.expanded.connect(  # pyright: ignore[reportUnknownMemberType]
            lambda _idx: self._resize_managed_tree(),
        )
        tree.collapsed.connect(  # pyright: ignore[reportUnknownMemberType]
            lambda _idx: self._resize_managed_tree(),
        )

    @staticmethod
    def _count_visible_descendants(item: QTreeWidgetItem) -> int:
        """Recursively count visible descendants of an expanded tree item."""
        count = 0
        if item.isExpanded():
            for i in range(item.childCount()):
                child = item.child(i)
                if child is not None and not child.isHidden():
                    count += 1
                    count += MainWindow._count_visible_descendants(child)
        return count

    def _resize_tree_widget(self, tree: QTreeWidget) -> None:
        """Fit a tree widget to its visible items so sections stay compact."""
        header = tree.header()
        header_height = header.height() if header is not None else 0
        row_height = 28
        frame_height = tree.frameWidth() * 2

        visible_count = 0
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item is not None and not item.isHidden():
                visible_count += 1
                visible_count += self._count_visible_descendants(item)

        tree.setFixedHeight(
            header_height + (visible_count * row_height) + frame_height,
        )

    def _resize_managed_tree(self) -> None:
        """Fit the managed tree to its visible items so sections stay compact."""
        self._resize_tree_widget(self.managed_tree)

    def _populate_process_tree(
        self,
        tree: QTreeWidget,
        rows: list[dict[str, object]],
        *,
        muted: bool = False,
    ) -> None:
        """Populate a process tree widget from plain row snapshots."""
        tree.setUpdatesEnabled(False)
        tree.clear()

        for row_idx, row in enumerate(rows):
            row_bg = (
                _COLOR_ROW_EVEN
                if row_idx % 2 == EVEN_ROW_REMAINDER
                else _COLOR_ROW_ODD
            )

            tree_item = QTreeWidgetItem(tree)
            self._configure_managed_tree_item_columns(
                tree_item, row_bg, row, muted=muted,
            )

        self._resize_tree_widget(tree)
        tree.setUpdatesEnabled(True)

    @staticmethod
    def _update_section_count(section: QWidget, count: int) -> None:
        """Update the process count label inside a section widget."""
        count_label = section.findChild(QLabel, 'section_count')
        if count_label is not None:
            count_label.setText(f'({count})')

    def _update_process_section(
        self,
        section: QWidget,
        tree: QTreeWidget,
        processes: list[dict[str, object]],
        *,
        muted: bool = False,
    ) -> None:
        """Keep section visible and show either process rows or an empty-state row."""
        section.setVisible(True)
        self._update_section_count(section, len(processes))
        if not processes:
            tree.clear()
            empty_item = QTreeWidgetItem(tree)
            for col, (val, align) in enumerate(
                zip(_EMPTY_VALUES, _EMPTY_ALIGNS, strict=True),
            ):
                empty_item.setText(col, val)
                empty_item.setTextAlignment(col, align)
                empty_item.setBackground(col, _COLOR_ROW_ODD)
                empty_item.setForeground(col, _COLOR_EMPTY)
            self._resize_tree_widget(tree)
            return
        self._populate_process_tree(tree, processes, muted=muted)

    def _save_item_expansion_recursive(self, item: QTreeWidgetItem) -> None:
        """Recursively persist expansion state for an item and its children."""
        pid = item.data(NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole)
        if isinstance(pid, int):
            self._managed_tree_ui_state.expanded[pid] = item.isExpanded()
        for i in range(item.childCount()):
            child = item.child(i)
            if child is not None:
                self._save_item_expansion_recursive(child)

    def _save_managed_tree_expansion(self) -> None:
        """Persist which tree items are currently expanded."""
        tree = self.managed_tree
        for i in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(i)
            if top_item is not None:
                self._save_item_expansion_recursive(top_item)

    def _restore_item_expansion_recursive(self, item: QTreeWidgetItem) -> None:
        """Recursively re-apply saved expansion state for an item and children."""
        pid = item.data(NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole)
        expanded = (
            self._managed_tree_ui_state.expanded.get(pid, True)
            if isinstance(pid, int)
            else True
        )
        item.setExpanded(expanded)
        for i in range(item.childCount()):
            child = item.child(i)
            if child is not None:
                self._restore_item_expansion_recursive(child)

    def _restore_managed_tree_expansion(self) -> None:
        """Re-apply saved expansion state to all tree items."""
        tree = self.managed_tree
        for i in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(i)
            if top_item is not None:
                self._restore_item_expansion_recursive(top_item)

    def _save_managed_tree_selection(self) -> None:
        """Persist which tree cells are selected, keyed by PID -> columns."""
        tree = self.managed_tree
        self._managed_tree_ui_state.selected_cells = {}
        sel_model = tree.selectionModel()
        if sel_model is None:
            return
        for index in sel_model.selectedIndexes():
            item = tree.itemFromIndex(index)
            if item is None:
                continue
            pid = item.data(NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole)
            if isinstance(pid, int):
                self._managed_tree_ui_state.selected_cells.setdefault(
                    pid, set(),
                ).add(index.column())

    def _restore_selection_recursive(
        self,
        tree: QTreeWidget,
        sel_model: QItemSelectionModel,
        item: QTreeWidgetItem,
    ) -> None:
        """Recursively restore cell selection for an item and its children."""
        self._restore_item_cell_selection(tree, sel_model, item)
        for i in range(item.childCount()):
            child = item.child(i)
            if child is not None:
                self._restore_selection_recursive(tree, sel_model, child)

    def _restore_managed_tree_selection(self) -> None:
        """Re-apply saved per-cell selection to tree items matching saved PIDs."""
        if not self._managed_tree_ui_state.selected_cells:
            return
        tree = self.managed_tree
        sel_model = tree.selectionModel()
        if sel_model is None:
            return
        for i in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(i)
            if top_item is not None:
                self._restore_selection_recursive(tree, sel_model, top_item)

    def _restore_item_cell_selection(
        self,
        tree: QTreeWidget,
        sel_model: QItemSelectionModel,
        item: QTreeWidgetItem,
    ) -> None:
        """Select saved columns for a single tree item if its PID was saved."""
        pid = item.data(NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole)
        if not isinstance(pid, int):
            return
        cols = self._managed_tree_ui_state.selected_cells.get(pid)
        if cols is None:
            return
        for col in cols:
            idx = tree.indexFromItem(item, col)
            sel_model.select(idx, QItemSelectionModel.SelectionFlag.Select)

    def _configure_managed_tree_item_columns(
        self,
        tree_item: QTreeWidgetItem,
        row_bg: QColor,
        row: dict[str, object],
        *,
        muted: bool = False,
    ) -> None:
        """Set text, alignment, colors, tooltips, and data roles on a tree item."""
        name = str(row.get('name', ''))
        path_text = str(row.get('path', ''))
        status = str(row.get('status', ''))
        indent = row.get('indent', 0)
        if not isinstance(indent, int):
            indent = 0
        values = (
            name, path_text,
            str(row.get('pid_text', '')),
            str(row.get('cpu_text', '')),
            str(row.get('mem_text', '')),
            status,
        )

        for col, (val, align) in enumerate(zip(values, _ALIGNS, strict=True)):
            tree_item.setText(col, val)
            tree_item.setTextAlignment(col, align)
            tree_item.setBackground(col, row_bg)
            if col == NAME_COLUMN_INDEX:
                tree_item.setData(col, COPY_TEXT_ROLE, name)
                if tooltip := PROCESS_TOOLTIPS.get(name.lower()):
                    tree_item.setToolTip(col, tooltip)
                if isinstance(row.get('pid_value'), int):
                    tree_item.setData(
                        col, Qt.ItemDataRole.UserRole, row['pid_value'],
                    )
            elif col == PATH_COLUMN_INDEX:
                tree_item.setToolTip(col, path_text)
            if col == STATUS_COLUMN_INDEX:
                tree_item.setForeground(
                    col,
                    _STATUS_QCOLORS.get(status, _COLOR_MUTED),
                )
            elif muted or indent > 0:
                tree_item.setForeground(col, _COLOR_MUTED)

    def _populate_managed_tree(
        self,
        rows: list[dict[str, object]],
    ) -> None:
        """Populate the managed tree widget from plain row snapshots."""
        tree = self.managed_tree
        self._save_managed_tree_expansion()
        self._save_managed_tree_selection()

        tree.setUpdatesEnabled(False)
        tree.clear()

        # Stack tracks the tree item at each depth so children
        # attach under the correct parent at any nesting level.
        parent_stack: list[QTreeWidgetItem] = []

        for row_idx, row in enumerate(rows):
            indent_raw = row['indent']
            indent = indent_raw if isinstance(indent_raw, int) else 0

            row_bg = (
                _COLOR_ROW_EVEN
                if row_idx % 2 == EVEN_ROW_REMAINDER
                else _COLOR_ROW_ODD
            )

            # Trim the stack back to the current indent depth.
            del parent_stack[indent:]

            if parent_stack:
                tree_item = QTreeWidgetItem(parent_stack[-1])
            else:
                tree_item = QTreeWidgetItem(tree)

            parent_stack.append(tree_item)

            self._configure_managed_tree_item_columns(
                tree_item, row_bg, row,
            )

        self._restore_managed_tree_expansion()
        self._restore_managed_tree_selection()
        self._resize_managed_tree()
        tree.setUpdatesEnabled(True)

    def _update_managed_section(
        self,
        processes: list[dict[str, object]],
    ) -> None:
        """Update the managed tree section with process data or an empty state."""
        self.managed_section.setVisible(True)
        self._update_section_count(self.managed_section, len(processes))
        if not processes:
            tree = self.managed_tree
            tree.clear()
            empty_item = QTreeWidgetItem(tree)
            for col, (val, align) in enumerate(
                zip(_EMPTY_VALUES, _EMPTY_ALIGNS, strict=True),
            ):
                empty_item.setText(col, val)
                empty_item.setTextAlignment(col, align)
                empty_item.setBackground(col, _COLOR_ROW_ODD)
                empty_item.setForeground(col, _COLOR_EMPTY)
            self._resize_managed_tree()
            return
        self._populate_managed_tree(processes)

    def _is_same_process_still_running(
        self,
        pid: int,
        target_create_time: float | None,
    ) -> bool:
        """Return True if the original target process identity is still alive."""
        if target_create_time is None:
            with contextlib.suppress(psutil.Error):
                return psutil.pid_exists(pid)
            return False

        with contextlib.suppress(psutil.Error):
            probe = psutil.Process(pid)
            return (
                abs(probe.create_time() - target_create_time)
                < PROCESS_CREATE_TIME_EPSILON
            )
        return False

    def _format_process_label(self, pid: int) -> str:
        """Build a display label as '<name> (PID n)' with PID fallback."""
        process_label = f'PID {pid}'
        with contextlib.suppress(psutil.Error):
            process_label = f'{psutil.Process(pid).name()} (PID {pid})'
        return process_label

    def _capture_target_create_times(self, pids: set[int]) -> dict[int, float | None]:
        """Capture best-effort create times for target process identity checks."""
        create_times: dict[int, float | None] = dict.fromkeys(pids)
        for pid in pids:
            with contextlib.suppress(psutil.Error):
                create_times[pid] = psutil.Process(pid).create_time()
        return create_times

    def _verified_denied_pids(
        self,
        denied_pids: set[int],
        target_pids: set[int],
    ) -> set[int]:
        """Capture create times and keep denied PIDs still running."""
        create_times = self._capture_target_create_times(target_pids)
        return {
            pid
            for pid in denied_pids
            if self._is_same_process_still_running(pid, create_times.get(pid))
        }

    def _classify_attempted_pids(
        self,
        attempted_pids: list[int],
        stopped_pids: set[int],
        denied_pids: set[int],
    ) -> tuple[list[int], list[int], list[int]]:
        """Split attempted pids into closed, denied, and already-gone groups."""
        stopped_known = [pid for pid in attempted_pids if pid in stopped_pids]
        denied_known = [pid for pid in attempted_pids if pid in denied_pids]
        gone_known = [
            pid for pid in attempted_pids
            if pid not in stopped_pids
            and pid not in denied_pids
        ]
        return stopped_known, denied_known, gone_known

    def _terminate_single_process(self, pid: int) -> None:
        """Terminate a single process by PID and refresh the display."""
        failure_reason: str | None = None
        permission_denied = False
        process_label = self._format_process_label(pid)
        target_create_time: float | None = None
        try:
            proc = psutil.Process(pid)
            with contextlib.suppress(psutil.Error):
                target_create_time = proc.create_time()
            proc.terminate()
            proc.wait(timeout=3)
        except psutil.AccessDenied:
            failure_reason = (
                'Permission denied while terminating'
                ' the process. Try running as administrator.'
            )
            permission_denied = True
        except psutil.TimeoutExpired:
            try:
                proc = psutil.Process(pid)
                proc.kill()
                proc.wait(timeout=3)
            except psutil.AccessDenied:
                failure_reason = (
                    'Permission denied while force-stopping'
                    ' the process. Try running as administrator.'
                )
                permission_denied = True
            except psutil.TimeoutExpired:
                failure_reason = (
                    'The process did not exit after'
                    ' terminate and force-stop attempts.'
                )
            except psutil.NoSuchProcess:
                pass
        except psutil.NoSuchProcess:
            pass

        self._refresh_process_info()

        # On Windows, transient AccessDenied/Timeout paths
        # can still end with the target gone.
        # Only report failure if the same original process is still running.
        if (
            failure_reason is not None
            and not self._is_same_process_still_running(
                pid, target_create_time,
            )
        ):
            failure_reason = None
            permission_denied = False
            self.status_label.setText(f'Terminated {process_label}.')

        if failure_reason is not None:
            self.status_label.setText(
                f'Failed to terminate {process_label}:'
                f' {failure_reason}',
            )
            self._popup(
                'Terminate failed',
                f'Could not terminate {process_label}.\n\nReason: {failure_reason}',
                QMessageBox.Icon.Warning,
            )
            if permission_denied:
                self._offer_uac_elevation(
                    reason=(
                        'Windows denied permission while trying'
                        ' to terminate the selected process.'
                    ),
                )

    def _stop_single_process(self, pid: int) -> None:
        """Terminate a single process tree by PID and refresh the display."""
        _, denied_pids = terminate_process_tree(pid)
        denied_pids = self._verified_denied_pids(denied_pids, {pid})
        self._refresh_process_info()
        if denied_pids:
            self._offer_uac_elevation(
                reason=(
                    'Windows denied permission while trying'
                    ' to terminate the selected process tree.'
                ),
            )

    @staticmethod
    def _configure_section_header_resize(header: QHeaderView) -> None:
        """Set standard column resize modes for process section headers."""
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (2, 3, 4, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

    def _confirm_terminate(self, *, pid: int, tree: bool) -> bool:
        """Ask user to confirm terminate action."""
        action_text = (
            'terminate this process tree'
            if tree
            else 'terminate this process'
        )
        detail = (
            'This will stop the selected process and all child processes.'
            if tree
            else 'This will stop only the selected process.'
        )
        process_label = self._format_process_label(pid)
        answer = QMessageBox.question(
            self,
            'Confirm terminate',
            (
                f'Are you sure you want to {action_text}?'
                f'\n\nProcess: {process_label}'
                f'\n\n{detail}'
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    @staticmethod
    def _handle_selection_action(
        chosen_action: QAction,
        actions: dict[str, QAction | None],
        view: QTreeWidget,
        *,
        row_index: QModelIndex | None = None,
        col_idx: int = 0,
    ) -> bool:
        """Handle select/copy actions common to both table and tree menus."""
        if chosen_action == actions.get('copy_cells'):
            copy_selected_cells(view)
        elif chosen_action == actions.get('copy_rows'):
            copy_selected_rows(view)
        elif chosen_action == actions.get('select_row') and row_index is not None:
            select_row(view, row_index)
        elif chosen_action == actions.get('select_column'):
            select_column(view, col_idx)
        elif chosen_action == actions.get('select_all'):
            select_all_cells(view)
        else:
            return False
        return True

    def _handle_process_menu_action(
        self,
        *,
        chosen_action: QAction | None,
        actions: dict[str, QAction | None],
        pid: int | None,
        row_path: str | None = None,
    ) -> None:
        """Execute the selected process-row context menu action."""
        if chosen_action is None:
            return

        open_location_action = actions.get('open_location')
        terminate_process_action = actions['terminate_process']
        terminate_tree_action = actions['terminate_tree']

        if (
            open_location_action is not None
            and chosen_action == open_location_action
            and row_path is not None
        ):
            subprocess.run(  # noqa: S603
                ['explorer', '/select,', row_path],  # noqa: S607
                check=False,
            )
            return

        if (
            terminate_process_action is not None
            and chosen_action == terminate_process_action
            and pid is not None
            and self._confirm_terminate(pid=pid, tree=False)
        ):
            self._terminate_single_process(pid)
            return

        if (
            terminate_tree_action is not None
            and chosen_action == terminate_tree_action
            and pid is not None
            and self._confirm_terminate(pid=pid, tree=True)
        ):
            self._stop_single_process(pid)

    def _build_process_context_menu(
        self,
        parent: QWidget,
        *,
        row_path: str | None,
        pid: int | None,
        has_children: bool,
    ) -> tuple[QMenu, dict[str, QAction | None]]:
        """Build the standard process context menu and return (menu, actions)."""
        menu = QMenu(parent)
        actions: dict[str, QAction | None] = {
            'copy_cells': menu.addAction('Copy selected cells'),
            'copy_rows': menu.addAction('Copy selected rows'),
        }
        menu.addSeparator()
        actions['select_row'] = menu.addAction('Select row')
        actions['select_column'] = menu.addAction('Select column')
        actions['select_all'] = menu.addAction('Select all')
        actions['open_location'] = None
        actions['terminate_process'] = None
        actions['terminate_tree'] = None
        if row_path is not None:
            menu.addSeparator()
            actions['open_location'] = menu.addAction('Open file location')
        if pid is not None:
            menu.addSeparator()
            actions['terminate_process'] = menu.addAction('Terminate process')
            if has_children:
                actions['terminate_tree'] = menu.addAction(
                    'Terminate process tree',
                )
        return menu, actions

    class _MenuContext(NamedTuple):
        """Bundled context for a process context menu invocation."""

        pid: int | None
        row_path: str | None
        has_children: bool
        row_index: QModelIndex | None
        col_idx: int

    def _dispatch_context_menu(
        self,
        view: QTreeWidget,
        position: QPoint,
        ctx: _MenuContext,
    ) -> None:
        """Build, show, and dispatch a process context menu."""
        menu, actions = self._build_process_context_menu(
            view, row_path=ctx.row_path, pid=ctx.pid,
            has_children=ctx.has_children,
        )
        viewport = view.viewport()
        if viewport is None:
            return

        chosen_action = menu.exec(viewport.mapToGlobal(position))
        if chosen_action is None:
            return
        if self._handle_selection_action(
            chosen_action, actions, view,
            row_index=ctx.row_index, col_idx=ctx.col_idx,
        ):
            return
        self._handle_process_menu_action(
            chosen_action=chosen_action,
            actions=actions,
            pid=ctx.pid,
            row_path=ctx.row_path,
        )

    def _show_tree_context_menu(self, tree: QTreeWidget, position: QPoint) -> None:
        """Show row actions for a process item in a tree widget."""
        tree_item = tree.itemAt(position)
        if tree_item is None:
            return

        header = tree.header()
        col_idx = max(header.logicalIndexAt(position.x()) if header else 0, 0)

        selection_model = tree.selectionModel()
        if selection_model is not None and not selection_model.hasSelection():
            tree.setCurrentItem(tree_item, col_idx)

        pid: int | None = None
        pid_data = tree_item.data(NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole)
        if isinstance(pid_data, int):
            pid = pid_data

        path_text = tree_item.text(PATH_COLUMN_INDEX)
        row_path = (
            path_text
            if path_text not in ('-', '', 'Executable path unavailable')
            else None
        )
        current_item = self._find_tree_item_by_pid(tree, pid)
        self._dispatch_context_menu(
            tree, position,
            self._MenuContext(
                pid=pid,
                row_path=row_path,
                has_children=(
                    self._tree_item_has_children(tree_item, pid)
                    if pid is not None else False
                ),
                row_index=(
                    tree.indexFromItem(current_item, 0)
                    if current_item is not None else None
                ),
                col_idx=col_idx,
            ),
        )

    @staticmethod
    def _tree_item_has_children(tree_item: QTreeWidgetItem, pid: int) -> bool:
        """Check whether a tree item or its underlying process has children."""
        if tree_item.childCount() > 0:
            return True
        with contextlib.suppress(psutil.Error):
            return len(psutil.Process(pid).children(recursive=False)) > 0
        return False

    @staticmethod
    def _find_tree_item_by_pid(
        tree: QTreeWidget,
        pid: int | None,
    ) -> QTreeWidgetItem | None:
        """Find a tree item matching *pid*, or None if not found."""
        if pid is None:
            return None
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            if top is None:
                continue
            if top.data(NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole) == pid:
                return top
            for j in range(top.childCount()):
                child = top.child(j)
                if (
                    child is not None
                    and child.data(
                        NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole,
                    ) == pid
                ):
                    return child
        return None

    def _show_managed_tree_context_menu(self, position: QPoint) -> None:
        """Show row actions for a process item in the managed tree widget."""
        self._show_tree_context_menu(self.managed_tree, position)

    def _popup(self, title: str, text: str, icon: QMessageBox.Icon) -> None:
        """Show a styled in-app modal dialog for status and report messages."""
        dialog = NotificationDialog(self, title, text, icon)
        dialog.exec()

    def _offer_uac_elevation(self, *, reason: str) -> None:
        """Offer to relaunch this app with elevation when an action is denied."""
        if is_running_as_admin():
            self._popup(
                'Permissions required',
                f'{reason}\n\nThe app is already running as administrator.',
                QMessageBox.Icon.Warning,
            )
            return

        answer = QMessageBox.question(
            self,
            'Administrator privileges required',
            f'{reason}\n\nWould you like to relaunch this app as administrator now?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        if request_self_elevation():
            if is_debug_session():
                self.status_label.setText(
                    'Elevation requested in debug mode. Keep this window open; close it'
                    ' manually after elevated app is stable.',
                )
                return

            self.status_label.setText(
                'Elevation requested. Closing this window'
                ' in favor of elevated instance.',
            )
            self.close()
            return

        self._popup(
            'Elevation failed',
            'Could not request administrator privileges from Windows.',
            QMessageBox.Icon.Warning,
        )

    def _report_and_notify(
        self,
        status_text: str,
        dialog_title: str,
        icon: QMessageBox.Icon,
        sections: list[tuple[str, list[dict[str, str]]]],
    ) -> None:
        """Update the status bar and show a process-report dialog."""
        self.status_label.setText(status_text)
        self._show_process_report(dialog_title, icon, sections)

    def _show_process_report(
        self,
        title: str,
        icon: QMessageBox.Icon,
        sections: list[tuple[str, list[dict[str, str]]]],
    ) -> None:
        """Show a structured process report dialog."""
        dialog = ProcessReportDialog(self, title, icon, sections)
        dialog.exec()

    def _wait_for_managed_process_start(
        self,
        *,
        timeout_seconds: float = 3.0,
        poll_interval_seconds: float = 0.1,
    ) -> int | None:
        """Poll for the managed Radeon Software process to appear after launch."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            pid = get_pid_by_path(self.process_path)
            if pid is not None:
                return pid
            QCoreApplication.processEvents()
            time.sleep(poll_interval_seconds)
        return get_pid_by_path(self.process_path)

    def _collect_process_tree_targets_for_pid(
        self,
        pid: int,
        category: str,
        target_categories: dict[int, str],
        process_info: dict[int, dict[str, str]],
    ) -> None:
        """Capture a process tree rooted at pid into shared report dictionaries."""
        target_categories[pid] = category
        capture_process_info(process_info, pid, category)

        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                target_categories[child.pid] = category
                capture_process_info(process_info, child.pid, category)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def _collect_managed_report_data(
        self,
        pid: int | None = None,
    ) -> tuple[dict[int, str], dict[int, dict[str, str]]]:
        """Collect managed Radeon Software process-tree metadata for reporting."""
        target_categories: dict[int, str] = {}
        process_info: dict[int, dict[str, str]] = {}

        managed_pid = get_pid_by_path(self.process_path) if pid is None else pid
        if managed_pid is not None:
            self._collect_process_tree_targets_for_pid(
                managed_pid,
                'Managed',
                target_categories,
                process_info,
            )

        return target_categories, process_info

    def _build_report_sections_from_pid_groups(
        self,
        process_info: dict[int, dict[str, str]],
        section_pid_groups: list[tuple[str, list[int]]],
    ) -> list[tuple[str, list[dict[str, str]]]]:
        """Build structured report sections from ordered PID groups."""
        return [
            (section_title, [to_report_entry(process_info, pid) for pid in pids])
            for section_title, pids in section_pid_groups
        ]

    def _ensure_process_path_exists(self) -> bool:
        """Check process path exists, showing error popup if missing."""
        if self.process_path.exists():
            return True
        self.status_label.setText('RadeonSoftware.exe path was not found.')
        self._popup(
            'Path not found',
            f'Could not find executable at:\n{self.process_path}',
            QMessageBox.Icon.Critical,
        )
        return False

    def restart_software(self) -> None:
        """Stop any running instance of Radeon Software, then launch a fresh one."""
        if not self._ensure_process_path_exists():
            return

        before_categories, before_info = self._collect_managed_report_data()
        attempted_pids = sorted(before_categories)

        stopped_pids: set[int] = set()
        denied_pids: set[int] = set()
        if attempted_pids:
            process_pid = attempted_pids[0]
            stopped_pids, denied_pids = terminate_process_tree(process_pid)
            denied_pids = self._verified_denied_pids(
                denied_pids, set(attempted_pids),
            )

        launch_detached(self.process_path)
        started_pid = self._wait_for_managed_process_start()
        started_categories, started_info = (
            self._collect_managed_report_data(started_pid)
        )

        stopped_known, denied_known, gone_known = self._classify_attempted_pids(
            attempted_pids,
            stopped_pids,
            denied_pids,
        )
        started_known = sorted(started_categories)

        report_sections = self._build_report_sections_from_pid_groups(
            before_info | started_info,
            [
                ('Closed', stopped_known),
                ('Could not close (permissions)', denied_known),
                ('Already gone / ended during action', gone_known),
                ('Started', started_known),
            ],
        )

        if denied_known or not started_known:
            self._report_and_notify(
                f'Restart partial: closed {len(stopped_known)},'
                f' started {len(started_known)},'
                f' denied {len(denied_known)}.',
                'Restart partial',
                QMessageBox.Icon.Warning,
                report_sections,
            )
            if denied_known:
                self._offer_uac_elevation(
                    reason=(
                        'Windows denied permission while trying'
                        ' to restart AMD Adrenalin.'
                    ),
                )
            return

        self._report_and_notify(
            f'Restarted AMD Adrenalin:'
            f' closed {len(stopped_known)},'
            f' started {len(started_known)}.',
            'Restart complete',
            QMessageBox.Icon.Information,
            report_sections,
        )

    def start_only(self) -> None:
        """Launch Radeon Software without stopping any existing instance first."""
        if not self._ensure_process_path_exists():
            return

        existing_pid = get_pid_by_path(self.process_path)
        if existing_pid is not None:
            existing_categories, existing_info = (
                self._collect_managed_report_data(existing_pid)
            )

            self._report_and_notify(
                'RadeonSoftware.exe is already running.',
                'Already running',
                QMessageBox.Icon.Information,
                self._build_report_sections_from_pid_groups(
                    existing_info,
                    [('Running', sorted(existing_categories))],
                ),
            )
            return

        launch_detached(self.process_path)
        started_pid = self._wait_for_managed_process_start()
        started_categories, started_info = (
            self._collect_managed_report_data(started_pid)
        )
        started_known = sorted(started_categories)
        report_sections = self._build_report_sections_from_pid_groups(
            started_info,
            [('Started', started_known)],
        )

        if not started_known:
            self._report_and_notify(
                'Launch requested, but no AMD Adrenalin process was detected yet.',
                'Start status',
                QMessageBox.Icon.Warning,
                report_sections,
            )
            return

        self._report_and_notify(
            f'Started {len(started_known)} AMD Adrenalin process(es).',
            'Started',
            QMessageBox.Icon.Information,
            report_sections,
        )

    def _set_monitor_badge(self, *, is_running: bool) -> None:
        """Update the monitor badge text and style based on running state."""
        new_name = 'badge_running' if is_running else 'badge_stopped'
        if self.status_badge.objectName() == new_name:
            return
        self.status_badge.setText(
            '● RUNNING' if is_running else '● NOT RUNNING',
        )
        self.status_badge.setObjectName(new_name)
        self.status_badge.setStyle(self.status_badge.style())

    def _schedule_refresh(self) -> None:
        """Schedule a process snapshot refresh without blocking the UI thread."""
        if self._refresh.in_flight:
            self._refresh.pending = True
            return

        self._refresh.in_flight = True
        worker = threading.Thread(
            target=self._run_refresh_worker,
            args=(self._process_path_str,),
            daemon=True,
            name='proc-refresh',
        )
        worker.start()

    def _run_refresh_worker(self, process_path: str) -> None:
        """Collect a refresh snapshot in a worker thread."""
        try:
            snapshot = collect_refresh_snapshot(process_path)
        except (RuntimeError, ValueError, TypeError, psutil.Error, OSError) as exc:
            self._refresh.bridge.snapshot_ready.emit({'error': str(exc)})
            return

        self._refresh.bridge.snapshot_ready.emit(snapshot)

    def _apply_refresh_snapshot(self, snapshot: object) -> None:
        """Apply worker-produced refresh data on the GUI thread."""
        self._refresh.in_flight = False

        if isinstance(snapshot, dict) and 'error' not in snapshot:
            is_running = bool(snapshot.get('is_running', False))
            managed_rows = snapshot.get('managed_rows', [])
            companion_rows = snapshot.get('companion_rows', [])
            service_rows = snapshot.get('service_rows', [])

            if (
                isinstance(managed_rows, list)
                and isinstance(companion_rows, list)
                and isinstance(service_rows, list)
            ):
                self._set_monitor_badge(is_running=is_running)
                self._update_managed_section(managed_rows)
                self._update_process_section(
                    self.companion_section,
                    self.companion_tree,
                    companion_rows,
                )
                self._update_process_section(
                    self.service_section,
                    self.service_tree,
                    service_rows,
                    muted=True,
                )

        if self._refresh.pending:
            self._refresh.pending = False
            self._schedule_refresh()

    def _refresh_process_info(self) -> None:
        """Request an asynchronous monitor refresh."""
        self._schedule_refresh()

    def stop_only(self) -> None:
        """Terminate the running Radeon Software process tree."""
        pid = get_pid_by_path(self.process_path)
        if pid is None:
            self.status_label.setText('RadeonSoftware.exe is not running.')
            self._popup(
                'Not running',
                'AMD Adrenalin is not currently running.',
                QMessageBox.Icon.Warning,
            )
            return

        target_categories, process_info = self._collect_managed_report_data(pid)

        stopped_pids, denied_pids = terminate_process_tree(pid)
        denied_pids = self._verified_denied_pids(
            denied_pids, set(target_categories),
        )

        attempted_pids = sorted(target_categories)
        stopped_known, denied_known, gone_known_unsorted = (
            self._classify_attempted_pids(
                attempted_pids,
                stopped_pids,
                denied_pids,
            )
        )
        gone_known = sorted(gone_known_unsorted)

        report_sections = self._build_report_sections_from_pid_groups(
            process_info,
            [
                ('Closed', stopped_known),
                ('Could not close (permissions)', denied_known),
                ('Already gone / ended during action', gone_known),
            ],
        )

        if denied_known:
            self._report_and_notify(
                f'Stop partial:'
                f' closed {len(stopped_known)},'
                f' denied {len(denied_known)}.',
                'Stop partial',
                QMessageBox.Icon.Warning,
                report_sections,
            )
            self._offer_uac_elevation(
                reason='Windows denied permission while trying to stop AMD Adrenalin.',
            )
            return

        if stopped_pids:
            self._report_and_notify(
                f'Stopped {len(stopped_known)} AMD Adrenalin process(es).',
                'Stopped',
                QMessageBox.Icon.Information,
                report_sections,
            )
            return

        self._report_and_notify(
            'RadeonSoftware.exe is no longer running.',
            'Already stopped',
            QMessageBox.Icon.Information,
            report_sections,
        )

    def _collect_managed_targets(
        self,
        target_categories: dict[int, str],
        process_info: dict[int, dict[str, str]],
    ) -> None:
        """Collect the main Radeon process and all its child targets."""
        main_pid = get_pid_by_path(self.process_path)
        if main_pid is None:
            return

        self._collect_process_tree_targets_for_pid(
            main_pid,
            'Managed',
            target_categories,
            process_info,
        )

    def _collect_companion_service_targets(
        self,
        target_categories: dict[int, str],
        process_info: dict[int, dict[str, str]],
    ) -> None:
        """Collect companion/service processes and their child targets."""
        tracked_names = COMPANION_NAMES | SERVICE_NAMES
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name = proc.info.get('name')
                if not isinstance(name, str):
                    continue
                name_lower = name.lower()
                if name_lower not in tracked_names:
                    continue

                category = 'Companion' if name_lower in COMPANION_NAMES else 'Service'
                target_categories[proc.pid] = category
                capture_process_info(process_info, proc.pid, category)
                try:
                    for child in proc.children(recursive=True):
                        if child.pid not in target_categories:
                            target_categories[child.pid] = category
                        capture_process_info(process_info, child.pid, category)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def _stop_targets(
        self,
        target_categories: dict[int, str],
    ) -> tuple[set[int], set[int]]:
        """Stop each target process tree; return stopped/denied PIDs."""
        stopped_pids_total: set[int] = set()
        denied_pids_total: set[int] = set()
        for pid in sorted(target_categories):
            stopped_pids, denied_pids = terminate_process_tree(pid)
            stopped_pids_total.update(stopped_pids)
            denied_pids_total.update(denied_pids)
        return stopped_pids_total, denied_pids_total

    def stop_all(self) -> None:
        """Terminate Radeon Software plus monitored AMD processes."""
        target_categories: dict[int, str] = {}
        process_info: dict[int, dict[str, str]] = {}

        self._collect_managed_targets(target_categories, process_info)
        self._collect_companion_service_targets(target_categories, process_info)

        if not target_categories:
            self.status_label.setText('No monitored AMD processes are running.')
            self._popup(
                'Nothing to stop',
                'No monitored AMD processes were found.',
                QMessageBox.Icon.Information,
            )
            return

        stopped_pids_total, denied_pids_total = self._stop_targets(target_categories)
        denied_pids_total = self._verified_denied_pids(
            denied_pids_total, set(target_categories),
        )

        for pid in stopped_pids_total | denied_pids_total:
            category = target_categories.get(pid, 'Unknown')
            capture_process_info(process_info, pid, category)

        report_sections = build_stop_all_report_sections(
            process_info,
            stopped_pids_total,
            denied_pids_total,
        )

        stopped_count = len(stopped_pids_total)
        denied_count = len(denied_pids_total)
        if denied_count > 0:
            self._report_and_notify(
                f'Stopped {stopped_count} AMD process(es),'
                f' {denied_count} denied by permissions.',
                'Stop All partial',
                QMessageBox.Icon.Warning,
                report_sections,
            )
            self._offer_uac_elevation(
                reason=(
                    'Windows denied permission while trying'
                    ' to stop one or more AMD processes.'
                ),
            )
            return

        self._report_and_notify(
            f'Stopped {stopped_count} monitored AMD process(es).',
            'Stop All complete',
            QMessageBox.Icon.Information,
            report_sections,
        )
