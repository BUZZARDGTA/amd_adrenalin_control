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

_DIALOG_BASE_STYLESHEET = """\
QDialog {
    background-color: #0c1320;
    color: #d7e3f5;
    border: 1px solid #1d2b43;
    border-radius: 12px;
}
QDialogButtonBox QPushButton {
    background-color: #1f6feb;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 700;
    padding: 8px 16px;
    min-width: 90px;
}
QDialogButtonBox QPushButton:hover {
    background-color: #3a82f7;
}
QDialogButtonBox QPushButton:pressed {
    background-color: #1759bf;
}
"""


class NotificationDialog(QDialog):
    """Styled in-app dialog used instead of native message boxes."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        text: str,
        icon: QMessageBox.Icon,
    ) -> None:
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

        heading = QLabel(f'{heading_text}  {title}', self)
        heading.setObjectName('dialog_heading')

        body = QLabel('Details', self)
        body.setObjectName('dialog_subheading')

        content = QTableWidget(1, 1, self)
        content.setObjectName('dialog_text')
        h_header = require_qheader_view(
            content.horizontalHeader(),
            'dialog horizontal header',
        )
        h_header.setVisible(False)
        v_header = require_qheader_view(
            content.verticalHeader(),
            'dialog vertical header',
        )
        v_header.setVisible(False)
        content.setShowGrid(False)
        content.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        content.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        content.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        content.setWordWrap(True)
        content.setTextElideMode(Qt.TextElideMode.ElideNone)
        content.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        text_item = QTableWidgetItem(text)
        text_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop,
        )
        content.setItem(0, 0, text_item)
        content.setColumnWidth(0, 680)
        content.resizeRowsToContents()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        buttons.accepted.connect(  # pyright: ignore[reportUnknownMemberType]
            self.accept,
        )

        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addWidget(content, 1)
        layout.addWidget(buttons)

        self.setStyleSheet(
            _DIALOG_BASE_STYLESHEET
            + f"""
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
            """,
        )

    @staticmethod
    def icon_theme(icon: QMessageBox.Icon) -> tuple[str, str]:
        """Return heading label and accent color for the provided icon type."""
        if icon == QMessageBox.Icon.Warning:
            return 'WARNING', '#f59e0b'
        if icon == QMessageBox.Icon.Critical:
            return 'ERROR', '#ef4444'
        if icon == QMessageBox.Icon.Information:
            return 'INFO', '#22c55e'
        return 'NOTICE', '#60a5fa'


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

        heading_text, accent = NotificationDialog.icon_theme(icon)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        heading = QLabel(f'{heading_text}  {title}', self)
        heading.setObjectName('report_heading')

        subtitle = QLabel('Action Report', self)
        subtitle.setObjectName('report_subheading')

        scroll = QScrollArea(self)
        scroll.setObjectName('report_scroll')
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        if viewport := scroll.viewport():
            viewport.setObjectName('report_viewport')

        self._body = QWidget(scroll)
        self._body.setObjectName('report_body')
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(12)

        self.populate_sections(sections)

        scroll.setWidget(self._body)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        buttons.accepted.connect(  # pyright: ignore[reportUnknownMemberType]
            self.accept,
        )

        root.addWidget(heading)
        root.addWidget(subtitle)
        root.addWidget(scroll, 1)
        root.addWidget(buttons)

        self.setStyleSheet(
            _DIALOG_BASE_STYLESHEET
            + f"""
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
            """,
        )

    def populate_sections(
        self,
        sections: list[tuple[str, list[dict[str, str]]]],
    ) -> None:
        """Build section and process cards into the report body."""
        populated = [
            (section_title, entries)
            for section_title, entries in sections
            if entries
        ]

        if not populated:
            empty = QLabel('No processes to report.', self._body)
            empty.setObjectName('report_empty')
            self._body_layout.addWidget(empty)
        else:
            for section_title, entries in populated:
                section = QFrame(self._body)
                section.setObjectName('report_section')
                section_layout = QVBoxLayout(section)
                section_layout.setContentsMargins(12, 12, 12, 12)
                section_layout.setSpacing(8)

                section_header = QLabel(
                    f'{section_title} ({len(entries)})', section,
                )
                section_header.setObjectName('report_section_title')
                section_layout.addWidget(section_header)

                for entry in entries:
                    self._build_entry_card(section, section_layout, entry)

                self._body_layout.addWidget(section)

        self._body_layout.addStretch()

    @staticmethod
    def _build_entry_card(
        parent: QFrame,
        layout: QVBoxLayout,
        entry: dict[str, str],
    ) -> None:
        """Build a single process entry card and add it to *layout*."""
        card = QFrame(parent)
        card.setObjectName('report_card')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(4)

        name = entry.get('name', '<unknown>')
        pid = entry.get('pid', '?')
        category = entry.get('category', 'Unknown')
        parent_text = entry.get('parent', '')
        path_text = entry.get('path', '<unavailable>')

        title_label = QLabel(f'{name} (PID {pid})', card)
        title_label.setObjectName('report_card_title')

        meta_lines = f'Category: {category}'
        if parent_text and parent_text != '-':
            meta_lines += f'\nParent: {parent_text}'
        meta_label = QLabel(meta_lines, card)
        meta_label.setObjectName('report_card_meta')

        path_label = QLabel('Path:', card)
        path_label.setObjectName('report_card_path_label')

        path_value = QLabel(path_text, card)
        path_value.setObjectName('report_card_path')
        path_value.setWordWrap(True)
        path_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )

        card_layout.addWidget(title_label)
        card_layout.addWidget(meta_label)
        card_layout.addWidget(path_label)
        card_layout.addWidget(path_value)
        layout.addWidget(card)
