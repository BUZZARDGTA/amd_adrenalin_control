"""Context menu building, dispatch, and action routing for process trees."""

import contextlib
import subprocess
from typing import TYPE_CHECKING, NamedTuple

import psutil
from PyQt6.QtCore import QModelIndex, QPoint, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QMainWindow,
    QMenu,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from .constants import (
    INVALID_PATH_VALUES,
    NAME_COLUMN_INDEX,
    PATH_COLUMN_INDEX,
    SERVICE_REGISTRY,
    SVC_DETAIL_ACCESS_DENIED,
)
from .process_ops import stop_windows_service
from .uac import is_running_as_admin
from .ui_helpers import (
    copy_selected_cells,
    copy_selected_rows,
    select_all_cells,
    select_column,
    select_row,
)


class _MenuContext(NamedTuple):
    """Bundled context for a process context menu invocation."""

    pid: int | None
    row_path: str | None
    has_children: bool
    row_index: QModelIndex | None
    col_idx: int


class _MenuTarget(NamedTuple):
    """Resolved tree item and column context for a context menu invocation."""

    item: QTreeWidgetItem
    col_idx: int
    row_path: str | None


if TYPE_CHECKING:
    _ContextMenuBase = QMainWindow
else:
    _ContextMenuBase = object


class ContextMenuMixin(_ContextMenuBase):
    """Mixin providing context-menu methods for MainWindow."""

    if TYPE_CHECKING:
        @property
        def managed_tree(self) -> QTreeWidget:
            """Tree widget for managed processes."""
            return QTreeWidget()

        def _format_process_label(self, pid: int) -> str:
            """Build a display label for a process."""
            del pid
            return ''
        def _terminate_single_process(self, pid: int) -> None:
            """Terminate a single process by PID."""
            del pid
        def _stop_single_process(self, pid: int) -> None:
            """Terminate a process tree by PID."""
            del pid
        def _popup(
            self, title: str, text: str, icon: QMessageBox.Icon,
        ) -> None:
            """Show a modal notification dialog."""
            del title, text, icon
        def _offer_uac_elevation(self, *, reason: str) -> None:
            """Offer to relaunch with elevation."""
            del reason
        def _refresh_process_info(self) -> None:
            """Request an asynchronous monitor refresh."""

    def _confirm_terminate(self: ContextMenuMixin, *, pid: int, tree: bool) -> bool:
        """Ask user to confirm terminate action."""
        action_text = (
            'terminate this process tree'
            if tree
            else 'terminate this process'
        )
        detail = (
            'This will stop the selected process and all child processes.'
            if tree
            else 'This will stop only the selected process.'
        )
        process_label = self._format_process_label(pid)
        answer = QMessageBox.question(
            self,
            'Confirm terminate',
            (
                f'Are you sure you want to {action_text}?'
                f'\n\nProcess: {process_label}'
                f'\n\n{detail}'
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    @staticmethod
    def _handle_selection_action(
        chosen_action: QAction,
        actions: dict[str, QAction | None],
        view: QTreeWidget,
        *,
        row_index: QModelIndex | None = None,
        col_idx: int = 0,
    ) -> bool:
        """Handle select/copy actions common to both table and tree menus."""
        if chosen_action == actions.get('copy_cells'):
            copy_selected_cells(view)
        elif chosen_action == actions.get('copy_rows'):
            copy_selected_rows(view)
        elif chosen_action == actions.get('select_row') and row_index is not None:
            select_row(view, row_index)
        elif chosen_action == actions.get('select_column'):
            select_column(view, col_idx)
        elif chosen_action == actions.get('select_all'):
            select_all_cells(view)
        else:
            return False
        return True

    @staticmethod
    def _open_file_location(row_path: str) -> None:
        """Open Windows Explorer with the given file path selected."""
        subprocess.run(  # noqa: S603
            ['explorer', f'/select,{row_path}'],  # noqa: S607
            check=False,
        )

    def _handle_process_menu_action(
        self: ContextMenuMixin,
        *,
        chosen_action: QAction | None,
        actions: dict[str, QAction | None],
        pid: int | None,
        row_path: str | None = None,
    ) -> None:
        """Execute the selected process-row context menu action."""
        if chosen_action is None:
            return

        open_location_action = actions.get('open_location')
        terminate_process_action = actions['terminate_process']
        terminate_tree_action = actions['terminate_tree']

        if (
            open_location_action is not None
            and chosen_action == open_location_action
            and row_path is not None
        ):
            self._open_file_location(row_path)
            return

        if (
            terminate_process_action is not None
            and chosen_action == terminate_process_action
            and pid is not None
            and self._confirm_terminate(pid=pid, tree=False)
        ):
            self._terminate_single_process(pid)
            return

        if (
            terminate_tree_action is not None
            and chosen_action == terminate_tree_action
            and pid is not None
            and self._confirm_terminate(pid=pid, tree=True)
        ):
            self._stop_single_process(pid)

    def _build_process_context_menu(
        self: ContextMenuMixin,
        parent: QWidget,
        *,
        row_path: str | None,
        pid: int | None,
        has_children: bool,
    ) -> tuple[QMenu, dict[str, QAction | None]]:
        """Build the standard process context menu and return (menu, actions)."""
        menu = QMenu(parent)
        actions = self._build_common_menu_actions(menu)
        actions['open_location'] = None
        actions['terminate_process'] = None
        actions['terminate_tree'] = None
        if row_path is not None:
            menu.addSeparator()
            actions['open_location'] = menu.addAction('Open file location')  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long
        if pid is not None:
            menu.addSeparator()
            actions['terminate_process'] = menu.addAction('Terminate process')  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long
            if has_children:
                actions['terminate_tree'] = menu.addAction(  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long
                    'Terminate process tree',
                )
        return menu, actions

    @staticmethod
    def _build_common_menu_actions(
        menu: QMenu,
    ) -> dict[str, QAction | None]:
        """Build copy/select actions shared by all context menus."""
        actions: dict[str, QAction | None] = {
            'copy_cells': menu.addAction('Copy selected cells'),  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long
            'copy_rows': menu.addAction('Copy selected rows'),  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long
        }
        menu.addSeparator()
        actions['select_row'] = menu.addAction('Select row')  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long
        actions['select_column'] = menu.addAction('Select column')  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long
        actions['select_all'] = menu.addAction('Select all')  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long
        return actions

    def _dispatch_context_menu(
        self: ContextMenuMixin,
        view: QTreeWidget,
        position: QPoint,
        ctx: _MenuContext,
    ) -> None:
        """Build, show, and dispatch a process context menu."""
        menu, actions = self._build_process_context_menu(
            view, row_path=ctx.row_path, pid=ctx.pid,
            has_children=ctx.has_children,
        )
        viewport = view.viewport()
        if viewport is None:
            return

        chosen_action = menu.exec(viewport.mapToGlobal(position))  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long
        if chosen_action is None:
            return
        if self._handle_selection_action(
            chosen_action, actions, view,
            row_index=ctx.row_index, col_idx=ctx.col_idx,
        ):
            return
        self._handle_process_menu_action(
            chosen_action=chosen_action,
            actions=actions,
            pid=ctx.pid,
            row_path=ctx.row_path,
        )

    @staticmethod
    def _resolve_menu_target(
        tree: QTreeWidget, position: QPoint,
    ) -> _MenuTarget | None:
        """Resolve the tree item and column context at a click position."""
        tree_item = tree.itemAt(position)
        if tree_item is None:
            return None
        if not tree_item.flags() & Qt.ItemFlag.ItemIsEnabled:
            return None
        header = tree.header()
        col_idx = max(header.logicalIndexAt(position.x()) if header else 0, 0)
        selection_model = tree.selectionModel()
        if selection_model is not None and not selection_model.hasSelection():
            tree.setCurrentItem(tree_item, col_idx)
        path_text = tree_item.text(PATH_COLUMN_INDEX)
        row_path = (
            path_text
            if path_text not in INVALID_PATH_VALUES
            else None
        )
        return _MenuTarget(item=tree_item, col_idx=col_idx, row_path=row_path)

    def show_tree_context_menu(
        self: ContextMenuMixin,
        tree: QTreeWidget,
        position: QPoint,
    ) -> None:
        """Show row actions for a process item in a tree widget."""
        target = self._resolve_menu_target(tree, position)
        if target is None:
            return

        pid: int | None = None
        pid_data = target.item.data(NAME_COLUMN_INDEX, Qt.ItemDataRole.UserRole)
        if isinstance(pid_data, int):
            pid = pid_data

        self._dispatch_context_menu(
            tree, position,
            _MenuContext(
                pid=pid,
                row_path=target.row_path,
                has_children=(
                    self._tree_item_has_children(target.item, pid)
                    if pid is not None else False
                ),
                row_index=tree.indexFromItem(target.item, 0),
                col_idx=target.col_idx,
            ),
        )

    @staticmethod
    def _tree_item_has_children(tree_item: QTreeWidgetItem, pid: int) -> bool:
        """Check whether a tree item or its underlying process has children."""
        if tree_item.childCount() > 0:
            return True
        with contextlib.suppress(psutil.Error):
            return bool(psutil.Process(pid).children(recursive=False))
        return False

    def _show_service_tree_context_menu(
        self: ContextMenuMixin, tree: QTreeWidget, position: QPoint,
    ) -> None:
        """Show service-specific actions for a row in the service tree."""
        target = self._resolve_menu_target(tree, position)
        if target is None:
            return

        service_name = SERVICE_REGISTRY.get(
            target.item.text(NAME_COLUMN_INDEX).lower(),
        )

        row_index = tree.indexFromItem(target.item, 0)

        menu = QMenu(tree)
        actions = self._build_common_menu_actions(menu)
        actions['open_location'] = None
        if target.row_path is not None:
            menu.addSeparator()
            actions['open_location'] = menu.addAction('Open file location')  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long
        actions['stop_service'] = None
        if service_name is not None:
            menu.addSeparator()
            actions['stop_service'] = menu.addAction('Stop service')  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long

        viewport = tree.viewport()
        if viewport is None:
            return

        chosen_action = menu.exec(viewport.mapToGlobal(position))  # pyright: ignore[reportUnknownMemberType]  # pylint: disable=line-too-long
        if chosen_action is None:
            return

        if self._handle_selection_action(
            chosen_action, actions, tree,
            row_index=row_index, col_idx=target.col_idx,
        ):
            return

        self._handle_service_menu_action(
            chosen_action, actions,
            row_path=target.row_path, service_name=service_name,
        )

    def _handle_service_menu_action(
        self: ContextMenuMixin,
        chosen_action: QAction,
        actions: dict[str, QAction | None],
        *,
        row_path: str | None,
        service_name: str | None,
    ) -> None:
        """Execute the selected service-row context menu action."""
        if (
            actions.get('open_location') is not None
            and chosen_action == actions['open_location']
            and row_path is not None
        ):
            self._open_file_location(row_path)
            return

        if (
            actions.get('stop_service') is not None
            and chosen_action == actions['stop_service']
            and service_name is not None
        ):
            self._stop_service_and_report(service_name)

    def _stop_service_and_report(
        self: ContextMenuMixin, service_name: str,
    ) -> None:
        """Stop a Windows service and show the result."""
        ok, detail = stop_windows_service(service_name)
        if ok:
            self._popup(
                'Service Stopped',
                f'{service_name}: {detail}',
                QMessageBox.Icon.Information,
            )
        elif detail == SVC_DETAIL_ACCESS_DENIED:
            if not is_running_as_admin():
                self._offer_uac_elevation(
                    reason=f'Could not stop {service_name}'
                    ' without administrator privileges.',
                )
            else:
                self._popup(
                    'Service Stop Failed',
                    f'{service_name}: {SVC_DETAIL_ACCESS_DENIED}',
                    QMessageBox.Icon.Warning,
                )
        else:
            self._popup(
                'Service Stop Failed',
                f'{service_name}:\n{detail}',
                QMessageBox.Icon.Warning,
            )
        self._refresh_process_info()

    def show_managed_tree_context_menu(
        self: ContextMenuMixin, position: QPoint,
    ) -> None:
        """Show row actions for a process item in the managed tree widget."""
        self.show_tree_context_menu(
            self.managed_tree, position,
        )
