# AMD Adrenalin Control

PyQt6 desktop utility for Windows to control AMD Adrenalin and monitor related AMD processes.

## Preview

<img width="1132" height="857" alt="amd-adrenalin-control_2026-03-20_07-37" src="https://github.com/user-attachments/assets/448d681c-2210-41f4-be63-bd109c2c9670" />

## Features

- Start AMD Adrenalin
- Restart AMD Adrenalin
- Stop AMD Adrenalin process tree
- Stop all monitored AMD processes (managed, companion, service)
- Live process monitor split into categorized tables
- Detailed, structured action reports for stop operations

## Requirements

- Windows 10/11
- Python 3.13+
- AMD Adrenalin installed at:
  - `C:/Program Files/AMD/CNext/CNext/RadeonSoftware.exe`

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Optional: install as a script

This project defines a script entrypoint in `pyproject.toml`:

```bash
pip install .
amd-adrenalin-control
```

## Project layout

- `main.py`: Thin application entrypoint
- `src/amd_adrenalin_control/main_window.py`: Main PyQt window and app interactions
- `src/amd_adrenalin_control/dialogs.py`: Custom notification and report dialogs
- `src/amd_adrenalin_control/process_ops.py`: Process start/stop/terminate operations
- `src/amd_adrenalin_control/refresh_snapshot.py`: Background snapshot helpers for live process monitor refreshes
- `src/amd_adrenalin_control/uac.py`: Windows UAC helpers for on-demand elevation
- `src/amd_adrenalin_control/_report_helpers.py`: Process reporting helpers for stop operations
- `src/amd_adrenalin_control/_stylesheet.py`: Application stylesheet
- `src/amd_adrenalin_control/constants.py`: App constants and process name sets
- `src/amd_adrenalin_control/ui_helpers.py`: UI runtime type helpers
- `requirements.txt`: Runtime dependencies
- `pyproject.toml`: Project metadata and tooling config

## Notes

- Some AMD processes require administrative privileges and may trigger a UAC prompt.

## License

GNU GPL v3.0 (GPL-3.0-only). See COPYING.
