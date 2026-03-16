"""Process management operations for AMD Adrenalin control."""
import subprocess
from pathlib import Path

import psutil


def get_pid_by_path(filepath: Path) -> int | None:
    """Return the PID of the running process whose executable matches filepath, or None."""
    for process in psutil.process_iter(["pid", "exe"]):
        if process.info["exe"] == str(filepath.absolute()):
            return process.pid
    return None


def _terminate_process(proc: psutil.Process, stopped_pids: set[int], denied_pids: set[int]) -> str:
    """Terminate a process and track outcome as 'ok', 'gone', or 'denied'."""
    try:
        proc.terminate()
        stopped_pids.add(proc.pid)
    except psutil.NoSuchProcess:
        return "gone"
    except psutil.AccessDenied:
        denied_pids.add(proc.pid)
        return "denied"
    else:
        return "ok"


def _kill_process(proc: psutil.Process, stopped_pids: set[int], denied_pids: set[int]) -> None:
    """Force-kill a process and track stopped/denied results."""
    try:
        proc.kill()
        stopped_pids.add(proc.pid)
    except psutil.NoSuchProcess:
        return
    except psutil.AccessDenied:
        denied_pids.add(proc.pid)


def _collect_alive_after_wait(children: list[psutil.Process], denied_pids: set[int]) -> list[psutil.Process]:
    """Wait briefly for children to exit and return those still alive."""
    alive_children: list[psutil.Process] = []
    for child in children:
        try:
            child.wait(timeout=3)
        except psutil.TimeoutExpired:
            alive_children.append(child)
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            denied_pids.add(child.pid)
    return alive_children


def _get_process_or_none(pid: int, denied_pids: set[int]) -> psutil.Process | None:
    """Return Process for pid when accessible, otherwise None and track denied pid."""
    try:
        return psutil.Process(pid)
    except psutil.NoSuchProcess:
        return None
    except psutil.AccessDenied:
        denied_pids.add(pid)
        return None


def _get_children_or_empty(parent: psutil.Process, denied_pids: set[int]) -> list[psutil.Process]:
    """Return recursive children or an empty list if inaccessible."""
    try:
        return parent.children(recursive=True)
    except psutil.NoSuchProcess:
        return []
    except psutil.AccessDenied:
        denied_pids.add(parent.pid)
        return []


def _wait_or_kill_parent(parent: psutil.Process, stopped_pids: set[int], denied_pids: set[int]) -> None:
    """Wait for parent to exit, then force-kill if timeout is reached."""
    try:
        parent.wait(3)
    except psutil.TimeoutExpired:
        _kill_process(parent, stopped_pids, denied_pids)
    except psutil.NoSuchProcess:
        return
    except psutil.AccessDenied:
        denied_pids.add(parent.pid)


def terminate_process_tree(pid: int) -> tuple[set[int], set[int]]:
    """Attempt to terminate pid and its children; return (stopped_pids, denied_pids)."""
    stopped_pids: set[int] = set()
    denied_pids: set[int] = set()

    parent = _get_process_or_none(pid, denied_pids)
    if parent is None:
        return stopped_pids, denied_pids

    children = _get_children_or_empty(parent, denied_pids)

    for child in children:
        _terminate_process(child, stopped_pids, denied_pids)

    alive_children = _collect_alive_after_wait(children, denied_pids)
    for child in alive_children:
        _kill_process(child, stopped_pids, denied_pids)

    parent_state = _terminate_process(parent, stopped_pids, denied_pids)
    if parent_state in {"gone", "denied"}:
        return stopped_pids, denied_pids

    _wait_or_kill_parent(parent, stopped_pids, denied_pids)

    return stopped_pids, denied_pids


def launch_detached(filepath: Path) -> None:
    """Launch the target executable detached from this Python process on Windows."""
    executable = filepath.resolve(strict=True)
    if executable.suffix.lower() != ".exe":
        msg = f"Expected an .exe path, got: {executable}"
        raise ValueError(msg)

    creation_flags = 0
    creation_flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    creation_flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    creation_flags |= getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)

    subprocess.Popen(  # noqa: S603
        [str(executable)],
        close_fds=True,
        creationflags=creation_flags,
    )
