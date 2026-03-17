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

STATUS_COLORS: dict[str, str] = {
    "running": "#22c55e",
    "sleeping": "#60a5fa",
    "stopped": "#f97316",
    "zombie": "#ef4444",
}
