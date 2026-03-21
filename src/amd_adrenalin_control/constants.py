"""Application constants for AMD Adrenalin process control and monitoring."""
import os
from pathlib import Path

RADEON_SOFTWARE_PATH = (
    Path(os.environ.get('PROGRAMFILES', 'C:/Program Files'))
    / 'AMD/CNext/CNext/RadeonSoftware.exe'
)

COMPANION_NAMES: frozenset[str] = frozenset({
    'amdadlxserv.exe',
    'amdow.exe',
    'amdrsserv.exe',
    'amdrssrcext.exe',
    'atieclxx.exe',
    'cpumetricsserver.exe',
    'amd3dvcacheuser.exe',
})

SERVICE_NAMES: frozenset[str] = frozenset({
    'atiesrxx.exe',
    'amdfendrsr.exe',
    'amd3dvcachesvc.exe',
    'amdppkgsvc.exe',
})

# Maps service executable names to their Windows service names.
SERVICE_REGISTRY: dict[str, str] = {
    'atiesrxx.exe': 'AMD External Events Utility',
    'amdfendrsr.exe': 'AMD Crash Defender Service',
    'amd3dvcachesvc.exe': 'amd3dvcacheSvc',
    'amdppkgsvc.exe': 'AmdPpkgSvc',
}

PROCESS_TOOLTIPS: dict[str, str] = {
    # pylint: disable=line-too-long
    # --- Main Adrenalin application ---
    'radeonsoftware.exe': 'AMD application - GPU control, overlay, tuning, and features (Adrenalin).',  # noqa: E501
    'cncmd.exe': 'AMD utility - command-line control for Radeon settings and features (CNext).',  # noqa: E501
    'splashwindow.exe': 'AMD helper - Adrenalin splash screen shown during startup.',
    # --- Companion / helper processes ---
    'amdadlxserv.exe': 'AMD service - GPU monitoring and feature access (ADLX).',
    'amd3dvcacheuser.exe': 'AMD helper - 3D V-Cache thread scheduling for games (Ryzen X3D).',  # noqa: E501
    'cpumetricsserver.exe': 'AMD service - CPU metrics collection for performance monitoring (CNext).',  # noqa: E501
    # --- System services ---
    'amd3dvcachesvc.exe': 'AMD service - 3D V-Cache scheduling support (Ryzen X3D).',
    'amdfendrsr.exe': 'AMD service - GPU driver crash detection and recovery (Crash Defender).',  # noqa: E501
    'amdppkgsvc.exe': 'AMD service - driver configuration and component provisioning.',
    'atieclxx.exe': 'AMD client - display events, hotkeys, and driver notifications.',
    'atiesrxx.exe': 'AMD service - background display event handling and driver actions.',  # noqa: E501
    # --- CNext helper executables ---
    'amdaiinferencing.exe': 'AMD helper - local AI inferencing engine for Adrenalin features.',  # noqa: E501
    'amddmlfilters.exe': 'AMD helper - DirectML-based video/image filters.',
    'amdidentifywindow.exe': 'AMD helper - on-screen display identifier for multi-monitor setups.',  # noqa: E501
    'amdimagelocalizer.exe': 'AMD helper - locale image resource loader for the Adrenalin UI.',  # noqa: E501
    'amdocapp.exe': 'AMD utility - GPU overclocking and tuning interface.',
    'amdow.exe': 'AMD helper - overlay window host for Radeon metrics display.',
    'amdrsserv.exe': 'AMD service - Radeon Software background service for features and updates.',  # noqa: E501
    'amdrssrcext.exe': 'AMD helper - Radeon Software source extension handler.',
    'compressionutility.exe': 'AMD utility - file compression helper for Adrenalin data.',  # noqa: E501
    'duplicatedesktop.exe': 'AMD helper - desktop duplication for streaming and recording capture.',  # noqa: E501
    'eyefinitypro.exe': 'AMD utility - Eyefinity multi-display configuration tool.',
    'giphywrapper.exe': 'AMD helper - Giphy integration for Adrenalin instant replay/GIF creation.',  # noqa: E501
    'launcherrsxruntime.exe': 'AMD helper - RSX runtime launcher for Radeon features.',
    'mmloaddrv.exe': 'AMD helper - multimedia driver loader for Radeon video encoding.',
    'mmloaddrvpxdiscrete.exe': 'AMD helper - multimedia driver loader for discrete GPU configurations.',  # noqa: E501
    'presentmon-x64.exe': 'AMD utility - frame-time and present-mode monitor (PresentMon).',  # noqa: E501
    'qtwebengineprocess.exe': 'AMD helper - Chromium web-engine renderer for Adrenalin UI panels.',  # noqa: E501
    'restreamapiwrapper.exe': 'AMD helper - Restream integration for multi-platform live streaming.',  # noqa: E501
    'rsservcmd.exe': 'AMD utility - Radeon Software service command-line interface.',
    'sinawelbowrapper.exe': 'AMD helper - Sina Weibo social integration for clip sharing.',  # noqa: E501
    'streamableapiwrapper.exe': 'AMD helper - Streamable integration for video upload.',
    'twitchclient.exe': 'AMD helper - Twitch integration for live streaming.',
    'twitterwrapperclient.exe': 'AMD helper - Twitter/X integration for clip sharing.',
    'videotrim.exe': 'AMD utility - video trimming tool for recorded clips.',
    'youtubeapiwrapper.exe': 'AMD helper - YouTube integration for video upload.',
    'ziputility.exe': 'AMD utility - archive/zip helper for Adrenalin data.',
    # --- Installer / CIM executables ---
    '7z.exe': 'Archive utility - 7-Zip extraction engine used by AMD installers.',
    'amdcleanupUtility.exe': 'AMD utility - driver and software removal/cleanup tool.',
    'amdinstallmanager.exe': 'AMD installer - manages driver download and installation.',  # noqa: E501
    'amdinstalluep.exe': 'AMD installer - user experience program enrollment during setup.',  # noqa: E501
    'amdsoftwarecompatibilitytool.exe': 'AMD installer - hardware/software compatibility checker.',  # noqa: E501
    'amdsoftwareinstaller.exe': 'AMD installer - main driver/software installation wizard.',  # noqa: E501
    'amdsplashscreen.exe': 'AMD installer - splash screen shown during driver installation.',  # noqa: E501
    'atisetup.exe': 'AMD installer - legacy ATI/AMD driver setup launcher.',
    'installmanagerapp.exe': 'AMD installer - Install Manager GUI application.',
    'setup.exe': 'AMD installer - driver package setup bootstrapper.',
    # --- Ryzen Master executables ---
    'amdryzenmaster.exe': 'AMD utility - CPU overclocking, monitoring, and tuning (Ryzen Master).',  # noqa: E501
    'amdbugreporttool.exe': 'AMD utility - bug report collector for Ryzen Master.',
    'amdryzenmastercli.exe': 'AMD utility - Ryzen Master command-line interface.',
    'rmcleanup.exe': 'AMD utility - Ryzen Master uninstall/cleanup helper.',
    'stress.exe': 'AMD utility - CPU stress test bundled with Ryzen Master.',
    'vc_redist.x64.exe': 'Microsoft runtime - Visual C++ redistributable required by Ryzen Master.',  # noqa: E501
    # --- Windows system processes spawned by AMD executables ---
    'cmd.exe': 'Windows system - Command Processor spawned as an AMD process launcher.',
    'conhost.exe': 'Windows system - Console Window Host spawned by an AMD console process.',  # noqa: E501
    'powershell.exe': 'Windows system - PowerShell instance spawned by an AMD process.',
    # pylint: enable=line-too-long
}

STATUS_COLORS: dict[str, str] = {
    'running': '#22c55e',
    'sleeping': '#60a5fa',
    'stopped': '#f97316',
    'zombie': '#ef4444',
}
