"""Main application window and UI behavior."""

import contextlib

import psutil
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .constants import COMPANION_NAMES, RADEON_SOFTWARE_PATH, SERVICE_NAMES, STATUS_COLORS
from .dialogs import NotificationDialog, ProcessReportDialog
from .process_ops import get_pid_by_path, launch_detached, terminate_process_tree
from .ui_helpers import require_qheader_view, require_str

STATUS_COLUMN_INDEX = 4
NAME_COLUMN_INDEX = 0
EVEN_ROW_REMAINDER = 0


class MainWindow(QMainWindow):
    """Main application window for controlling and monitoring AMD Adrenalin."""

    def __init__(self) -> None:
        """Initialise the main window, build the UI, and start the refresh timer."""
        super().__init__()
        self.process_path = RADEON_SOFTWARE_PATH
        self.setWindowTitle("AMD Adrenalin Control")
        self.setMinimumSize(940, 800)
        self.resize(1080, 920)

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

        start_btn = QPushButton("Start", self)
        start_btn.setMinimumHeight(40)
        start_btn.setObjectName("start_btn")
        start_btn.clicked.connect(self.start_only)  # pyright: ignore[reportUnknownMemberType]

        stop_btn = QPushButton("Stop", self)
        stop_btn.setMinimumHeight(40)
        stop_btn.setObjectName("stop_btn")
        stop_btn.clicked.connect(self.stop_only)  # pyright: ignore[reportUnknownMemberType]

        stop_all_btn = QPushButton("Stop All AMD", self)
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
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #0f141d;
            }
            QWidget#central_widget,
            QWidget#monitor_content,
            QWidget#monitor_viewport {
                background-color: #0f141d;
            }
            QLabel {
                color: #e9eef8;
                font-size: 13px;
            }
            QPushButton {
                background-color: #1f6feb;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background-color: #3a82f7;
            }
            QPushButton:pressed {
                background-color: #1759bf;
            }
            QPushButton#start_btn {
                background-color: #15803d;
            }
            QPushButton#start_btn:hover {
                background-color: #16a34a;
            }
            QPushButton#start_btn:pressed {
                background-color: #166534;
            }
            QPushButton#stop_btn {
                background-color: #b91c1c;
            }
            QPushButton#stop_btn:hover {
                background-color: #dc2626;
            }
            QPushButton#stop_btn:pressed {
                background-color: #991b1b;
            }
            QPushButton#stop_all_btn {
                background-color: #7f1d1d;
                border: 1px solid #991b1b;
            }
            QPushButton#stop_all_btn:hover {
                background-color: #991b1b;
            }
            QPushButton#stop_all_btn:pressed {
                background-color: #7a1616;
            }
            QTableWidget#process_table {
                background-color: #0d1220;
                color: #c9d8f0;
                border: 1px solid #1e2d45;
                border-radius: 6px;
                gridline-color: #1a2540;
                font-size: 12px;
                outline: 0;
            }
            QTableWidget#process_table::item {
                padding: 6px 10px;
                border: none;
            }
            QTableWidget#process_table::item:selected {
                background-color: #1c2e4a;
                color: #e9eef8;
            }
            QHeaderView::section {
                background-color: #141c2e;
                color: #6a9fd8;
                font-size: 11px;
                font-weight: 700;
                padding: 6px 10px;
                border: none;
                border-bottom: 1px solid #1e2d45;
            }
            QLabel#monitor_label {
                color: #6a9fd8;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#section_header {
                color: #6a9fd8;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.6px;
            }
            QLabel#section_description {
                color: #8ea7c7;
                font-size: 11px;
            }
            QLabel#badge_running {
                color: #22c55e;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#badge_stopped {
                color: #ef4444;
                font-size: 11px;
                font-weight: 700;
            }
            QWidget#process_section {
                background-color: #0b111d;
                border: 1px solid #182338;
                border-radius: 8px;
            }
            QScrollArea {
                background: transparent;
            }
            QScrollArea#monitor_scroll {
                border: none;
                background-color: #0f141d;
            }
            """,
        )

    def _show_process_sections(self) -> None:
        """Ensure all process sections are visible after UI construction."""
        self.managed_section.show()
        self.companion_section.show()
        self.service_section.show()

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

        table = QTableWidget(0, 5, section)
        table.setObjectName("process_table")
        table.setHorizontalHeaderLabels(["Name", "PID", "CPU %", "Memory", "Status"])  # pyright: ignore[reportUnknownMemberType]
        if h_header := table.horizontalHeader():
            h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        if v_header := table.verticalHeader():
            v_header.setVisible(False)
            v_header.setDefaultSectionSize(28)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
                p = str(proc.pid)
                cpu = f"{proc.cpu_percent(interval=None):.1f} %"
                mem_mb = proc.memory_info().rss / (1024 * 1024)
                mem = f"{mem_mb:.1f} MB"
                status = require_str(proc.status(), "process status")
            except psutil.NoSuchProcess:
                name, p, cpu, mem, status = "<ended>", "-", "-", "-", "gone"

            values = [name, p, cpu, mem, status]
            aligns = [
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
                if col == NAME_COLUMN_INDEX:
                    item.setToolTip(self._process_tooltip(proc))
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
            empty_values = ["No active processes", "-", "-", "-", "idle"]
            empty_aligns = [
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
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

    def _popup(self, title: str, text: str, icon: QMessageBox.Icon) -> None:
        """Show a styled in-app modal dialog for status and report messages."""
        dialog = NotificationDialog(self, title, text, icon)
        dialog.exec()

    def _show_process_report(
        self,
        title: str,
        icon: QMessageBox.Icon,
        sections: list[tuple[str, list[dict[str, str]]]],
    ) -> None:
        """Show a structured process report dialog."""
        dialog = ProcessReportDialog(self, title, icon, sections)
        dialog.exec()

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

        process_pid = get_pid_by_path(self.process_path)
        if process_pid:
            terminate_process_tree(process_pid)

        launch_detached(self.process_path)
        self.status_label.setText("RadeonSoftware.exe restarted successfully.")
        self._popup(
            "Restart complete",
            "AMD Adrenalin has been restarted successfully.",
            QMessageBox.Icon.Information,
        )

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
            process_name = self.process_path.name
            with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                process_name = psutil.Process(existing_pid).name()

            self.status_label.setText("RadeonSoftware.exe is already running.")
            self._popup(
                "Already running",
                f"AMD Adrenalin is already running: {process_name} (PID {existing_pid}).",
                QMessageBox.Icon.Information,
            )
            return

        launch_detached(self.process_path)
        self.status_label.setText("RadeonSoftware.exe started.")
        self._popup(
            "Started",
            "AMD Adrenalin was launched.",
            QMessageBox.Icon.Information,
        )

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

        attempted_processes: dict[int, str] = {}
        try:
            parent = psutil.Process(pid)
            try:
                attempted_processes[parent.pid] = parent.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                attempted_processes[parent.pid] = self.process_path.name

            try:
                for child in parent.children(recursive=True):
                    try:
                        attempted_processes[child.pid] = child.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        attempted_processes[child.pid] = "<unknown>"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            attempted_processes[pid] = self.process_path.name

        stopped_pids, denied_pids = terminate_process_tree(pid)

        attempted_pids = set(attempted_processes)
        stopped_known = sorted(pid_val for pid_val in attempted_pids if pid_val in stopped_pids)
        denied_known = sorted(pid_val for pid_val in attempted_pids if pid_val in denied_pids)
        gone_known = sorted(
            pid_val
            for pid_val in attempted_pids
            if pid_val not in stopped_pids and pid_val not in denied_pids
        )

        stopped_entries = [
            {
                "name": attempted_processes[pid_val],
                "pid": str(pid_val),
                "category": "Managed",
                "parent": "Managed tree",
                "path": "<unavailable>",
            }
            for pid_val in stopped_known
        ]
        denied_entries = [
            {
                "name": attempted_processes[pid_val],
                "pid": str(pid_val),
                "category": "Managed",
                "parent": "Managed tree",
                "path": "<unavailable>",
            }
            for pid_val in denied_known
        ]
        gone_entries = [
            {
                "name": attempted_processes[pid_val],
                "pid": str(pid_val),
                "category": "Managed",
                "parent": "Managed tree",
                "path": "<unavailable>",
            }
            for pid_val in gone_known
        ]
        report_sections = [
            ("Closed", stopped_entries),
            ("Could not close (permissions)", denied_entries),
            ("Already gone", gone_entries),
        ]

        if denied_known:
            self.status_label.setText(
                f"Stop partial: closed {len(stopped_entries)}, denied {len(denied_entries)}.",
            )
            self._show_process_report("Stop partial", QMessageBox.Icon.Warning, report_sections)
            return

        if stopped_pids:
            self.status_label.setText(
                f"Stopped {len(stopped_entries)} AMD Adrenalin process(es).",
            )
            self._show_process_report("Stopped", QMessageBox.Icon.Information, report_sections)
            return

        self.status_label.setText("RadeonSoftware.exe is no longer running.")
        self._show_process_report("Already stopped", QMessageBox.Icon.Information, report_sections)

    def _capture_process_info(
        self,
        process_info: dict[int, dict[str, str]],
        pid: int,
        category: str,
    ) -> None:
        """Capture best-effort process metadata for reporting."""
        existing = process_info.get(pid)
        if existing is not None:
            if existing.get("category") == "Unknown" and category != "Unknown":
                existing["category"] = category
            return

        name = "<unknown>"
        parent_text = "<unknown>"
        path_text = "<unavailable>"
        try:
            proc = psutil.Process(pid)
            with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                name = proc.name()

            try:
                parent_proc = proc.parent()
                if parent_proc is None:
                    parent_text = "None"
                else:
                    parent_name = "<unknown>"
                    with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                        parent_name = parent_proc.name()
                    parent_text = f"{parent_name} (PID {parent_proc.pid})"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            try:
                exe_path = proc.exe()
                path_text = exe_path or "<unavailable>"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        process_info[pid] = {
            "name": name,
            "category": category,
            "parent": parent_text,
            "path": path_text,
        }

    def _collect_managed_targets(
        self,
        target_categories: dict[int, str],
        process_info: dict[int, dict[str, str]],
    ) -> None:
        """Collect the main Radeon process and all its child targets."""
        main_pid = get_pid_by_path(self.process_path)
        if main_pid is None:
            return

        target_categories[main_pid] = "Managed"
        self._capture_process_info(process_info, main_pid, "Managed")
        try:
            parent = psutil.Process(main_pid)
            for child in parent.children(recursive=True):
                target_categories[child.pid] = "Managed"
                self._capture_process_info(process_info, child.pid, "Managed")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

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
                self._capture_process_info(process_info, proc.pid, category)
                try:
                    for child in proc.children(recursive=True):
                        if child.pid not in target_categories:
                            target_categories[child.pid] = category
                        self._capture_process_info(process_info, child.pid, category)
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

    def _to_report_entry(self, process_info: dict[int, dict[str, str]], pid: int) -> dict[str, str]:
        """Build a single report row for a PID from captured process metadata."""
        info = process_info.get(
            pid,
            {
                "name": "<unknown>",
                "category": "Unknown",
                "parent": "<unknown>",
                "path": "<unavailable>",
            },
        )
        return {
            "name": info["name"],
            "pid": str(pid),
            "category": info["category"],
            "parent": info["parent"],
            "path": info["path"],
        }

    def _build_stop_all_report_sections(
        self,
        process_info: dict[int, dict[str, str]],
        stopped_pids_total: set[int],
        denied_pids_total: set[int],
    ) -> list[tuple[str, list[dict[str, str]]]]:
        """Build grouped report sections for stop-all results."""
        attempted_pids = set(process_info)
        category_order: dict[str, int] = {
            "Managed": 0,
            "Companion": 1,
            "Service": 2,
            "Unknown": 3,
        }

        def report_sort_key(pid: int) -> tuple[int, int]:
            info = process_info.get(pid)
            category = info["category"] if info is not None else "Unknown"
            return category_order.get(category, 99), pid

        stopped_known = sorted(
            (pid for pid in attempted_pids if pid in stopped_pids_total),
            key=report_sort_key,
        )
        denied_known = sorted(
            (pid for pid in attempted_pids if pid in denied_pids_total),
            key=report_sort_key,
        )
        gone_known = sorted(
            (pid for pid in attempted_pids if pid not in stopped_pids_total and pid not in denied_pids_total),
            key=report_sort_key,
        )

        return [
            ("Closed", [self._to_report_entry(process_info, pid) for pid in stopped_known]),
            (
                "Could not close (permissions)",
                [self._to_report_entry(process_info, pid) for pid in denied_known],
            ),
            (
                "Already gone / ended during action",
                [self._to_report_entry(process_info, pid) for pid in gone_known],
            ),
        ]

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
            self._capture_process_info(process_info, pid, category)

        report_sections = self._build_stop_all_report_sections(
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
            return

        self.status_label.setText(f"Stopped {stopped_count} monitored AMD process(es).")
        self._show_process_report("Stop All complete", QMessageBox.Icon.Information, report_sections)
