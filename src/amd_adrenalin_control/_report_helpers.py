"""Process reporting helpers for AMD Adrenalin Control."""

import contextlib
from collections.abc import Callable

import psutil


def _safe_process_get(
    proc: psutil.Process,
    getter: Callable[[psutil.Process], str],
    default: str,
) -> str:
    """Return getter(proc) or default when process info is unavailable."""
    with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
        return getter(proc)
    return default


def _parent_display_text(proc: psutil.Process) -> str:
    """Build parent display text in the form '<name> (PID n)' when available."""
    with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
        parent_proc = proc.parent()
        if parent_proc is None:
            return 'None'
        parent_name = _safe_process_get(
            parent_proc,
            lambda item: item.name(),
            '<unknown>',
        )
        return f'{parent_name} (PID {parent_proc.pid})'
    return '<unknown>'


def capture_process_info(
    process_info: dict[int, dict[str, str]],
    pid: int,
    category: str,
) -> None:
    """Capture best-effort process metadata for reporting."""
    existing = process_info.get(pid)
    if existing is not None:
        if existing.get('category') == 'Unknown' and category != 'Unknown':
            existing['category'] = category
        return

    name = '<unknown>'
    parent_text = '<unknown>'
    path_text = '<unavailable>'
    try:
        proc = psutil.Process(pid)
        name = _safe_process_get(proc, lambda item: item.name(), '<unknown>')
        parent_text = _parent_display_text(proc)
        path_text = _safe_process_get(
            proc,
            lambda item: item.exe() or '<unavailable>',
            '<unavailable>',
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    process_info[pid] = {
        'name': name,
        'category': category,
        'parent': parent_text,
        'path': path_text,
    }


def to_report_entry(
    process_info: dict[int, dict[str, str]],
    pid: int,
) -> dict[str, str]:
    """Build a single report row for a PID from captured process metadata."""
    info = process_info.get(
        pid,
        {
            'name': '<unknown>',
            'category': 'Unknown',
            'parent': '<unknown>',
            'path': '<unavailable>',
        },
    )
    return {
        'name': info['name'],
        'pid': str(pid),
        'category': info['category'],
        'parent': info['parent'],
        'path': info['path'],
    }


def build_stop_all_report_sections(
    process_info: dict[int, dict[str, str]],
    stopped_pids_total: set[int],
    denied_pids_total: set[int],
) -> list[tuple[str, list[dict[str, str]]]]:
    """Build grouped report sections for stop-all results."""
    attempted_pids = set(process_info)
    category_order: dict[str, int] = {
        'Managed': 0,
        'Companion': 1,
        'Service': 2,
        'Unknown': 3,
    }

    def report_sort_key(pid: int) -> tuple[int, int]:
        info = process_info.get(pid)
        category = info['category'] if info is not None else 'Unknown'
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
        (pid for pid in attempted_pids
            if pid not in stopped_pids_total
            and pid not in denied_pids_total),
        key=report_sort_key,
    )

    return [
        ('Closed', [
            to_report_entry(process_info, pid)
            for pid in stopped_known
        ]),
        (
            'Could not close (permissions)',
            [to_report_entry(process_info, pid) for pid in denied_known],
        ),
        (
            'Already gone / ended during action',
            [to_report_entry(process_info, pid) for pid in gone_known],
        ),
    ]
