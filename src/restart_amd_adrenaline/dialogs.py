"""Custom PyQt dialogs for notifications and structured process reports."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QMessageBox,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .ui_helpers import require_qheader_view


class NotificationDialog(QDialog):
    """Styled in-app dialog used instead of native message boxes."""

    def __init__(self, parent: QWidget, title: str, text: str, icon: QMessageBox.Icon) -> None:
        """Initialize a styled modal notification dialog."""
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(680, 420)
        self.resize(760, 520)

        heading_text, accent = self.icon_theme(icon)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        heading = QLabel(f"{heading_text}  {title}", self)
        heading.setObjectName("dialog_heading")

        body = QLabel("Details", self)
        body.setObjectName("dialog_subheading")

        content = QTableWidget(0, 1, self)
        content.setObjectName("dialog_text")
        content.setRowCount(1)
        content.setColumnCount(1)
        require_qheader_view(content.horizontalHeader(), "dialog horizontal header").setVisible(False)
        require_qheader_view(content.verticalHeader(), "dialog vertical header").setVisible(False)
        content.setShowGrid(False)
        content.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        content.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        content.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        content.setWordWrap(True)
        content.setTextElideMode(Qt.TextElideMode.ElideNone)
        content.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        text_item = QTableWidgetItem(text)
        text_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        content.setItem(0, 0, text_item)
        content.setColumnWidth(0, 680)
        content.resizeRowsToContents()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        buttons.accepted.connect(self.accept)  # pyright: ignore[reportUnknownMemberType]

        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addWidget(content, 1)
        layout.addWidget(buttons)

        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: #0c1320;
                color: #d7e3f5;
                border: 1px solid #1d2b43;
                border-radius: 12px;
            }}
            QLabel#dialog_heading {{
                color: {accent};
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#dialog_subheading {{
                color: #8ea7c7;
                font-size: 11px;
                font-weight: 700;
            }}
            QTableWidget#dialog_text {{
                background-color: #0b111d;
                color: #d7e3f5;
                border: 1px solid #1f2f4a;
                border-radius: 8px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
                padding: 8px;
            }}
            QDialogButtonBox QPushButton {{
                background-color: #1f6feb;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 8px 16px;
                min-width: 90px;
            }}
            QDialogButtonBox QPushButton:hover {{
                background-color: #3a82f7;
            }}
            QDialogButtonBox QPushButton:pressed {{
                background-color: #1759bf;
            }}
            """,
        )

    @staticmethod
    def icon_theme(icon: QMessageBox.Icon) -> tuple[str, str]:
        """Return heading label and accent color for the provided icon type."""
        if icon == QMessageBox.Icon.Warning:
            return "WARNING", "#f59e0b"
        if icon == QMessageBox.Icon.Critical:
            return "ERROR", "#ef4444"
        if icon == QMessageBox.Icon.Information:
            return "INFO", "#22c55e"
        return "NOTICE", "#60a5fa"


class ProcessReportDialog(QDialog):
    """Structured process report dialog with section and process cards."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        icon: QMessageBox.Icon,
        sections: list[tuple[str, list[dict[str, str]]]],
    ) -> None:
        """Initialize a structured modal report dialog with section cards."""
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(860, 620)
        self.resize(980, 720)

        populated_sections = [
            (section_title, entries)
            for section_title, entries in sections
            if entries
        ]

        heading_text, accent = NotificationDialog.icon_theme(icon)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        heading = QLabel(f"{heading_text}  {title}", self)
        heading.setObjectName("report_heading")

        subtitle = QLabel("Action Report", self)
        subtitle.setObjectName("report_subheading")

        scroll = QScrollArea(self)
        scroll.setObjectName("report_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        if viewport := scroll.viewport():
            viewport.setObjectName("report_viewport")

        body = QWidget(scroll)
        body.setObjectName("report_body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)

        if not populated_sections:
            empty = QLabel("No processes to report.", body)
            empty.setObjectName("report_empty")
            body_layout.addWidget(empty)
        else:
            for section_title, entries in populated_sections:
                section = QFrame(body)
                section.setObjectName("report_section")
                section_layout = QVBoxLayout(section)
                section_layout.setContentsMargins(12, 12, 12, 12)
                section_layout.setSpacing(8)

                section_header = QLabel(f"{section_title} ({len(entries)})", section)
                section_header.setObjectName("report_section_title")
                section_layout.addWidget(section_header)

                for entry in entries:
                    card = QFrame(section)
                    card.setObjectName("report_card")
                    card_layout = QVBoxLayout(card)
                    card_layout.setContentsMargins(10, 10, 10, 10)
                    card_layout.setSpacing(4)

                    name = entry.get("name", "<unknown>")
                    pid = entry.get("pid", "?")
                    category = entry.get("category", "Unknown")
                    parent_text = entry.get("parent", "<unknown>")
                    path_text = entry.get("path", "<unavailable>")

                    title_label = QLabel(f"{name} (PID {pid})", card)
                    title_label.setObjectName("report_card_title")

                    meta_label = QLabel(
                        f"Category: {category}\n"
                        f"Parent: {parent_text}",
                        card,
                    )
                    meta_label.setObjectName("report_card_meta")

                    path_label = QLabel("Path:", card)
                    path_label.setObjectName("report_card_path_label")

                    path_value = QLabel(path_text, card)
                    path_value.setObjectName("report_card_path")
                    path_value.setWordWrap(True)
                    path_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

                    card_layout.addWidget(title_label)
                    card_layout.addWidget(meta_label)
                    card_layout.addWidget(path_label)
                    card_layout.addWidget(path_value)
                    section_layout.addWidget(card)

                body_layout.addWidget(section)

        body_layout.addStretch()
        scroll.setWidget(body)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        buttons.accepted.connect(self.accept)  # pyright: ignore[reportUnknownMemberType]

        root.addWidget(heading)
        root.addWidget(subtitle)
        root.addWidget(scroll, 1)
        root.addWidget(buttons)

        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: #0c1320;
                color: #d7e3f5;
                border: 1px solid #1d2b43;
                border-radius: 12px;
            }}
            QScrollArea#report_scroll,
            QWidget#report_viewport,
            QWidget#report_body {{
                background-color: #0c1320;
                border: none;
            }}
            QLabel#report_heading {{
                color: {accent};
                font-size: 16px;
                font-weight: 800;
            }}
            QLabel#report_subheading {{
                color: #8ea7c7;
                font-size: 11px;
                font-weight: 700;
            }}
            QFrame#report_section {{
                background-color: #0b111d;
                border: 1px solid #1d2f4b;
                border-radius: 10px;
            }}
            QLabel#report_section_title {{
                color: #9fc3f2;
                font-size: 12px;
                font-weight: 800;
            }}
            QLabel#report_empty {{
                color: #64748b;
                font-size: 11px;
                font-style: italic;
            }}
            QFrame#report_card {{
                background-color: #101a2b;
                border: 1px solid #243a5a;
                border-radius: 8px;
            }}
            QLabel#report_card_title {{
                color: #dce9fb;
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#report_card_meta {{
                color: #9ab4d5;
                font-size: 11px;
            }}
            QLabel#report_card_path_label {{
                color: #84a8d8;
                font-size: 11px;
                font-weight: 700;
            }}
            QLabel#report_card_path {{
                color: #d0def3;
                font-size: 11px;
                background-color: #0b1422;
                border: 1px solid #1f2f49;
                border-radius: 6px;
                padding: 6px;
            }}
            QDialogButtonBox QPushButton {{
                background-color: #1f6feb;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 8px 16px;
                min-width: 90px;
            }}
            QDialogButtonBox QPushButton:hover {{
                background-color: #3a82f7;
            }}
            QDialogButtonBox QPushButton:pressed {{
                background-color: #1759bf;
            }}
            """,
        )
