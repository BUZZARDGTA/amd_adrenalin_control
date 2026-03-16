"""Background snapshot helpers for live process monitor refreshes."""

from pathlib import Path

import psutil
from PyQt6.QtCore import QObject, pyqtSignal

from .constants import COMPANION_NAMES, SERVICE_NAMES
from .process_ops import get_pid_by_path


class RefreshBridge(QObject):
    """Thread-safe signal bridge for refresh snapshots coming from worker threads."""

    snapshot_ready = pyqtSignal(object)


def build_row_snapshot(proc: psutil.Process, indent: int) -> dict[str, object]:
    """Build a plain-data row snapshot for a process."""
    try:
        prefix = "  └  " if indent > 0 else ""
        name = prefix + proc.name()
        pid_text = str(proc.pid)
        cpu_text = f"{proc.cpu_percent(interval=None):.1f} %"
        mem_mb = proc.memory_info().rss / (1024 * 1024)
        mem_text = f"{mem_mb:.1f} MB"
        status = str(proc.status())
        try:
            exe_path = proc.exe()
            path_text = exe_path or "Executable path unavailable"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            path_text = "Executable path unavailable"
        pid_value: int | None = proc.pid
    except psutil.NoSuchProcess:
        name, path_text, pid_text, cpu_text, mem_text, status = "<ended>", "<unavailable>", "-", "-", "-", "gone"
        pid_value = None

    return {
        "name": name,
        "path": path_text,
        "pid_text": pid_text,
        "cpu_text": cpu_text,
        "mem_text": mem_text,
        "status": status,
        "pid_value": pid_value,
        "indent": indent,
    }


def collect_running_processes() -> dict[int, psutil.Process]:
    """Collect running processes keyed by PID and warm up CPU counters."""
    all_procs: dict[int, psutil.Process] = {}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            all_procs[proc.pid] = proc
            proc.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return all_procs


def build_managed_rows(pid: int | None) -> tuple[list[tuple[psutil.Process, int]], set[int]]:
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


def split_companion_and_service_rows(
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


def collect_refresh_snapshot(process_path: str) -> dict[str, object]:
    """Collect all data needed to refresh monitor tables in a worker thread."""
    pid = get_pid_by_path(Path(process_path))

    all_procs = collect_running_processes()
    main_rows, managed_pids = build_managed_rows(pid)
    companion_rows, service_rows = split_companion_and_service_rows(all_procs, managed_pids)

    return {
        "is_running": bool(main_rows),
        "managed_rows": [build_row_snapshot(proc, indent) for proc, indent in main_rows],
        "companion_rows": [build_row_snapshot(proc, 0) for proc in companion_rows],
        "service_rows": [build_row_snapshot(proc, 0) for proc in service_rows],
    }
