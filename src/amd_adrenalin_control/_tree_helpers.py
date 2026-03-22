"""Tree widget display, population, and UI state persistence helpers."""

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

from .constants import (
    EVEN_ROW_REMAINDER,
    NAME_COLUMN_INDEX,
    PATH_COLUMN_INDEX,
    PROCESS_TOOLTIPS,
    STATUS_COLORS,
    STATUS_COLUMN_INDEX,
)
from .refresh_snapshot import RowSnapshot
from .ui_helpers import COPY_TEXT_ROLE

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

_EMPTY_VALUES = ('No active processes', '-', '-', '-', '-', '-')
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
        sample = tree.topLevelItem(0)
        row_height = (
            tree.visualItemRect(sample).height()
            if sample is not None
            else 0
        ) or 28
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

    def _build_hierarchical_tree_items(
        self: TreeDisplayMixin,
        tree: QTreeWidget,
        rows: list[RowSnapshot],
    ) -> None:
        """Build QTreeWidgetItems from row snapshots using indent for nesting."""
        parent_stack: list[QTreeWidgetItem] = []
        for row_idx, row in enumerate(rows):
            row_bg = (
                _COLOR_ROW_EVEN
                if row_idx % 2 == EVEN_ROW_REMAINDER
                else _COLOR_ROW_ODD
            )
            del parent_stack[row['indent']:]
            if parent_stack:
                tree_item = QTreeWidgetItem(parent_stack[-1])
            else:
                tree_item = QTreeWidgetItem(tree)
            parent_stack.append(tree_item)
            self._configure_managed_tree_item_columns(tree_item, row_bg, row)

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

    def _update_tree_section(
        self: TreeDisplayMixin,
        section: QWidget,
        tree: QTreeWidget,
        state: ManagedTreeUiState,
        processes: list[RowSnapshot],
    ) -> None:
        """Update a section with process rows or an empty-state placeholder."""
        section.setVisible(True)
        self._update_section_count(section, len(processes))
        if not processes:
            self._populate_empty_row(tree)
            self._resize_tree_widget(tree)
            return
        self._save_tree_ui(tree, state)
        tree.setUpdatesEnabled(False)
        tree.clear()
        self._build_hierarchical_tree_items(tree, processes)
        self._restore_tree_ui(tree, state)
        self._resize_tree_widget(tree)
        tree.setUpdatesEnabled(True)

    def update_process_section(
        self: TreeDisplayMixin,
        section: QWidget,
        tree: QTreeWidget,
        processes: list[RowSnapshot],
    ) -> None:
        """Keep section visible and show either process rows or an empty-state row."""
        self._update_tree_section(
            section, tree, self._tree_ui.service, processes,
        )

    def update_companion_section(
        self: TreeDisplayMixin,
        processes: list[RowSnapshot],
    ) -> None:
        """Update companion section with tree hierarchy like the managed section."""
        self._update_tree_section(
            self.companion_section,
            self.companion_tree,
            self._tree_ui.companion,
            processes,
        )

    def update_managed_section(
        self: TreeDisplayMixin,
        processes: list[RowSnapshot],
    ) -> None:
        """Update the managed tree section with process data or an empty state."""
        self._update_tree_section(
            self.managed_section,
            self.managed_tree,
            self._tree_ui.managed,
            processes,
        )

    # -- Tree UI state persistence -------------------------------------

    def _save_tree_ui(
        self: TreeDisplayMixin,
        tree: QTreeWidget,
        state: ManagedTreeUiState,
    ) -> None:
        """Persist expansion and selection state for a hierarchical tree."""
        state.expanded.clear()
        state.selected_cells.clear()
        sel_model = tree.selectionModel()
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            if top is not None:
                self._save_tree_ui_recursive(state, tree, sel_model, top)

    def _restore_tree_ui(
        self: TreeDisplayMixin,
        tree: QTreeWidget,
        state: ManagedTreeUiState,
    ) -> None:
        """Restore expansion and selection state for a hierarchical tree."""
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
        sel_model: QItemSelectionModel | None,
        item: QTreeWidgetItem,
    ) -> None:
        """Recursively save expansion and selection into a state object."""
        pid = item.data(
            NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole,
        )
        if isinstance(pid, int):
            state.expanded[pid] = item.isExpanded()
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
                self._save_tree_ui_recursive(
                    state, tree, sel_model, child,
                )

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
