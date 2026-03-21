"""Tree widget display, population, and UI state persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple

from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from .constants import PROCESS_TOOLTIPS, STATUS_COLORS
from .refresh_snapshot import RowSnapshot
from .ui_helpers import COPY_TEXT_ROLE

PATH_COLUMN_INDEX = 1
PID_COLUMN_INDEX = 2
STATUS_COLUMN_INDEX = 5
NAME_COLUMN_INDEX = 0
EVEN_ROW_REMAINDER = 0

_COLOR_ROW_EVEN = QColor('#111827')
_COLOR_ROW_ODD = QColor('#0d1220')
_COLOR_MUTED = QColor('#94a3b8')
_COLOR_EMPTY = QColor('#64748b')
_STATUS_QCOLORS: dict[str, QColor] = {
    status: QColor(color) for status, color in STATUS_COLORS.items()
}

_ALIGNS = (
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignCenter,
)

_EMPTY_VALUES = ('No active processes', '-', '-', '-', '-', 'idle')
_EMPTY_ALIGNS = (
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignCenter,
)


@dataclass(slots=True)
class ManagedTreeUiState:
    """Mutable UI state for a single process tree section."""

    expanded: dict[int, bool] = field(default_factory=dict[int, bool])
    selected_cells: dict[int, set[int]] = field(default_factory=dict[int, set[int]])


class TreeUiStates(NamedTuple):
    """Per-section tree UI states."""

    managed: ManagedTreeUiState
    companion: ManagedTreeUiState
    service: ManagedTreeUiState


class TreeDisplayMixin:
    """Mixin providing tree widget display and state-persistence methods."""

    if TYPE_CHECKING:
        @property
        def managed_tree(self) -> QTreeWidget:
            """Tree widget for managed processes."""
            return QTreeWidget()
        @property
        def companion_tree(self) -> QTreeWidget:
            """Tree widget for companion processes."""
            return QTreeWidget()
        @property
        def service_tree(self) -> QTreeWidget:
            """Tree widget for system services."""
            return QTreeWidget()
        @property
        def managed_section(self) -> QWidget:
            """Section widget for managed processes."""
            return QWidget()
        @property
        def companion_section(self) -> QWidget:
            """Section widget for companion processes."""
            return QWidget()
        @property
        def service_section(self) -> QWidget:
            """Section widget for system services."""
            return QWidget()
        _tree_ui: TreeUiStates

    # -- Tree display --------------------------------------------------

    @staticmethod
    def _count_visible_descendants(item: QTreeWidgetItem) -> int:
        """Recursively count visible descendants of an expanded tree item."""
        count = 0
        if item.isExpanded():
            for i in range(item.childCount()):
                child = item.child(i)
                if child is not None and not child.isHidden():
                    count += 1
                    count += TreeDisplayMixin._count_visible_descendants(child)
        return count

    def _resize_tree_widget(self: TreeDisplayMixin, tree: QTreeWidget) -> None:
        """Fit a tree widget to its visible items so sections stay compact."""
        header = tree.header()
        header_height = header.height() if header is not None else 0
        row_height = 28
        frame_height = tree.frameWidth() * 2

        visible_count = 0
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item is not None and not item.isHidden():
                visible_count += 1
                visible_count += self._count_visible_descendants(item)

        tree.setFixedHeight(
            header_height + (visible_count * row_height) + frame_height,
        )

    def _resize_managed_tree(self: TreeDisplayMixin) -> None:
        """Fit the managed tree to its visible items so sections stay compact."""
        tree = self.managed_tree
        self._resize_tree_widget(tree)

    def _configure_managed_tree_item_columns(
        self: TreeDisplayMixin,
        tree_item: QTreeWidgetItem,
        row_bg: QColor,
        row: RowSnapshot,
    ) -> None:
        """Set text, alignment, colors, tooltips, and data roles on a tree item."""
        name = row['name']
        path_text = row['path']
        status = row['status']
        values = (
            name, path_text,
            row['pid_text'],
            row['cpu_text'],
            row['mem_text'],
            status,
        )

        for col, (val, align) in enumerate(zip(values, _ALIGNS, strict=True)):
            tree_item.setText(col, val)
            tree_item.setTextAlignment(col, align)
            tree_item.setBackground(col, row_bg)
            if col == NAME_COLUMN_INDEX:
                tree_item.setData(col, COPY_TEXT_ROLE, name)
                if tooltip := PROCESS_TOOLTIPS.get(name.lower()):
                    tree_item.setToolTip(col, tooltip)
                if isinstance(row.get('pid_value'), int):
                    tree_item.setData(
                        col, Qt.ItemDataRole.UserRole, row['pid_value'],
                    )
            elif col == PATH_COLUMN_INDEX:
                tree_item.setToolTip(col, path_text)
            if col == STATUS_COLUMN_INDEX:
                tree_item.setForeground(
                    col,
                    _STATUS_QCOLORS.get(status, _COLOR_MUTED),
                )

    def _populate_process_tree(
        self: TreeDisplayMixin,
        tree: QTreeWidget,
        rows: list[RowSnapshot],
    ) -> None:
        """Populate a process tree widget from plain row snapshots."""
        tree.setUpdatesEnabled(False)
        tree.clear()

        for row_idx, row in enumerate(rows):
            row_bg = (
                _COLOR_ROW_EVEN
                if row_idx % 2 == EVEN_ROW_REMAINDER
                else _COLOR_ROW_ODD
            )

            tree_item = QTreeWidgetItem(tree)
            self._configure_managed_tree_item_columns(
                tree_item, row_bg, row,
            )

        self._resize_tree_widget(tree)
        tree.setUpdatesEnabled(True)

    @staticmethod
    def _update_section_count(section: QWidget, count: int) -> None:
        """Update the process count label inside a section widget."""
        result = section.findChild(QWidget, 'section_count')
        if isinstance(result, QLabel):
            result.setText(f'({count})')

    @staticmethod
    def _populate_empty_row(tree: QTreeWidget) -> None:
        """Insert a non-selectable placeholder row into an empty tree."""
        tree.clear()
        empty_item = QTreeWidgetItem(tree)
        empty_item.setFlags(
            empty_item.flags()
            & ~Qt.ItemFlag.ItemIsSelectable
            & ~Qt.ItemFlag.ItemIsEnabled,
        )
        for col, (val, align) in enumerate(
            zip(_EMPTY_VALUES, _EMPTY_ALIGNS, strict=True),
        ):
            empty_item.setText(col, val)
            empty_item.setTextAlignment(col, align)
            empty_item.setBackground(col, _COLOR_ROW_ODD)
            empty_item.setForeground(col, _COLOR_EMPTY)

    # -- Section updates -----------------------------------------------

    def update_process_section(
        self: TreeDisplayMixin,
        section: QWidget,
        tree: QTreeWidget,
        processes: list[RowSnapshot],
    ) -> None:
        """Keep section visible and show either process rows or an empty-state row."""
        section.setVisible(True)
        self._update_section_count(section, len(processes))
        if not processes:
            self._populate_empty_row(tree)
            self._resize_tree_widget(tree)
            return
        is_service = tree is self.service_tree
        if is_service:
            svc_state = self._tree_ui.service
            self._save_flat_tree_selection(
                tree, svc_state,
            )
            tree.setUpdatesEnabled(False)
            tree.clear()
            for row_idx, row in enumerate(processes):
                row_bg = (
                    _COLOR_ROW_EVEN
                    if row_idx % 2 == EVEN_ROW_REMAINDER
                    else _COLOR_ROW_ODD
                )
                tree_item = QTreeWidgetItem(tree)
                self._configure_managed_tree_item_columns(
                    tree_item, row_bg, row,
                )
            self._restore_flat_tree_selection(
                tree, svc_state,
            )
            self._resize_tree_widget(tree)
            tree.setUpdatesEnabled(True)
        else:
            self._populate_process_tree(tree, processes)

    def update_companion_section(
        self: TreeDisplayMixin,
        processes: list[RowSnapshot],
    ) -> None:
        """Update companion section with tree hierarchy like the managed section."""
        section = self.companion_section
        tree = self.companion_tree
        section.setVisible(True)
        self._update_section_count(section, len(processes))
        if not processes:
            self._populate_empty_row(tree)
            self._resize_tree_widget(tree)
            return

        self._save_companion_tree_ui(tree)

        tree.setUpdatesEnabled(False)
        tree.clear()
        parent_stack: list[QTreeWidgetItem] = []

        for row_idx, row in enumerate(processes):
            indent = row['indent']

            row_bg = (
                _COLOR_ROW_EVEN
                if row_idx % 2 == EVEN_ROW_REMAINDER
                else _COLOR_ROW_ODD
            )

            del parent_stack[indent:]

            if parent_stack:
                tree_item = QTreeWidgetItem(parent_stack[-1])
            else:
                tree_item = QTreeWidgetItem(tree)

            parent_stack.append(tree_item)

            self._configure_managed_tree_item_columns(
                tree_item, row_bg, row,
            )

        self._restore_companion_tree_ui(tree)
        self._resize_tree_widget(tree)
        tree.setUpdatesEnabled(True)

    def _populate_managed_tree(
        self: TreeDisplayMixin,
        rows: list[RowSnapshot],
    ) -> None:
        """Populate the managed tree widget from plain row snapshots."""
        tree = self.managed_tree
        self._save_managed_tree_expansion()
        self._save_managed_tree_selection()

        tree.setUpdatesEnabled(False)
        tree.clear()

        # Stack tracks the tree item at each depth so children
        # attach under the correct parent at any nesting level.
        parent_stack: list[QTreeWidgetItem] = []

        for row_idx, row in enumerate(rows):
            indent = row['indent']

            row_bg = (
                _COLOR_ROW_EVEN
                if row_idx % 2 == EVEN_ROW_REMAINDER
                else _COLOR_ROW_ODD
            )

            # Trim the stack back to the current indent depth.
            del parent_stack[indent:]

            if parent_stack:
                tree_item = QTreeWidgetItem(parent_stack[-1])
            else:
                tree_item = QTreeWidgetItem(tree)

            parent_stack.append(tree_item)

            self._configure_managed_tree_item_columns(
                tree_item, row_bg, row,
            )

        self._restore_managed_tree_expansion()
        self._restore_managed_tree_selection()
        self._resize_managed_tree()
        tree.setUpdatesEnabled(True)

    def update_managed_section(
        self: TreeDisplayMixin,
        processes: list[RowSnapshot],
    ) -> None:
        """Update the managed tree section with process data or an empty state."""
        section = self.managed_section
        section.setVisible(True)
        self._update_section_count(section, len(processes))
        if not processes:
            tree = self.managed_tree
            self._populate_empty_row(tree)
            self._resize_managed_tree()
            return
        self._populate_managed_tree(processes)

    # -- Tree UI state persistence -------------------------------------

    @staticmethod
    def _save_flat_tree_selection(
        tree: QTreeWidget,
        state: ManagedTreeUiState,
    ) -> None:
        """Save selected cells for a flat (non-hierarchical) tree."""
        state.selected_cells.clear()
        sel_model = tree.selectionModel()
        if sel_model is None:
            return
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item is None:
                continue
            pid = item.data(
                NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole,
            )
            if not isinstance(pid, int):
                continue
            for col in range(tree.columnCount()):
                idx = tree.indexFromItem(item, col)
                if sel_model.isSelected(idx):
                    state.selected_cells.setdefault(pid, set()).add(col)

    @staticmethod
    def _restore_flat_tree_selection(
        tree: QTreeWidget,
        state: ManagedTreeUiState,
    ) -> None:
        """Restore selected cells for a flat (non-hierarchical) tree."""
        if not state.selected_cells:
            return
        sel_model = tree.selectionModel()
        if sel_model is None:
            return
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item is None:
                continue
            pid = item.data(
                NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole,
            )
            if not isinstance(pid, int):
                continue
            cols = state.selected_cells.get(pid)
            if cols is None:
                continue
            for col in cols:
                idx = tree.indexFromItem(item, col)
                sel_model.select(
                    idx,
                    QItemSelectionModel.SelectionFlag.Select,
                )

    def _save_companion_tree_ui(self: TreeDisplayMixin, tree: QTreeWidget) -> None:
        """Persist expansion and selection state for the companion tree."""
        state = self._tree_ui.companion
        state.expanded.clear()
        state.selected_cells.clear()
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            if top is not None:
                self._save_tree_ui_recursive(state, tree, top)

    def _restore_companion_tree_ui(self: TreeDisplayMixin, tree: QTreeWidget) -> None:
        """Restore expansion and selection state for the companion tree."""
        state = self._tree_ui.companion
        sel_model = tree.selectionModel()
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            if top is not None:
                self._restore_tree_ui_recursive(
                    state, tree, sel_model, top,
                )

    def _save_tree_ui_recursive(
        self: TreeDisplayMixin,
        state: ManagedTreeUiState,
        tree: QTreeWidget,
        item: QTreeWidgetItem,
    ) -> None:
        """Recursively save expansion and selection into a state object."""
        pid = item.data(
            NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole,
        )
        if isinstance(pid, int):
            state.expanded[pid] = item.isExpanded()
            sel_model = tree.selectionModel()
            if sel_model is not None:
                for col in range(tree.columnCount()):
                    idx = tree.indexFromItem(item, col)
                    if sel_model.isSelected(idx):
                        state.selected_cells.setdefault(
                            pid, set(),
                        ).add(col)
        for i in range(item.childCount()):
            child = item.child(i)
            if child is not None:
                self._save_tree_ui_recursive(state, tree, child)

    def _restore_tree_ui_recursive(
        self: TreeDisplayMixin,
        state: ManagedTreeUiState,
        tree: QTreeWidget,
        sel_model: QItemSelectionModel | None,
        item: QTreeWidgetItem,
    ) -> None:
        """Recursively restore expansion and selection from a state object."""
        pid = item.data(
            NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole,
        )
        expanded = (
            state.expanded.get(pid, True)
            if isinstance(pid, int)
            else True
        )
        item.setExpanded(expanded)
        if sel_model is not None and isinstance(pid, int):
            cols = state.selected_cells.get(pid)
            if cols is not None:
                for col in cols:
                    idx = tree.indexFromItem(item, col)
                    sel_model.select(
                        idx,
                        QItemSelectionModel.SelectionFlag.Select,
                    )
        for i in range(item.childCount()):
            child = item.child(i)
            if child is not None:
                self._restore_tree_ui_recursive(
                    state, tree, sel_model, child,
                )

    def _save_item_expansion_recursive(
        self: TreeDisplayMixin,
        item: QTreeWidgetItem,
    ) -> None:
        """Recursively persist expansion state for an item and its children."""
        managed = self._tree_ui.managed
        pid = item.data(NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole)
        if isinstance(pid, int):
            managed.expanded[pid] = item.isExpanded()
        for i in range(item.childCount()):
            child = item.child(i)
            if child is not None:
                self._save_item_expansion_recursive(child)

    def _save_managed_tree_expansion(self: TreeDisplayMixin) -> None:
        """Persist which tree items are currently expanded."""
        tree = self.managed_tree
        for i in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(i)
            if top_item is not None:
                self._save_item_expansion_recursive(top_item)

    def _restore_item_expansion_recursive(
        self: TreeDisplayMixin,
        item: QTreeWidgetItem,
    ) -> None:
        """Recursively re-apply saved expansion state for an item and children."""
        managed = self._tree_ui.managed
        pid = item.data(NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole)
        expanded = (
            managed.expanded.get(pid, True)
            if isinstance(pid, int)
            else True
        )
        item.setExpanded(expanded)
        for i in range(item.childCount()):
            child = item.child(i)
            if child is not None:
                self._restore_item_expansion_recursive(child)

    def _restore_managed_tree_expansion(self: TreeDisplayMixin) -> None:
        """Re-apply saved expansion state to all tree items."""
        tree = self.managed_tree
        for i in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(i)
            if top_item is not None:
                self._restore_item_expansion_recursive(top_item)

    def _save_managed_tree_selection(self: TreeDisplayMixin) -> None:
        """Persist which tree cells are selected, keyed by PID -> columns."""
        tree = self.managed_tree
        managed = self._tree_ui.managed
        managed.selected_cells = {}
        sel_model = tree.selectionModel()
        if sel_model is None:
            return
        for index in sel_model.selectedIndexes():
            item = tree.itemFromIndex(index)
            if item is None:
                continue
            pid = item.data(NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole)
            if isinstance(pid, int):
                managed.selected_cells.setdefault(
                    pid, set(),
                ).add(index.column())

    def _restore_selection_recursive(
        self: TreeDisplayMixin,
        tree: QTreeWidget,
        sel_model: QItemSelectionModel,
        item: QTreeWidgetItem,
    ) -> None:
        """Recursively restore cell selection for an item and its children."""
        self._restore_item_cell_selection(tree, sel_model, item)
        for i in range(item.childCount()):
            child = item.child(i)
            if child is not None:
                self._restore_selection_recursive(tree, sel_model, child)

    def _restore_managed_tree_selection(self: TreeDisplayMixin) -> None:
        """Re-apply saved per-cell selection to tree items matching saved PIDs."""
        managed = self._tree_ui.managed
        if not managed.selected_cells:
            return
        tree = self.managed_tree
        sel_model = tree.selectionModel()
        if sel_model is None:
            return
        for i in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(i)
            if top_item is not None:
                self._restore_selection_recursive(tree, sel_model, top_item)

    def _restore_item_cell_selection(
        self: TreeDisplayMixin,
        tree: QTreeWidget,
        sel_model: QItemSelectionModel,
        item: QTreeWidgetItem,
    ) -> None:
        """Select saved columns for a single tree item if its PID was saved."""
        managed = self._tree_ui.managed
        pid = item.data(NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole)
        if not isinstance(pid, int):
            return
        cols = managed.selected_cells.get(pid)
        if cols is None:
            return
        for col in cols:
            idx = tree.indexFromItem(item, col)
            sel_model.select(idx, QItemSelectionModel.SelectionFlag.Select)
