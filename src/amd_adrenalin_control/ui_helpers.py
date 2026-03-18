"""UI-specific runtime type validation helpers."""

from PyQt6.QtCore import QItemSelectionModel, QModelIndex, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QHeaderView,
    QTableWidget,
    QTreeWidget,
)

COPY_TEXT_ROLE = Qt.ItemDataRole.UserRole + 1

_CopyView = QTableWidget | QTreeWidget


class InvalidTypeError(TypeError):
    """Raised when a value is not the expected runtime type."""

    def __init__(self, field_name: str, expected_type: str, actual_type: str) -> None:
        """Build a consistent type-validation error message."""
        message = f'{field_name} must be {expected_type}, got {actual_type}'
        super().__init__(message)


def require_str(value: object, field_name: str) -> str:
    """Return value as a string, or raise if it is not a string."""
    if not isinstance(value, str):
        raise InvalidTypeError(field_name, 'str', type(value).__name__)
    return value


def require_qheader_view(value: object, field_name: str) -> QHeaderView:
    """Return value as a QHeaderView, or raise if it is missing or invalid."""
    if not isinstance(value, QHeaderView):
        raise InvalidTypeError(field_name, 'QHeaderView', type(value).__name__)
    return value


def _cell_text(view: _CopyView, index: QModelIndex) -> str:
    """Return clipboard text for a model index, preferring COPY_TEXT_ROLE."""
    model = view.model()
    if model is None:
        return ''
    clipboard_text = model.data(index, COPY_TEXT_ROLE)
    if isinstance(clipboard_text, str):
        return clipboard_text
    display = model.data(index, Qt.ItemDataRole.DisplayRole)
    return str(display) if display is not None else ''


def copy_selected_rows(view: _CopyView) -> None:
    """Copy selected rows to the clipboard as tab-separated text."""
    sel_model = view.selectionModel()
    if sel_model is None:
        return

    indexes = sel_model.selectedIndexes()
    if not indexes:
        return

    model = view.model()
    if model is None:
        return

    col_count = model.columnCount()
    rows_by_y: dict[int, QModelIndex] = {}
    for idx in indexes:
        y = view.visualRect(idx).y()
        if y not in rows_by_y:
            rows_by_y[y] = idx

    copied_rows: list[str] = []
    for y in sorted(rows_by_y):
        ref = rows_by_y[y]
        row_values = [
            _cell_text(view, model.index(ref.row(), col, ref.parent()))
            for col in range(col_count)
        ]
        copied_rows.append('\t'.join(row_values))

    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText('\n'.join(copied_rows))


def copy_selected_cells(view: _CopyView) -> None:
    """Copy selected cells to the clipboard preserving row/column layout."""
    sel_model = view.selectionModel()
    if sel_model is None:
        return

    indexes = sel_model.selectedIndexes()
    if not indexes:
        return

    min_col = min(idx.column() for idx in indexes)
    max_col = max(idx.column() for idx in indexes)

    rows_by_y: dict[int, dict[int, QModelIndex]] = {}
    for idx in indexes:
        y = view.visualRect(idx).y()
        rows_by_y.setdefault(y, {})[idx.column()] = idx

    copied_rows: list[str] = []
    for y in sorted(rows_by_y):
        col_map = rows_by_y[y]
        row_values: list[str] = []
        for col in range(min_col, max_col + 1):
            cell_idx = col_map.get(col)
            row_values.append(
                _cell_text(view, cell_idx) if cell_idx is not None else '',
            )
        copied_rows.append('\t'.join(row_values))

    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText('\n'.join(copied_rows))


def select_row(view: _CopyView, index: QModelIndex) -> None:
    """Select all cells in the row containing *index*."""
    sel_model = view.selectionModel()
    model = view.model()
    if sel_model is None or model is None:
        return
    sel_model.clearSelection()
    parent = index.parent()
    for col in range(model.columnCount(parent)):
        sel_model.select(
            model.index(index.row(), col, parent),
            QItemSelectionModel.SelectionFlag.Select,
        )


def select_column(view: _CopyView, col: int) -> None:
    """Select all visible cells in column *col*."""
    sel_model = view.selectionModel()
    model = view.model()
    if sel_model is None or model is None:
        return
    sel_model.clearSelection()

    def _select_children(parent: QModelIndex) -> None:
        for row in range(model.rowCount(parent)):
            sel_model.select(
                model.index(row, col, parent),
                QItemSelectionModel.SelectionFlag.Select,
            )
            child_parent = model.index(row, 0, parent)
            if model.rowCount(child_parent) > 0:
                _select_children(child_parent)

    _select_children(view.rootIndex())


def select_all_cells(view: _CopyView) -> None:
    """Select every cell in the view."""
    sel_model = view.selectionModel()
    model = view.model()
    if sel_model is None or model is None:
        return
    sel_model.clearSelection()
    col_count = model.columnCount()

    def _select_children(parent: QModelIndex) -> None:
        for row in range(model.rowCount(parent)):
            for col in range(col_count):
                sel_model.select(
                    model.index(row, col, parent),
                    QItemSelectionModel.SelectionFlag.Select,
                )
            child_parent = model.index(row, 0, parent)
            if model.rowCount(child_parent) > 0:
                _select_children(child_parent)

    _select_children(view.rootIndex())
