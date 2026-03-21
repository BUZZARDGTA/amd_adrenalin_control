"""Process control actions, service management, refresh, and bulk operations."""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import psutil
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QLabel, QMessageBox, QTreeWidget, QWidget

from ._report_helpers import (
    build_stop_all_report_sections,
    capture_process_info,
    to_report_entry,
)
from .constants import (
    COMPANION_NAMES,
    SERVICE_NAMES,
    SERVICE_REGISTRY,
)
from .dialogs import NotificationDialog, ProcessReportDialog
from .process_ops import (
    get_pid_by_path,
    launch_detached,
    query_service_binary_path,
    query_service_pid,
    start_windows_service,
    terminate_process_tree,
)
from .refresh_snapshot import (
    RefreshBridge,
    SnapshotPayload,
    collect_refresh_snapshot,
)
from .uac import is_debug_session, is_running_as_admin, request_self_elevation

if TYPE_CHECKING:
    from .refresh_snapshot import RowSnapshot

PROCESS_CREATE_TIME_EPSILON = 0.001


@dataclass(slots=True)
class RefreshState:
    """Mutable state for the background refresh mechanism."""

    bridge: RefreshBridge
    in_flight: bool = False
    pending: bool = False
    closing: bool = False


class ActionsMixin:
    """Mixin providing process control, service management, and refresh methods."""

    if TYPE_CHECKING:
        @property
        def status_label(self) -> QLabel:
            """Hidden label for status text."""
            return QLabel()
        @property
        def status_badge(self) -> QLabel:
            """Visible running/stopped badge."""
            return QLabel()
        process_path: Path
        @property
        def _process_path_str(self) -> str:
            """Absolute path string for the target executable."""
            return ''
        _refresh: RefreshState
        @property
        def service_section(self) -> QWidget:
            """Section widget for system services."""
            return QWidget()
        @property
        def service_tree(self) -> QTreeWidget:
            """Tree widget for system services."""
            return QTreeWidget()

        def close(self) -> bool:
            """Close the main window."""
            return False
        def update_managed_section(
            self, processes: list[RowSnapshot],
        ) -> None:
            """Update the managed tree section."""
            del processes
        def update_companion_section(
            self, processes: list[RowSnapshot],
        ) -> None:
            """Update the companion tree section."""
            del processes
        def update_process_section(
            self,
            section: QWidget,
            tree: QTreeWidget,
            processes: list[RowSnapshot],
        ) -> None:
            """Update a process tree section."""
            del section, tree, processes

    # -- Process identity & verification -------------------------------

    def _is_same_process_still_running(
        self: ActionsMixin,
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

    def _format_process_label(self: ActionsMixin, pid: int) -> str:
        """Build a display label as '<name> (PID n)' with PID fallback."""
        process_label = f'PID {pid}'
        with contextlib.suppress(psutil.Error):
            process_label = f'{psutil.Process(pid).name()} (PID {pid})'
        return process_label

    def _capture_target_create_times(
        self: ActionsMixin, pids: set[int],
    ) -> dict[int, float | None]:
        """Capture best-effort create times for target process identity checks."""
        create_times: dict[int, float | None] = dict.fromkeys(pids)
        for pid in pids:
            with contextlib.suppress(psutil.Error):
                create_times[pid] = psutil.Process(pid).create_time()
        return create_times

    def _verified_denied_pids(
        self: ActionsMixin,
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
        self: ActionsMixin,
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

    # -- Process termination -------------------------------------------

    def _terminate_single_process(self: ActionsMixin, pid: int) -> None:
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

    def _stop_single_process(self: ActionsMixin, pid: int) -> None:
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

    # -- Dialogs & notifications ---------------------------------------

    def _popup(
        self: ActionsMixin, title: str, text: str, icon: QMessageBox.Icon,
    ) -> None:
        """Show a styled in-app modal dialog for status and report messages."""
        dialog = NotificationDialog(self, title, text, icon)  # type: ignore[arg-type]
        dialog.exec()

    def _offer_uac_elevation(self: ActionsMixin, *, reason: str) -> None:
        """Offer to relaunch this app with elevation when an action is denied."""
        if is_running_as_admin():
            self._popup(
                'Permissions required',
                f'{reason}\n\nThe app is already running as administrator.',
                QMessageBox.Icon.Warning,
            )
            return

        answer = QMessageBox.question(
            self,  # type: ignore[arg-type]
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
        self: ActionsMixin,
        status_text: str,
        dialog_title: str,
        icon: QMessageBox.Icon,
        sections: list[tuple[str, list[dict[str, str]]]],
    ) -> None:
        """Update the status bar and show a process-report dialog."""
        self.status_label.setText(status_text)
        self._show_process_report(dialog_title, icon, sections)

    def _show_process_report(
        self: ActionsMixin,
        title: str,
        icon: QMessageBox.Icon,
        sections: list[tuple[str, list[dict[str, str]]]],
    ) -> None:
        """Show a structured process report dialog."""
        dialog = ProcessReportDialog(self, title, icon, sections)  # type: ignore[arg-type]
        dialog.exec()

    # -- Report data collection ----------------------------------------

    def _wait_for_managed_process_start(
        self: ActionsMixin,
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
        self: ActionsMixin,
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
        self: ActionsMixin,
        pid: int | None = None,
    ) -> tuple[dict[int, str], dict[int, dict[str, str]]]:
        """Collect managed Radeon Software process-tree metadata for reporting."""
        target_categories: dict[int, str] = {}
        process_info: dict[int, dict[str, str]] = {}

        managed_pid = (
            get_pid_by_path(self.process_path)
            if pid is None
            else pid
        )
        if managed_pid is not None:
            self._collect_process_tree_targets_for_pid(
                managed_pid,
                'Managed',
                target_categories,
                process_info,
            )

        return target_categories, process_info

    def _build_report_sections_from_pid_groups(
        self: ActionsMixin,
        process_info: dict[int, dict[str, str]],
        section_pid_groups: list[tuple[str, list[int]]],
    ) -> list[tuple[str, list[dict[str, str]]]]:
        """Build structured report sections from ordered PID groups."""
        return [
            (section_title, [to_report_entry(process_info, pid) for pid in pids])
            for section_title, pids in section_pid_groups
        ]

    def _ensure_process_path_exists(self: ActionsMixin) -> bool:
        """Check process path exists, showing error popup if missing."""
        if self.process_path.exists():
            return True
        self.status_label.setText(
            'RadeonSoftware.exe path was not found.',
        )
        self._popup(
            'Path not found',
            f'Could not find executable at:\n{self.process_path}',
            QMessageBox.Icon.Critical,
        )
        return False

    # -- Software control actions --------------------------------------

    def restart_software(self: ActionsMixin) -> None:
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

    def start_only(self: ActionsMixin) -> None:
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

    def stop_only(self: ActionsMixin) -> None:
        """Terminate the running Radeon Software process tree."""
        pid = get_pid_by_path(self.process_path)
        if pid is None:
            self.status_label.setText(
                'RadeonSoftware.exe is not running.',
            )
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

    # -- Service management --------------------------------------------

    def start_services(self: ActionsMixin) -> None:
        """Start all registered AMD Windows services."""
        started, already, failed = self._attempt_service_starts()
        summary, title, icon, needs_elevation = (
            self._build_service_report(started, already, failed)
        )
        sections = self._build_service_sections(started, already, failed)
        self._report_and_notify(summary, title, icon, sections)
        if needs_elevation and not is_running_as_admin():
            self._offer_uac_elevation(
                reason='Some AMD services could not be started'
                ' without administrator privileges.',
            )

    @staticmethod
    def _build_service_entry(name: str, category: str) -> dict[str, str]:
        """Build a single service report entry with its binary path and PID."""
        path = query_service_binary_path(name) or '<unavailable>'
        pid = query_service_pid(name)
        return {
            'name': name,
            'pid': str(pid) if pid else '-',
            'category': category,
            'path': path,
        }

    def _build_service_sections(
        self: ActionsMixin,
        started: list[str],
        already: list[str],
        failed: list[tuple[str, str]],
    ) -> list[tuple[str, list[dict[str, str]]]]:
        """Convert service start results into report dialog sections."""
        sections: list[tuple[str, list[dict[str, str]]]] = []
        if started:
            sections.append(('Started', [
                self._build_service_entry(s, 'Service')
                for s in started
            ]))
        if already:
            sections.append(('Already Running', [
                self._build_service_entry(s, 'Service')
                for s in already
            ]))
        if failed:
            sections.append(('Failed', [
                self._build_service_entry(s, detail)
                for s, detail in failed
            ]))
        return sections

    @staticmethod
    def _attempt_service_starts() -> (
        tuple[list[str], list[str], list[tuple[str, str]]]
    ):
        """Iterate registered services and attempt to start each one."""
        started: list[str] = []
        already: list[str] = []
        failed: list[tuple[str, str]] = []
        for _exe, svc_name in sorted(SERVICE_REGISTRY.items()):
            ok, detail = start_windows_service(svc_name)
            if not ok:
                failed.append((svc_name, detail))
            elif detail == 'already running':
                already.append(svc_name)
            else:
                started.append(svc_name)
        return started, already, failed

    @staticmethod
    def _build_service_report(
        started: list[str],
        already: list[str],
        failed: list[tuple[str, str]],
    ) -> tuple[str, str, QMessageBox.Icon, bool]:
        """Format service report summary text, icon, and elevation flag."""
        lines: list[str] = []
        if started:
            lines.append(f'Started {len(started)} service(s):')
            lines.extend(f'  Ã¢â‚¬Â¢ {s}' for s in started)
        if already:
            lines.append(f'{len(already)} service(s) already running:')
            lines.extend(f'  Ã¢â‚¬Â¢ {s}' for s in already)
        if failed:
            lines.append(f'{len(failed)} service(s) failed:')
            for svc, detail in failed:
                lines.extend((f'  Ã¢â‚¬Â¢ {svc}', f'    {detail}'))
        summary = '\n'.join(lines) if lines else 'No services configured.'
        icon = QMessageBox.Icon.Information
        title = 'AMD Services'
        needs_elevation = False
        if failed:
            icon = QMessageBox.Icon.Warning
            title = 'AMD Services (partial)'
            needs_elevation = any('access' in d.lower() for _, d in failed)
        return summary, title, icon, needs_elevation

    # -- Refresh mechanism ---------------------------------------------

    def _set_monitor_badge(self: ActionsMixin, *, is_running: bool) -> None:
        """Update the monitor badge text and style based on running state."""
        new_name = 'badge_running' if is_running else 'badge_stopped'
        if self.status_badge.objectName() == new_name:
            return
        self.status_badge.setText(
            'Ã¢â€”Â RUNNING' if is_running else 'Ã¢â€”Â NOT RUNNING',
        )
        self.status_badge.setObjectName(new_name)
        self.status_badge.setStyle(
            self.status_badge.style(),
        )

    def _schedule_refresh(self: ActionsMixin) -> None:
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

    def _run_refresh_worker(self: ActionsMixin, process_path: str) -> None:
        """Collect a refresh snapshot in a worker thread."""
        try:
            snapshot = collect_refresh_snapshot(process_path)
        except (RuntimeError, ValueError, TypeError, psutil.Error, OSError) as exc:
            if self._refresh.closing:
                return
            self._refresh.bridge.emit_snapshot({'error': str(exc)})
            return

        if self._refresh.closing:
            return
        self._refresh.bridge.emit_snapshot(snapshot)

    def _apply_refresh_snapshot(
        self: ActionsMixin, snapshot: SnapshotPayload,
    ) -> None:
        """Apply worker-produced refresh data on the GUI thread."""
        self._refresh.in_flight = False

        if 'error' not in snapshot:
            self._set_monitor_badge(is_running=snapshot['is_running'])
            self.update_managed_section(snapshot['managed_rows'])
            self.update_companion_section(snapshot['companion_rows'])
            self.update_process_section(
                self.service_section,
                self.service_tree,
                snapshot['service_rows'],
            )

        if self._refresh.pending:
            self._refresh.pending = False
            self._schedule_refresh()

    def _refresh_process_info(self: ActionsMixin) -> None:
        """Request an asynchronous monitor refresh."""
        self._schedule_refresh()

    # -- Bulk stop all -------------------------------------------------

    def _collect_managed_targets(
        self: ActionsMixin,
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
        self: ActionsMixin,
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
        self: ActionsMixin,
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

    def stop_all(self: ActionsMixin) -> None:
        """Terminate Radeon Software plus monitored AMD processes."""
        target_categories: dict[int, str] = {}
        process_info: dict[int, dict[str, str]] = {}

        self._collect_managed_targets(target_categories, process_info)
        self._collect_companion_service_targets(target_categories, process_info)

        if not target_categories:
            self.status_label.setText(
                'No monitored AMD processes are running.',
            )
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
