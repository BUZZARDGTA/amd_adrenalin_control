"""UI-specific runtime type validation helpers."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QHeaderView, QTableWidget, QTableWidgetItem

COPY_TEXT_ROLE = Qt.ItemDataRole.UserRole + 1


class InvalidTypeError(TypeError):
    """Raised when a value is not the expected runtime type."""

    def __init__(self, field_name: str, expected_type: str, actual_type: str) -> None:
        """Build a consistent type-validation error message."""
        message = f"{field_name} must be {expected_type}, got {actual_type}"
        super().__init__(message)


def require_str(value: object, field_name: str) -> str:
    """Return value as a string, or raise if it is not a string."""
    if not isinstance(value, str):
        raise InvalidTypeError(field_name, "str", type(value).__name__)
    return value


def require_qheader_view(value: object, field_name: str) -> QHeaderView:
    """Return value as a QHeaderView, or raise if it is missing or invalid."""
    if not isinstance(value, QHeaderView):
        raise InvalidTypeError(field_name, "QHeaderView", type(value).__name__)
    return value


def _clipboard_text_for_item(item: QTableWidgetItem | None) -> str:
    """Return clipboard text override for an item when one exists."""
    if item is None:
        return ""

    clipboard_text = item.data(COPY_TEXT_ROLE)
    if isinstance(clipboard_text, str):
        return clipboard_text
    return item.text()


def copy_selected_rows(table: QTableWidget) -> None:
    """Copy selected table rows to the clipboard as tab-separated text."""
    selection_model = table.selectionModel()
    if selection_model is None:
        return

    selected_indexes = selection_model.selectedIndexes()
    if not selected_indexes:
        return

    row_numbers = sorted({index.row() for index in selected_indexes})
    copied_rows: list[str] = []
    for row_idx in row_numbers:
        row_values: list[str] = []
        for col_idx in range(table.columnCount()):
            item = table.item(row_idx, col_idx)
            row_values.append(_clipboard_text_for_item(item))
        copied_rows.append("\t".join(row_values))

    clipboard = QApplication.clipboard()
    if clipboard is None:
        return

    clipboard.setText("\n".join(copied_rows))


def copy_selected_cells(table: QTableWidget) -> None:
    """Copy selected cells to the clipboard preserving row/column layout."""
    selection_model = table.selectionModel()
    if selection_model is None:
        return

    selected_indexes = selection_model.selectedIndexes()
    if not selected_indexes:
        return

    min_row = min(index.row() for index in selected_indexes)
    max_row = max(index.row() for index in selected_indexes)
    min_col = min(index.column() for index in selected_indexes)
    max_col = max(index.column() for index in selected_indexes)
    selected_positions = {(index.row(), index.column()) for index in selected_indexes}

    copied_rows: list[str] = []
    for row_idx in range(min_row, max_row + 1):
        row_values: list[str] = []
        for col_idx in range(min_col, max_col + 1):
            if (row_idx, col_idx) not in selected_positions:
                row_values.append("")
                continue

            item = table.item(row_idx, col_idx)
            row_values.append(_clipboard_text_for_item(item))
        copied_rows.append("\t".join(row_values))

    clipboard = QApplication.clipboard()
    if clipboard is None:
        return

    clipboard.setText("\n".join(copied_rows))
