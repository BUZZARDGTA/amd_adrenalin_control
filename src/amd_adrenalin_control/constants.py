"""Application constants for AMD Adrenalin process control and monitoring."""
from pathlib import Path

RADEON_SOFTWARE_PATH = Path("C:/Program Files/AMD/CNext/CNext/RadeonSoftware.exe")

COMPANION_NAMES: frozenset[str] = frozenset({
    "amdadlxserv.exe",
    "cpumetricsserver.exe",
    "amd3dvcacheuser.exe",
})

SERVICE_NAMES: frozenset[str] = frozenset({
    "atiesrxx.exe",
    "atieclxx.exe",
    "amdfendrsr.exe",
    "amd3dvcachesvc.exe",
    "amdppkgsvc.exe",
})

PROCESS_TOOLTIPS: dict[str, str] = {
    "radeonsoftware.exe": "AMD application - GPU control, overlay, tuning, and features (Adrenalin).",
    "cncmd.exe": "AMD utility - command-line control for Radeon settings and features (CNext).",
    "amdadlxserv.exe": "AMD service - GPU monitoring and feature access (ADLX).",
    "amd3dvcacheuser.exe": "AMD helper - 3D V-Cache thread scheduling for games (Ryzen X3D).",
    "cpumetricsserver.exe": "AMD service - CPU metrics collection for performance monitoring (CNext).",
    "amd3dvcachesvc.exe": "AMD service - 3D V-Cache scheduling support (Ryzen X3D).",
    "amdfendrsr.exe": "AMD service - GPU driver crash detection and recovery (Crash Defender).",
    "amdppkgsvc.exe": "AMD service - driver configuration and component provisioning.",
    "atieclxx.exe": "AMD client - display events, hotkeys, and driver notifications.",
    "atiesrxx.exe": "AMD service - background display event handling and driver actions.",
}

STATUS_COLORS: dict[str, str] = {
    "running": "#22c55e",
    "sleeping": "#60a5fa",
    "stopped": "#f97316",
    "zombie": "#ef4444",
}
