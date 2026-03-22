"""Process management operations for AMD Adrenalin control."""
import contextlib
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
import psutil
import pywintypes
import win32service
import win32serviceutil
import winerror

from .constants import (
    SIGNAL_DENIED,
    SIGNAL_GONE,
    SIGNAL_OK,
    SVC_DETAIL_ACCESS_DENIED,
    SVC_DETAIL_ALREADY_RUNNING,
    SVC_DETAIL_ALREADY_STOPPED,
    SVC_DETAIL_START_PENDING,
    SVC_DETAIL_STARTED,
    SVC_DETAIL_STOP_PENDING,
    SVC_DETAIL_STOPPED,
)

_DETACHED_CREATION_FLAGS: int = (
    getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    | getattr(subprocess, 'DETACHED_PROCESS', 0)
    | getattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB', 0)
)


def get_pid_by_path(filepath: Path) -> int | None:
    """Return the PID of the process matching filepath, or None."""
    target = os.path.normcase(str(filepath.absolute()))
    for process in psutil.process_iter(['pid', 'exe']):
        try:
            exe = process.info.get('exe')
            if exe and os.path.normcase(exe) == target:
                return process.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def _signal_process(
    proc: psutil.Process,
    signal_name: str,
    stopped_pids: set[int],
    denied_pids: set[int],
) -> str:
    """Send a terminate/kill signal and track outcome."""
    try:
        getattr(proc, signal_name)()
        stopped_pids.add(proc.pid)
    except psutil.NoSuchProcess:
        return SIGNAL_GONE
    except psutil.AccessDenied:
        denied_pids.add(proc.pid)
        return SIGNAL_DENIED
    return SIGNAL_OK


def _terminate_process(
    proc: psutil.Process,
    stopped_pids: set[int],
    denied_pids: set[int],
) -> str:
    """Terminate a process and track outcome."""
    return _signal_process(proc, 'terminate', stopped_pids, denied_pids)


def _kill_process(
    proc: psutil.Process,
    stopped_pids: set[int],
    denied_pids: set[int],
) -> None:
    """Force-kill a process and track stopped/denied results."""
    _signal_process(proc, 'kill', stopped_pids, denied_pids)


def _collect_alive_after_wait(
    children: list[psutil.Process],
    denied_pids: set[int],
) -> list[psutil.Process]:
    """Wait briefly for children to exit and return those still alive."""
    try:
        _, alive = psutil.wait_procs(children, timeout=3)
    except psutil.AccessDenied:
        # On Windows, wait_procs can raise AccessDenied for protected
        # child processes.  Fall back to checking each child individually.
        alive: list[psutil.Process] = []
        for child in children:
            try:
                child.wait(timeout=0)
            except psutil.TimeoutExpired:
                alive.append(child)
            except psutil.AccessDenied:
                denied_pids.add(child.pid)
                alive.append(child)
            except psutil.NoSuchProcess:
                pass
    return list(alive)


def _get_process_or_none(pid: int, denied_pids: set[int]) -> psutil.Process | None:
    """Return Process for pid when accessible, otherwise None and track denied pid."""
    try:
        return psutil.Process(pid)
    except psutil.NoSuchProcess:
        return None
    except psutil.AccessDenied:
        denied_pids.add(pid)
        return None


def _get_children_or_empty(
    parent: psutil.Process,
    denied_pids: set[int],
) -> list[psutil.Process]:
    """Return recursive children or an empty list if inaccessible."""
    try:
        return parent.children(recursive=True)
    except psutil.NoSuchProcess:
        return []
    except psutil.AccessDenied:
        denied_pids.add(parent.pid)
        return []


def _wait_or_kill_parent(
    parent: psutil.Process,
    stopped_pids: set[int],
    denied_pids: set[int],
) -> None:
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
    if parent_state in {SIGNAL_GONE, SIGNAL_DENIED}:
        return stopped_pids, denied_pids

    _wait_or_kill_parent(parent, stopped_pids, denied_pids)

    return stopped_pids, denied_pids


def launch_detached(filepath: Path) -> None:
    """Launch the target executable detached from this Python process on Windows."""
    executable = filepath.resolve(strict=True)
    if executable.suffix.lower() != '.exe':
        msg = f'Expected an .exe path, got: {executable}'
        raise ValueError(msg)

    subprocess.Popen(  # noqa: S603  # pylint: disable=consider-using-with
        [str(executable)],
        close_fds=True,
        creationflags=_DETACHED_CREATION_FLAGS,
    )


def _wait_for_service_status(
    service_name: str,
    target_status: int,
    timeout: float = 10.0,
) -> bool:
    """Poll until the service reaches target_status or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            raw_status: object = win32serviceutil.QueryServiceStatus(service_name)[1]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]  # pylint: disable=line-too-long
        except pywintypes.error:
            return False
        if not isinstance(raw_status, int):
            return False
        if raw_status == target_status:
            return True
        time.sleep(0.3)
    return False


def query_service_status(service_name: str) -> int | None:
    """Return the current win32service status constant, or None on error."""
    try:
        raw_status: object = win32serviceutil.QueryServiceStatus(service_name)[1]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]  # pylint: disable=line-too-long
    except pywintypes.error:
        return None
    return raw_status if isinstance(raw_status, int) else None


@contextlib.contextmanager
def _open_service(
    service_name: str,
    access: int,
) -> Iterator[object]:
    """Context manager for Win32 service handles with automatic cleanup."""
    hscm = win32service.OpenSCManager(
        None, None, win32service.SC_MANAGER_CONNECT,
    )
    try:
        hs = win32service.OpenService(  # pyright: ignore[reportUnknownMemberType]
            hscm, service_name, access,
        )
        try:
            yield hs
        finally:
            win32service.CloseServiceHandle(hs)
    finally:
        win32service.CloseServiceHandle(hscm)


def query_service_pid(service_name: str) -> int | None:
    """Return the PID of a running Windows service, or None on error/stopped."""
    try:
        with _open_service(service_name, win32service.SERVICE_QUERY_STATUS) as hs:
            info: object = win32service.QueryServiceStatusEx(hs)  # pyright: ignore[reportArgumentType, reportUnknownVariableType]  # pylint: disable=line-too-long
            if not isinstance(info, dict):
                return None
            pid: object = info.get('ProcessId', 0)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]  # pylint: disable=line-too-long
            if not isinstance(pid, int):
                return None
            return pid or None  # PID 0 means no dedicated process
    except pywintypes.error:
        return None


def query_service_binary_path(service_name: str) -> str | None:
    """Return the binary path of a Windows service, or None on error."""
    try:
        with _open_service(service_name, win32service.SERVICE_QUERY_CONFIG) as hs:
            config: object = win32service.QueryServiceConfig(hs)  # pyright: ignore[reportArgumentType, reportUnknownMemberType, reportUnknownVariableType]  # pylint: disable=line-too-long
            if not isinstance(config, tuple) or len(config) < 4:  # pyright: ignore[reportUnknownArgumentType]  # pylint: disable=line-too-long
                return None
            path: object = config[3]  # lpBinaryPathName  # pyright: ignore[reportUnknownVariableType]  # pylint: disable=line-too-long
            return path if isinstance(path, str) else None
    except pywintypes.error:
        return None


def start_windows_service(
    service_name: str,
) -> tuple[bool, str]:
    """Start a Windows service via Win32 API; return (success, detail)."""
    try:
        win32serviceutil.StartService(service_name)  # pyright: ignore[reportUnknownMemberType]
    except pywintypes.error as exc:
        if exc.winerror == winerror.ERROR_SERVICE_ALREADY_RUNNING:
            return True, SVC_DETAIL_ALREADY_RUNNING
        if exc.winerror == winerror.ERROR_ACCESS_DENIED:
            return False, SVC_DETAIL_ACCESS_DENIED
        return False, exc.strerror
    reached = _wait_for_service_status(
        service_name, win32service.SERVICE_RUNNING,
    )
    if reached:
        return True, SVC_DETAIL_STARTED
    return True, SVC_DETAIL_START_PENDING


def stop_windows_service(
    service_name: str,
) -> tuple[bool, str]:
    """Stop a Windows service via Win32 API; return (success, detail)."""
    try:
        win32serviceutil.StopService(service_name)  # pyright: ignore[reportUnknownMemberType]
    except pywintypes.error as exc:
        if exc.winerror == winerror.ERROR_SERVICE_NOT_ACTIVE:
            return True, SVC_DETAIL_ALREADY_STOPPED
        if exc.winerror == winerror.ERROR_ACCESS_DENIED:
            return False, SVC_DETAIL_ACCESS_DENIED
        return False, exc.strerror
    reached = _wait_for_service_status(
        service_name, win32service.SERVICE_STOPPED,
    )
    if reached:
        return True, SVC_DETAIL_STOPPED
    return True, SVC_DETAIL_STOP_PENDING
