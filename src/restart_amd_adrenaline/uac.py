"""Windows UAC helpers for on-demand elevation."""

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

_SHELL_EXECUTE_SUCCESS_MIN = 32


def is_running_as_admin() -> bool:
    """Return True when the current process has administrator privileges on Windows."""
    if os.name != "nt":
        return False

    try:
        token_handle = wintypes.HANDLE()
        token_query = 0x0008
        token_elevation_class = 20

        opened = ctypes.windll.advapi32.OpenProcessToken(
            ctypes.windll.kernel32.GetCurrentProcess(),
            token_query,
            ctypes.byref(token_handle),
        )
        if not opened:
            return False

        class TokenElevation(ctypes.Structure):  # pylint: disable=too-few-public-methods
            """Maps to the Windows TOKEN_ELEVATION struct."""

            _fields_ = [("TokenIsElevated", wintypes.DWORD)]

        elevation = TokenElevation()
        return_length = wintypes.DWORD(0)
        try:
            queried = ctypes.windll.advapi32.GetTokenInformation(
                token_handle,
                token_elevation_class,
                ctypes.byref(elevation),
                ctypes.sizeof(elevation),
                ctypes.byref(return_length),
            )
            if not queried:
                return False

            return bool(elevation.TokenIsElevated)
        finally:
            ctypes.windll.kernel32.CloseHandle(token_handle)
    except (OSError, AttributeError):
        return False


def request_self_elevation() -> bool:
    """Attempt to relaunch this Python process with a UAC elevation prompt on Windows."""
    if os.name != "nt":
        return False

    executable = _resolve_windows_python_executable()
    params = subprocess.list2cmdline(_build_elevated_argv())
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            params,
            str(Path.cwd()),
            1,
        )
    except (OSError, AttributeError):
        return False

    return result > _SHELL_EXECUTE_SUCCESS_MIN


def _build_elevated_argv() -> list[str]:
    """Build argv for elevated relaunch with a stable app entrypoint."""
    entry_script = _resolve_entry_script()
    if entry_script is not None:
        return [str(entry_script)]

    # Fallback: preserve the previous debugpy-aware behavior if entry script is not found.
    if "--" in sys.argv:
        split_idx = sys.argv.index("--")
        target_argv = sys.argv[split_idx + 1:]
        if target_argv:
            return target_argv

    if sys.argv:
        first = Path(sys.argv[0])
        if first.name.lower() == "launcher" and len(sys.argv) > 1:
            possible_script = Path(sys.argv[-1])
            if possible_script.suffix.lower() == ".py":
                return [str(possible_script)]

    return sys.argv


def _resolve_entry_script() -> Path | None:
    """Resolve the repository entrypoint script for elevated relaunch."""
    try:
        repo_root = Path(__file__).resolve().parents[2]
    except (OSError, IndexError):
        return None

    main_script = repo_root / "main.py"
    if main_script.exists():
        return main_script
    return None


def _resolve_windows_python_executable() -> str:
    """Prefer pythonw.exe on Windows to avoid opening an extra console window."""
    current = Path(sys.executable)
    pythonw = current.with_name("pythonw.exe")
    if pythonw.exists():
        return str(pythonw)
    return str(current)


def is_debug_session() -> bool:
    """Return True when running under an active debugger/debug launcher."""
    if sys.gettrace() is not None:
        return True

    lowered_argv = [arg.lower() for arg in sys.argv]
    return any("debugpy" in arg for arg in lowered_argv)
