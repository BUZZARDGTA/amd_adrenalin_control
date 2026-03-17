# AMD Adrenalin Control

PyQt6 desktop utility for Windows to control AMD Adrenalin and monitor related AMD processes.

## Preview

<img width="1132" height="917" alt="python_2026-03-17_07-17" src="https://github.com/user-attachments/assets/d59c280f-274f-41cb-a6e5-176f09249af8" />

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
- `src/amd_adrenalin_control/constants.py`: App constants and process name sets
- `src/amd_adrenalin_control/ui_helpers.py`: UI runtime type helpers
- `requirements.txt`: Runtime dependencies
- `pyproject.toml`: Project metadata and tooling config

## Notes

- Some AMD processes require administrative privileges and may trigger a UAC prompt.

## License

GNU GPL v3.0 (GPL-3.0-only). See COPYING.
