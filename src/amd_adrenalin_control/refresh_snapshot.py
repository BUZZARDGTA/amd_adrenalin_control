"""Background snapshot helpers for live process monitor refreshes."""

import os

import psutil
from PyQt6.QtCore import QObject, pyqtSignal

from .constants import COMPANION_NAMES, SERVICE_NAMES


class RefreshBridge(QObject):
    """Thread-safe signal bridge for refresh snapshots coming from worker threads."""

    snapshot_ready = pyqtSignal(object)


def _safe_process_name_lower(proc: psutil.Process) -> str | None:
    """Return a process name in lowercase when available, otherwise None."""
    info_name = proc.info.get('name')
    if isinstance(info_name, str):
        return info_name.lower()

    try:
        return proc.name().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def build_row_snapshot(proc: psutil.Process, indent: int) -> dict[str, object]:
    """Build a plain-data row snapshot for a process."""
    try:
        with proc.oneshot():
            name = proc.name()
            pid_text = str(proc.pid)
            cpu_text = f'{proc.cpu_percent(interval=None):.1f} %'
            mem_mb = proc.memory_info().rss / (1024 * 1024)
            mem_text = f'{mem_mb:.1f} MB'
            status = str(proc.status())
            try:
                exe_path = proc.exe()
                path_text = exe_path or 'Executable path unavailable'
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                path_text = 'Executable path unavailable'
            pid_value: int | None = proc.pid
    except psutil.NoSuchProcess:
        name, path_text, pid_text, cpu_text, mem_text, status = (
            '<ended>', '<unavailable>', '-', '-', '-', 'gone',
        )
        pid_value = None
    except psutil.AccessDenied:
        name, path_text, pid_text, cpu_text, mem_text, status = (
            '<restricted>',
            'Executable path unavailable',
            str(proc.pid),
            '-',
            '-',
            'restricted',
        )
        pid_value = proc.pid

    return {
        'name': name,
        'path': path_text,
        'pid_text': pid_text,
        'cpu_text': cpu_text,
        'mem_text': mem_text,
        'status': status,
        'pid_value': pid_value,
        'indent': indent,
    }


def collect_running_processes() -> dict[int, psutil.Process]:
    """Collect running processes keyed by PID and warm up CPU counters."""
    all_procs: dict[int, psutil.Process] = {}
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            all_procs[proc.pid] = proc
            proc.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return all_procs


def _find_pid_by_path(
    all_procs: dict[int, psutil.Process],
    target: str,
) -> int | None:
    """Return the PID matching target exe path from an already-collected dict."""
    norm_target = os.path.normcase(target)
    for proc in all_procs.values():
        exe = proc.info.get('exe')
        if exe and os.path.normcase(exe) == norm_target:
            return proc.pid
    return None


def _walk_process_tree(
    proc: psutil.Process,
    depth: int,
) -> list[tuple[psutil.Process, int]]:
    """Recursively walk a process tree returning (process, depth) pairs."""
    result: list[tuple[psutil.Process, int]] = [(proc, depth)]
    try:
        children = proc.children(recursive=False)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return result
    for child in children:
        result.extend(_walk_process_tree(child, depth + 1))
    return result


def build_managed_rows(
    pid: int | None,
) -> tuple[list[tuple[psutil.Process, int]], set[int]]:
    """Build rows for the main managed process and its descendants."""
    if pid is None:
        return [], set()

    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return [], set()

    main_rows = _walk_process_tree(parent, 0)
    managed_pids = {proc.pid for proc, _ in main_rows}
    return main_rows, managed_pids


def split_companion_and_service_rows(
    all_procs: dict[int, psutil.Process],
    managed_pids: set[int],
) -> tuple[list[psutil.Process], list[psutil.Process]]:
    """Return companion and service process lists excluding managed rows."""
    companion_rows: list[tuple[psutil.Process, str]] = []
    service_rows: list[tuple[psutil.Process, str]] = []

    for proc in all_procs.values():
        if proc.pid in managed_pids:
            continue

        name_lower = _safe_process_name_lower(proc)
        if name_lower is None:
            continue

        if name_lower in COMPANION_NAMES:
            companion_rows.append((proc, name_lower))
        elif name_lower in SERVICE_NAMES:
            service_rows.append((proc, name_lower))

    companion_rows.sort(key=lambda pair: pair[1])
    service_rows.sort(key=lambda pair: pair[1])
    return (
        [proc for proc, _ in companion_rows],
        [proc for proc, _ in service_rows],
    )


def collect_refresh_snapshot(process_path: str) -> dict[str, object]:
    """Collect all data needed to refresh monitor tables in a worker thread."""
    all_procs = collect_running_processes()
    pid = _find_pid_by_path(all_procs, process_path)
    main_rows, managed_pids = build_managed_rows(pid)
    companion_rows, service_rows = (
        split_companion_and_service_rows(
            all_procs, managed_pids,
        )
    )

    return {
        'is_running': bool(main_rows),
        'managed_rows': [
            build_row_snapshot(proc, indent)
            for proc, indent in main_rows
        ],
        'companion_rows': [
            build_row_snapshot(proc, 0)
            for proc in companion_rows
        ],
        'service_rows': [
            build_row_snapshot(proc, 0)
            for proc in service_rows
        ],
    }
