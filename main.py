"""Application entrypoint for AMD Adrenalin Control."""

from PyQt6.QtWidgets import QApplication

from src.restart_amd_adrenaline.main_window import MainWindow


def main() -> None:
    """Application entrypoint used by direct execution and project scripts."""
    app = QApplication([])
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    app.exec()


if __name__ == "__main__":
    main()
