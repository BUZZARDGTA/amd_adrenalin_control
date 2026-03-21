# Project Guidelines

## Overview
This repository is a Windows-only PyQt6 desktop utility for controlling and monitoring AMD Adrenalin processes. The entrypoint is `main.py`, and primary application logic lives under `src/amd_adrenalin_control/`.

## Architecture
- Keep `main.py` as a thin startup wrapper (`QApplication` setup + `MainWindow` launch).
- Put UI orchestration in `src/amd_adrenalin_control/main_window.py`.
- Keep process lifecycle logic in `src/amd_adrenalin_control/process_ops.py`.
- Keep refresh/snapshot collection and thread-safe signal bridging in `src/amd_adrenalin_control/refresh_snapshot.py`.
- Keep Windows elevation/privilege checks in `src/amd_adrenalin_control/uac.py`.
- Keep structured report generation in `src/amd_adrenalin_control/_report_helpers.py` and user-facing dialogs in `src/amd_adrenalin_control/dialogs.py`.
- Keep style/theme constants in `src/amd_adrenalin_control/_stylesheet.py` and domain constants in `src/amd_adrenalin_control/constants.py`.
- Keep UI selection/copy utilities and runtime type helpers in `src/amd_adrenalin_control/ui_helpers.py`.

## Build And Run
- Create venv: `python -m venv .venv`
- Activate (PowerShell): `.venv\\Scripts\\Activate.ps1`
- Install deps (editable): `pip install -e .`
- Run app: `python main.py` (or equivalently: `amd-adrenalin-control`)

## Testing And Validation
- No automated test suite is currently configured.
- For behavior changes, validate manually by launching the app and exercising affected UI flows.
- If available in VS Code, prefer running the workspace task `Run AMD Adrenalin Control` to verify startup.

## Conventions
- Preserve existing module boundaries and avoid cross-cutting refactors unless requested.
- Use explicit type hints consistently (`str | None`, `list[str]`, `dict[int, ...]`).
- Keep constants centralized; avoid scattering duplicated process names, paths, or style values.
- Keep psutil interactions defensive: handle `NoSuchProcess` and `AccessDenied` gracefully.
- Keep termination behavior graceful-first (`terminate` + wait) with kill fallback for stubborn descendants.
- For Qt tree widget hover behavior, ensure mouse tracking remains enabled on both the tree and its viewport when hover styling is involved.
- For stop/failure reporting, prefer confirming PID identity (`pid` + `create_time`) before showing persistent failure/elevation guidance.

## Platform Constraints
- Target platform is Windows 10/11 only.
- Assume AMD Adrenalin executable path defaults to `C:/Program Files/AMD/CNext/CNext/RadeonSoftware.exe`.
- Keep Windows-specific APIs explicit (`ctypes.windll`, UAC relaunch, Windows subprocess creation flags).
- Python requirement is `>=3.13` (from `pyproject.toml`); do not introduce features requiring older runtimes.

## Editing Expectations
- Keep diffs minimal and focused on the task.
- Do not reformat unrelated sections of files.
- Preserve existing public behavior unless the change request explicitly modifies it.
- Follow lint settings in `pyproject.toml` / `.flake8`; do not “fix” unrelated linter issues during targeted edits.

## Key References
- `README.md` for setup and feature overview.
- `src/amd_adrenalin_control/main_window.py` for UI composition and refresh cadence.
- `src/amd_adrenalin_control/process_ops.py` for process start/stop strategy.
- `src/amd_adrenalin_control/uac.py` for elevation flow.
