"""Main application window and UI behavior."""

import contextlib
import time

import psutil
from PyQt6.QtCore import QCoreApplication, QPoint, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QKeySequence
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ._report_helpers import build_stop_all_report_sections, capture_process_info, to_report_entry
from ._stylesheet import MAIN_STYLESHEET
from .constants import COMPANION_NAMES, RADEON_SOFTWARE_PATH, SERVICE_NAMES, STATUS_COLORS
from .dialogs import NotificationDialog, ProcessReportDialog
from .process_ops import get_pid_by_path, launch_detached, terminate_process_tree
from .uac import is_debug_session, is_running_as_admin, request_self_elevation
from .ui_helpers import copy_selected_cells, copy_selected_rows, require_qheader_view, require_str

PATH_COLUMN_INDEX = 1
PID_COLUMN_INDEX = 2
STATUS_COLUMN_INDEX = 5
NAME_COLUMN_INDEX = 0
EVEN_ROW_REMAINDER = 0


class MainWindow(QMainWindow):
    """Main application window for controlling and monitoring AMD Adrenalin."""

    def __init__(self) -> None:
        """Initialise the main window, build the UI, and start the refresh timer."""
        super().__init__()
        self.process_path = RADEON_SOFTWARE_PATH
        self.setWindowTitle("AMD Adrenalin Control")
        self.setMinimumSize(973, 733)
        self.resize(1113, 853)

        # Define UI attributes in __init__ to satisfy pylint W0201.
        self.status_label = QLabel("Monitoring Radeon Software and related AMD processes.", self)
        self.path_label = QLabel(f"Path: {self.process_path}", self)
        self.status_badge = QLabel("● NOT RUNNING", self)
        self.status_badge.setObjectName("badge_stopped")
        self.managed_section, self.managed_table = self._create_process_section(
            self,
            "Radeon Software Managed",
            "Main RadeonSoftware.exe process and any child processes spawned from it.",
        )
        self.companion_section, self.companion_table = self._create_process_section(
            self,
            "AMD Companion Processes",
            "Supporting user-space AMD helper executables that assist telemetry and features.",
        )
        self.service_section, self.service_table = self._create_process_section(
            self,
            "AMD System Services",
            "Background service executables that provide driver and system-level AMD functionality.",
        )
        self._process_tables = [self.managed_table, self.companion_table, self.service_table]

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh_process_info)  # pyright: ignore[reportUnknownMemberType]
        self._timer.start()
        self._refresh_process_info()

    def _build_ui(self) -> None:
        """Construct and lay out all widgets in the main window."""
        central = QWidget(self)
        central.setObjectName("central_widget")
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

    def _build_top_controls(self, layout: QGridLayout) -> None:
        """Build status labels and top action buttons."""
        self.status_label.setWordWrap(True)
        self.path_label.setWordWrap(True)

        restart_btn = QPushButton("Restart Adrenalin", self)
        restart_btn.setMinimumHeight(40)
        restart_btn.clicked.connect(self.restart_software)  # pyright: ignore[reportUnknownMemberType]

        start_btn = QPushButton("Start Adrenalin", self)
        start_btn.setMinimumHeight(40)
        start_btn.setObjectName("start_btn")
        start_btn.clicked.connect(self.start_only)  # pyright: ignore[reportUnknownMemberType]

        stop_btn = QPushButton("Stop Adrenalin", self)
        stop_btn.setMinimumHeight(40)
        stop_btn.setObjectName("stop_btn")
        stop_btn.clicked.connect(self.stop_only)  # pyright: ignore[reportUnknownMemberType]

        stop_all_btn = QPushButton("Stop All Adrenalin processes", self)
        stop_all_btn.setMinimumHeight(38)
        stop_all_btn.setObjectName("stop_all_btn")
        stop_all_btn.clicked.connect(self.stop_all)  # pyright: ignore[reportUnknownMemberType]

        layout.addWidget(self.status_label, 0, 0, 1, 3)
        layout.addWidget(self.path_label, 1, 0, 1, 3)
        layout.addWidget(restart_btn, 2, 0)
        layout.addWidget(start_btn, 2, 1)
        layout.addWidget(stop_btn, 2, 2)
        layout.addWidget(stop_all_btn, 3, 0, 1, 3)

    def _build_monitor_header(self, layout: QGridLayout) -> None:
        """Build the live monitor heading and status badge row."""
        monitor_header = QWidget(self)
        monitor_header.setObjectName("monitor_header")
        header_layout = QHBoxLayout(monitor_header)
        header_layout.setContentsMargins(0, 4, 0, 0)
        header_layout.setSpacing(10)

        monitor_label = QLabel("Live Process Monitor", self)
        monitor_label.setObjectName("monitor_label")
        header_layout.addWidget(monitor_label)
        header_layout.addWidget(self.status_badge)
        header_layout.addStretch()
        layout.addWidget(monitor_header, 4, 0, 1, 3)

    def _build_monitor_sections(self, layout: QGridLayout) -> None:
        """Build the process monitor scroll area and section tables."""
        monitor_scroll = QScrollArea(self)
        monitor_scroll.setObjectName("monitor_scroll")
        monitor_scroll.setWidgetResizable(True)
        monitor_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        if viewport := monitor_scroll.viewport():
            viewport.setObjectName("monitor_viewport")

        monitor_content = QWidget(monitor_scroll)
        monitor_content.setObjectName("monitor_content")
        monitor_layout = QVBoxLayout(monitor_content)
        monitor_layout.setContentsMargins(0, 0, 0, 0)
        monitor_layout.setSpacing(14)

        monitor_layout.addWidget(self.managed_section)
        monitor_layout.addWidget(self.companion_section)
        monitor_layout.addWidget(self.service_section)
        monitor_layout.addStretch()

        monitor_scroll.setWidget(monitor_content)
        layout.addWidget(monitor_scroll, 5, 0, 1, 3)

    def _apply_stylesheet(self) -> None:
        """Apply the main window stylesheet."""
        self.setStyleSheet(MAIN_STYLESHEET)

    def _show_process_sections(self) -> None:
        """Ensure all process sections are visible after UI construction."""
        self.managed_section.show()
        self.companion_section.show()
        self.service_section.show()

    def _configure_process_table_interactions(self, table: QTableWidget) -> None:
        """Enable row selection, copy, and row context menu actions."""
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(  # pyright: ignore[reportUnknownMemberType]
            lambda pos, current_table=table: self._show_process_context_menu(current_table, pos),
        )

        copy_action = QAction(table)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        copy_action.triggered.connect(  # pyright: ignore[reportUnknownMemberType]
            lambda _, current_table=table: copy_selected_cells(current_table),
        )
        table.addAction(copy_action)
        table.itemSelectionChanged.connect(  # pyright: ignore[reportUnknownMemberType]
            lambda current_table=table: self._enforce_single_table_selection(current_table),
        )

    def _enforce_single_table_selection(self, active_table: QTableWidget) -> None:
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
    ) -> tuple[QWidget, QTableWidget]:
        """Create a labeled process section with a dedicated table."""
        section = QWidget(parent)
        section.setObjectName("process_section")
        section.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(12, 12, 12, 12)
        section_layout.setSpacing(8)

        label = QLabel(title, section)
        label.setObjectName("section_header")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        description_label = QLabel(description, section)
        description_label.setObjectName("section_description")
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        table = QTableWidget(0, 6, section)
        table.setObjectName("process_table")
        table.setHorizontalHeaderLabels(["Name", "Path", "PID", "CPU %", "Memory", "Status"])  # pyright: ignore[reportUnknownMemberType]
        if h_header := table.horizontalHeader():
            h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            h_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        if v_header := table.verticalHeader():
            v_header.hide()
            v_header.setMinimumWidth(0)
            v_header.setMaximumWidth(0)
            v_header.setFixedWidth(0)
            v_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            v_header.setSectionsClickable(False)
            v_header.setHighlightSections(False)
            v_header.setDefaultSectionSize(28)
        table.setCornerButtonEnabled(False)
        self._configure_process_table_interactions(table)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        section_layout.addWidget(label)
        section_layout.addWidget(description_label)
        section_layout.addWidget(table)
        return section, table

    def _process_tooltip(self, proc: psutil.Process) -> str:
        """Return a tooltip describing the process executable path."""
        try:
            exe_path = proc.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "Executable path unavailable"

        if not exe_path:
            return "Executable path unavailable"
        return exe_path

    def _resize_process_table(self, table: QTableWidget) -> None:
        """Fit a process table to its rows so stacked sections stay compact."""
        header_height = require_qheader_view(table.horizontalHeader(), "horizontal header").height()
        row_height = require_qheader_view(table.verticalHeader(), "vertical header").defaultSectionSize()
        frame_height = table.frameWidth() * 2
        table.setFixedHeight(header_height + (table.rowCount() * row_height) + frame_height)

    def _populate_process_table(
        self,
        table: QTableWidget,
        processes: list[tuple[psutil.Process, int]],
        *,
        muted: bool = False,
    ) -> None:
        """Populate a process table with the supplied rows."""
        table.setRowCount(len(processes))

        for row_idx, (proc, indent) in enumerate(processes):
            try:
                prefix = "  └  " if indent > 0 else ""
                name = prefix + proc.name()
                path = self._process_tooltip(proc)
                p = str(proc.pid)
                cpu = f"{proc.cpu_percent(interval=None):.1f} %"
                mem_mb = proc.memory_info().rss / (1024 * 1024)
                mem = f"{mem_mb:.1f} MB"
                status = require_str(proc.status(), "process status")
            except psutil.NoSuchProcess:
                name, path, p, cpu, mem, status = "<ended>", "<unavailable>", "-", "-", "-", "gone"

            values = [name, path, p, cpu, mem, status]
            aligns = [
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignCenter,
            ]
            row_bg = (
                QColor("#111827")
                if row_idx % 2 == EVEN_ROW_REMAINDER
                else QColor("#0d1220")
            )
            for col, (val, align) in enumerate(zip(values, aligns, strict=True)):
                item = QTableWidgetItem(val)
                item.setTextAlignment(align)
                item.setBackground(row_bg)
                if col == PATH_COLUMN_INDEX:
                    item.setToolTip(self._process_tooltip(proc))
                if col == NAME_COLUMN_INDEX:
                    item.setData(Qt.ItemDataRole.UserRole, proc.pid)
                    with contextlib.suppress(psutil.Error):
                        item.setData(
                            Qt.ItemDataRole.UserRole + 1,
                            len(proc.children(recursive=False)) > 0,
                        )
                if col == STATUS_COLUMN_INDEX:
                    item.setForeground(QColor(STATUS_COLORS.get(status, "#94a3b8")))
                elif muted or indent > 0:
                    item.setForeground(QColor("#94a3b8"))
                table.setItem(row_idx, col, item)

        self._resize_process_table(table)

    def _update_process_section(
        self,
        section: QWidget,
        table: QTableWidget,
        processes: list[tuple[psutil.Process, int]],
        *,
        muted: bool = False,
    ) -> None:
        """Keep section visible and show either process rows or an empty-state row."""
        section.setVisible(True)
        if not processes:
            table.setRowCount(1)
            empty_values = ["No active processes", "-", "-", "-", "-", "idle"]
            empty_aligns = [
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignCenter,
            ]
            for col, (val, align) in enumerate(zip(empty_values, empty_aligns, strict=True)):
                item = QTableWidgetItem(val)
                item.setTextAlignment(align)
                item.setBackground(QColor("#0d1220"))
                item.setForeground(QColor("#64748b"))
                table.setItem(0, col, item)
            self._resize_process_table(table)
            return
        self._populate_process_table(table, processes, muted=muted)

    def _process_pid_from_row(self, table: QTableWidget, row_idx: int) -> int | None:
        """Return the PID for a populated process row, or None for placeholder rows."""
        name_item = table.item(row_idx, NAME_COLUMN_INDEX)
        if name_item is None:
            return None

        pid_value = name_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(pid_value, int):
            return pid_value
        return None

    def _terminate_single_process(self, pid: int) -> None:
        """Terminate a single process by PID and refresh the display."""
        failure_reason: str | None = None
        permission_denied = False
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=3)
        except psutil.AccessDenied:
            failure_reason = "Permission denied while terminating the process. Try running as administrator."
            permission_denied = True
        except psutil.TimeoutExpired:
            try:
                proc = psutil.Process(pid)
                proc.kill()
                proc.wait(timeout=3)
            except psutil.AccessDenied:
                failure_reason = "Permission denied while force-stopping the process. Try running as administrator."
                permission_denied = True
            except psutil.TimeoutExpired:
                failure_reason = "The process did not exit after terminate and force-stop attempts."
            except psutil.NoSuchProcess:
                pass
        except psutil.NoSuchProcess:
            pass

        self._refresh_process_info()

        if failure_reason is not None:
            self.status_label.setText(f"Failed to terminate PID {pid}: {failure_reason}")
            self._popup(
                "Terminate failed",
                f"Could not terminate PID {pid}.\n\nReason: {failure_reason}",
                QMessageBox.Icon.Warning,
            )
            if permission_denied:
                self._offer_uac_elevation(
                    reason="Windows denied permission while trying to terminate the selected process.",
                )

    def _stop_single_process(self, pid: int) -> None:
        """Terminate a single process tree by PID and refresh the display."""
        _, denied_pids = terminate_process_tree(pid)
        self._refresh_process_info()
        if denied_pids:
            self._offer_uac_elevation(
                reason="Windows denied permission while trying to terminate the selected process tree.",
            )

    def _row_has_children(self, table: QTableWidget, row_idx: int) -> bool:
        """Return cached child-process info for a row, defaulting to False."""
        name_item = table.item(row_idx, NAME_COLUMN_INDEX)
        if name_item is None:
            return False

        has_children = name_item.data(Qt.ItemDataRole.UserRole + 1)
        return bool(has_children)

    def _confirm_terminate(self, *, pid: int, tree: bool) -> bool:
        """Ask user to confirm terminate action."""
        action_text = "terminate this process tree" if tree else "terminate this process"
        detail = "This will stop the selected process and all child processes." if tree else "This will stop only the selected process."
        answer = QMessageBox.question(
            self,
            "Confirm terminate",
            f"Are you sure you want to {action_text}?\n\nPID: {pid}\n\n{detail}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _handle_process_menu_action(
        self,
        *,
        chosen_action: QAction | None,
        actions: dict[str, QAction | None],
        table: QTableWidget,
        pid: int | None,
    ) -> None:
        """Execute the selected process-row context menu action."""
        copy_cells_action = actions["copy_cells"]
        copy_rows_action = actions["copy_rows"]
        terminate_process_action = actions["terminate_process"]
        terminate_tree_action = actions["terminate_tree"]

        if chosen_action is None:
            return

        if copy_cells_action is not None and chosen_action == copy_cells_action:
            copy_selected_cells(table)
            return

        if copy_rows_action is not None and chosen_action == copy_rows_action:
            copy_selected_rows(table)
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

    def _show_process_context_menu(self, table: QTableWidget, position: QPoint) -> None:
        """Show row actions for a real process row under the mouse."""
        row_idx = table.rowAt(position.y())
        if row_idx < 0:
            return
        col_idx = table.columnAt(position.x())
        col_idx = max(col_idx, 0)

        selection_model = table.selectionModel()
        if selection_model is not None and not selection_model.hasSelection():
            table.setCurrentCell(row_idx, col_idx)

        pid = self._process_pid_from_row(table, row_idx)

        menu = QMenu(table)
        copy_cells_action = menu.addAction("Copy selected cells")
        copy_rows_action = menu.addAction("Copy selected rows")
        terminate_process_action = None
        terminate_tree_action = None
        if pid is not None:
            menu.addSeparator()
            terminate_process_action = menu.addAction("Terminate process")
            if self._row_has_children(table, row_idx):
                terminate_tree_action = menu.addAction("Terminate process tree")
        viewport = table.viewport()
        if viewport is None:
            return

        chosen_action = menu.exec(viewport.mapToGlobal(position))
        actions: dict[str, QAction | None] = {
            "copy_cells": copy_cells_action,
            "copy_rows": copy_rows_action,
            "terminate_process": terminate_process_action,
            "terminate_tree": terminate_tree_action,
        }
        self._handle_process_menu_action(
            chosen_action=chosen_action,
            actions=actions,
            table=table,
            pid=pid,
        )

    def _popup(self, title: str, text: str, icon: QMessageBox.Icon) -> None:
        """Show a styled in-app modal dialog for status and report messages."""
        dialog = NotificationDialog(self, title, text, icon)
        dialog.exec()

    def _offer_uac_elevation(self, *, reason: str) -> None:
        """Offer to relaunch this app with elevation when an action is denied."""
        if is_running_as_admin():
            self._popup(
                "Permissions required",
                f"{reason}\n\nThe app is already running as administrator.",
                QMessageBox.Icon.Warning,
            )
            return

        answer = QMessageBox.question(
            self,
            "Administrator privileges required",
            (
                f"{reason}\n\n"
                "Would you like to relaunch this app as administrator now?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        if request_self_elevation():
            if is_debug_session():
                self.status_label.setText(
                    "Elevation requested in debug mode. Keep this window open; close it manually after elevated app is stable.",
                )
                return

            self.status_label.setText("Elevation requested. Closing this window in favor of elevated instance.")
            self.close()
            return

        self._popup(
            "Elevation failed",
            "Could not request administrator privileges from Windows.",
            QMessageBox.Icon.Warning,
        )

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
            self._collect_process_tree_targets_for_pid(managed_pid, "Managed", target_categories, process_info)

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

    def restart_software(self) -> None:
        """Stop any running instance of Radeon Software, then launch a fresh one."""
        if not self.process_path.exists():
            self.status_label.setText("RadeonSoftware.exe path was not found.")
            self._popup(
                "Path not found",
                f"Could not find executable at:\n{self.process_path}",
                QMessageBox.Icon.Critical,
            )
            return

        before_categories, before_info = self._collect_managed_report_data()
        attempted_pids = sorted(before_categories)

        stopped_pids: set[int] = set()
        denied_pids: set[int] = set()
        if attempted_pids:
            process_pid = attempted_pids[0]
            stopped_pids, denied_pids = terminate_process_tree(process_pid)

        launch_detached(self.process_path)
        started_pid = self._wait_for_managed_process_start()
        started_categories, started_info = self._collect_managed_report_data(started_pid)

        stopped_known = [pid for pid in attempted_pids if pid in stopped_pids]
        denied_known = [pid for pid in attempted_pids if pid in denied_pids]
        gone_known = [pid for pid in attempted_pids if pid not in stopped_pids and pid not in denied_pids]
        started_known = sorted(started_categories)

        report_sections = self._build_report_sections_from_pid_groups(
            before_info | started_info,
            [
                ("Closed", stopped_known),
                ("Could not close (permissions)", denied_known),
                ("Already gone / ended during action", gone_known),
                ("Started", started_known),
            ],
        )

        if denied_known or not started_known:
            self.status_label.setText(
                f"Restart partial: closed {len(stopped_known)}, started {len(started_known)}, denied {len(denied_known)}.",
            )
            self._show_process_report("Restart partial", QMessageBox.Icon.Warning, report_sections)
            if denied_known:
                self._offer_uac_elevation(
                    reason="Windows denied permission while trying to restart AMD Adrenalin.",
                )
            return

        self.status_label.setText(
            f"Restarted AMD Adrenalin: closed {len(stopped_known)}, started {len(started_known)}.",
        )
        self._show_process_report("Restart complete", QMessageBox.Icon.Information, report_sections)

    def start_only(self) -> None:
        """Launch Radeon Software without stopping any existing instance first."""
        if not self.process_path.exists():
            self.status_label.setText("RadeonSoftware.exe path was not found.")
            self._popup(
                "Path not found",
                f"Could not find executable at:\n{self.process_path}",
                QMessageBox.Icon.Critical,
            )
            return

        existing_pid = get_pid_by_path(self.process_path)
        if existing_pid is not None:
            existing_categories, existing_info = self._collect_managed_report_data(existing_pid)

            self.status_label.setText("RadeonSoftware.exe is already running.")
            self._show_process_report(
                "Already running",
                QMessageBox.Icon.Information,
                self._build_report_sections_from_pid_groups(
                    existing_info,
                    [("Running", sorted(existing_categories))],
                ),
            )
            return

        launch_detached(self.process_path)
        started_pid = self._wait_for_managed_process_start()
        started_categories, started_info = self._collect_managed_report_data(started_pid)
        started_known = sorted(started_categories)
        report_sections = self._build_report_sections_from_pid_groups(
            started_info,
            [("Started", started_known)],
        )

        if not started_known:
            self.status_label.setText("Launch requested, but no AMD Adrenalin process was detected yet.")
            self._show_process_report("Start status", QMessageBox.Icon.Warning, report_sections)
            return

        self.status_label.setText(f"Started {len(started_known)} AMD Adrenalin process(es).")
        self._show_process_report("Started", QMessageBox.Icon.Information, report_sections)

    def _collect_running_processes(self) -> dict[int, psutil.Process]:
        """Collect running processes keyed by PID and warm up CPU counters."""
        all_procs: dict[int, psutil.Process] = {}
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                all_procs[proc.pid] = proc
                proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return all_procs

    def _build_managed_rows(self, pid: int | None) -> tuple[list[tuple[psutil.Process, int]], set[int]]:
        """Build rows for the main managed process and its children."""
        if pid is None:
            return [], set()

        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            return [], set()

        main_rows = [(parent, 0)] + [(child, 1) for child in children]
        managed_pids = {proc.pid for proc, _ in main_rows}
        return main_rows, managed_pids

    def _split_companion_and_service_rows(
        self,
        all_procs: dict[int, psutil.Process],
        managed_pids: set[int],
    ) -> tuple[list[psutil.Process], list[psutil.Process]]:
        """Return companion and service process lists excluding managed rows."""
        companion_rows: list[psutil.Process] = []
        service_rows: list[psutil.Process] = []

        for proc in all_procs.values():
            if proc.pid in managed_pids:
                continue
            try:
                name_lower = proc.name().lower()
                if name_lower in COMPANION_NAMES:
                    companion_rows.append(proc)
                elif name_lower in SERVICE_NAMES:
                    service_rows.append(proc)
            except psutil.NoSuchProcess:
                pass

        companion_rows.sort(key=lambda proc: proc.name().lower())
        service_rows.sort(key=lambda proc: proc.name().lower())
        return companion_rows, service_rows

    def _set_monitor_badge(self, *, is_running: bool) -> None:
        """Update the monitor badge text and style based on running state."""
        if is_running:
            self.status_badge.setText("● RUNNING")
            self.status_badge.setObjectName("badge_running")
        else:
            self.status_badge.setText("● NOT RUNNING")
            self.status_badge.setObjectName("badge_stopped")
        self.status_badge.setStyle(self.status_badge.style())

    def _refresh_process_info(self) -> None:
        """Query running processes and update the live process tables."""
        pid = get_pid_by_path(self.process_path)

        all_procs = self._collect_running_processes()
        main_rows, managed_pids = self._build_managed_rows(pid)
        companion_rows, service_rows = self._split_companion_and_service_rows(all_procs, managed_pids)
        self._set_monitor_badge(is_running=bool(main_rows))

        self._update_process_section(self.managed_section, self.managed_table, main_rows)
        self._update_process_section(
            self.companion_section,
            self.companion_table,
            [(proc, 0) for proc in companion_rows],
        )
        self._update_process_section(
            self.service_section,
            self.service_table,
            [(proc, 0) for proc in service_rows],
            muted=True,
        )

    def stop_only(self) -> None:
        """Terminate the running Radeon Software process tree."""
        pid = get_pid_by_path(self.process_path)
        if pid is None:
            self.status_label.setText("RadeonSoftware.exe is not running.")
            self._popup(
                "Not running",
                "AMD Adrenalin is not currently running.",
                QMessageBox.Icon.Warning,
            )
            return

        target_categories, process_info = self._collect_managed_report_data(pid)

        stopped_pids, denied_pids = terminate_process_tree(pid)

        attempted_pids = sorted(target_categories)
        stopped_known = [pid_val for pid_val in attempted_pids if pid_val in stopped_pids]
        denied_known = [pid_val for pid_val in attempted_pids if pid_val in denied_pids]
        gone_known = sorted(
            pid_val
            for pid_val in attempted_pids
            if pid_val not in stopped_pids and pid_val not in denied_pids
        )

        report_sections = self._build_report_sections_from_pid_groups(
            process_info,
            [
                ("Closed", stopped_known),
                ("Could not close (permissions)", denied_known),
                ("Already gone / ended during action", gone_known),
            ],
        )

        if denied_known:
            self.status_label.setText(
                f"Stop partial: closed {len(stopped_known)}, denied {len(denied_known)}.",
            )
            self._show_process_report("Stop partial", QMessageBox.Icon.Warning, report_sections)
            self._offer_uac_elevation(
                reason="Windows denied permission while trying to stop AMD Adrenalin.",
            )
            return

        if stopped_pids:
            self.status_label.setText(
                f"Stopped {len(stopped_known)} AMD Adrenalin process(es).",
            )
            self._show_process_report("Stopped", QMessageBox.Icon.Information, report_sections)
            return

        self.status_label.setText("RadeonSoftware.exe is no longer running.")
        self._show_process_report("Already stopped", QMessageBox.Icon.Information, report_sections)

    def _collect_managed_targets(
        self,
        target_categories: dict[int, str],
        process_info: dict[int, dict[str, str]],
    ) -> None:
        """Collect the main Radeon process and all its child targets."""
        main_pid = get_pid_by_path(self.process_path)
        if main_pid is None:
            return

        self._collect_process_tree_targets_for_pid(main_pid, "Managed", target_categories, process_info)

    def _collect_companion_service_targets(
        self,
        target_categories: dict[int, str],
        process_info: dict[int, dict[str, str]],
    ) -> None:
        """Collect companion/service processes and their child targets."""
        tracked_names = COMPANION_NAMES | SERVICE_NAMES
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info.get("name")
                if not isinstance(name, str):
                    continue
                name_lower = name.lower()
                if name_lower not in tracked_names:
                    continue

                category = "Companion" if name_lower in COMPANION_NAMES else "Service"
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

    def _stop_targets(self, target_categories: dict[int, str]) -> tuple[set[int], set[int]]:
        """Stop each target process tree and return aggregate stopped/denied PID sets."""
        stopped_pids_total: set[int] = set()
        denied_pids_total: set[int] = set()
        for pid in sorted(target_categories):
            stopped_pids, denied_pids = terminate_process_tree(pid)
            stopped_pids_total.update(stopped_pids)
            denied_pids_total.update(denied_pids)
        return stopped_pids_total, denied_pids_total

    def stop_all(self) -> None:
        """Terminate Radeon Software plus monitored AMD companion and service processes."""
        target_categories: dict[int, str] = {}
        process_info: dict[int, dict[str, str]] = {}

        self._collect_managed_targets(target_categories, process_info)
        self._collect_companion_service_targets(target_categories, process_info)

        if not target_categories:
            self.status_label.setText("No monitored AMD processes are running.")
            self._popup(
                "Nothing to stop",
                "No monitored AMD processes were found.",
                QMessageBox.Icon.Information,
            )
            return

        stopped_pids_total, denied_pids_total = self._stop_targets(target_categories)

        for pid in stopped_pids_total | denied_pids_total:
            category = target_categories.get(pid, "Unknown")
            capture_process_info(process_info, pid, category)

        report_sections = build_stop_all_report_sections(
            process_info,
            stopped_pids_total,
            denied_pids_total,
        )

        stopped_count = len(stopped_pids_total)
        denied_count = len(denied_pids_total)
        if denied_count > 0:
            self.status_label.setText(
                f"Stopped {stopped_count} AMD process(es), {denied_count} denied by permissions.",
            )
            self._show_process_report("Stop All partial", QMessageBox.Icon.Warning, report_sections)
            self._offer_uac_elevation(
                reason="Windows denied permission while trying to stop one or more AMD processes.",
            )
            return

        self.status_label.setText(f"Stopped {stopped_count} monitored AMD process(es).")
        self._show_process_report("Stop All complete", QMessageBox.Icon.Information, report_sections)
