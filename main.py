"""Application entrypoint for AMD Adrenalin Control."""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from amd_adrenalin_control.main_window import MainWindow


def main() -> None:
    """Application entrypoint used by direct execution and project scripts."""
    app = QApplication([])
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()

    app.exec()


if __name__ == '__main__':
    main()
