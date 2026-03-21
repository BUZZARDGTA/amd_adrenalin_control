"""Main application window and UI behavior."""

from collections.abc import Callable
from typing import NamedTuple

from PyQt6.QtCore import (
    QModelIndex,
    QPoint,
    Qt,
    QTimer,
)
from PyQt6.QtGui import (
    QAction,
    QCloseEvent,
    QKeySequence,
)
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from ._actions import ActionsMixin, RefreshState
from ._context_menus import ContextMenuMixin
from ._stylesheet import MAIN_STYLESHEET
from ._tree_helpers import ManagedTreeUiState, TreeDisplayMixin, TreeUiStates
from .constants import RADEON_SOFTWARE_PATH
from .refresh_snapshot import RefreshBridge
from .ui_helpers import copy_selected_cells


class _SectionPair(NamedTuple):
    """A process-monitor section widget paired with its tree widget."""

    section: QWidget
    tree: QTreeWidget


class _Sections(NamedTuple):
    """All three process-monitor section pairs."""

    managed: _SectionPair
    companion: _SectionPair
    service: _SectionPair


class _StatusWidgets(NamedTuple):
    """Status indicator widgets shown in the monitor header."""

    label: QLabel
    badge: QLabel


class MainWindow(  # pylint: disable=too-many-ancestors
    TreeDisplayMixin,
    ContextMenuMixin,
    ActionsMixin,
    QMainWindow,
):
    """Main application window for controlling and monitoring AMD Adrenalin."""

    def __init__(self) -> None:
        """Initialise the main window, build the UI, and start the refresh timer."""
        super().__init__()
        self.process_path = RADEON_SOFTWARE_PATH
        self.setWindowTitle(f'AMD Adrenalin Control v{__version__}')
        self.setMinimumSize(1040, 900)
        self.resize(1180, 1020)

        _label = QLabel('', self)
        _label.hide()
        _badge = QLabel('● NOT RUNNING', self)
        _badge.setObjectName('badge_stopped')
        self._status = _StatusWidgets(label=_label, badge=_badge)

        managed_pair = self._create_managed_section(
            self,
            'Radeon Software Managed',
            'Main RadeonSoftware.exe process and any child processes spawned from it.',
        )
        companion_pair = self._create_process_section(
            self,
            'AMD Companion Processes',
            'Supporting user-space AMD helper executables'
            ' that assist telemetry and features.',
        )
        service_pair = self._create_process_section(
            self,
            'AMD System Services',
            'Background service executables that provide'
            ' driver and system-level AMD functionality.',
        )
        self._sections = _Sections(
            managed=_SectionPair(*managed_pair),
            companion=_SectionPair(*companion_pair),
            service=_SectionPair(*service_pair),
        )

        # Replace the generic process context menu on the service tree
        # with a service-specific one (stop service instead of terminate).
        svc_tree = self._sections.service.tree
        _ctx = svc_tree.customContextMenuRequested
        _ctx.disconnect()  # pyright: ignore[reportUnknownMemberType]

        def _on_svc_ctx_menu(pos: QPoint) -> None:
            self._show_service_tree_context_menu(svc_tree, pos)

        _ctx.connect(_on_svc_ctx_menu)  # pyright: ignore[reportUnknownMemberType]
        self._tree_ui = TreeUiStates(
            managed=ManagedTreeUiState(),
            companion=ManagedTreeUiState(),
            service=ManagedTreeUiState(),
        )

        bridge = RefreshBridge(self)
        bridge.snapshot_ready.connect(  # pyright: ignore[reportUnknownMemberType]
            self._apply_refresh_snapshot,
        )
        self._refresh = RefreshState(bridge)

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(  # pyright: ignore[reportUnknownMemberType]
            self._refresh_process_info,
        )
        self._timer.start()
        self._refresh_process_info()

    def closeEvent(  # noqa: N802  # pylint: disable=invalid-name
        self,
        a0: QCloseEvent | None,
    ) -> None:
        """Stop the refresh timer and prevent worker emits on close."""
        self._timer.stop()
        self._refresh.closing.set()
        super().closeEvent(a0)

    # ------------------------------------------------------------------
    # Properties that delegate to grouped containers so the rest of the
    # code can keep using the original attribute names unchanged.
    # ------------------------------------------------------------------

    @property
    def status_label(self) -> QLabel:
        """Hidden label used for status text storage."""
        return self._status.label

    @property
    def status_badge(self) -> QLabel:
        """Visible running/stopped badge in the monitor header."""
        return self._status.badge

    @property
    def managed_section(self) -> QWidget:
        """Section widget for the managed process group."""
        return self._sections.managed.section

    @property
    def managed_tree(self) -> QTreeWidget:
        """Tree widget for the managed process group."""
        return self._sections.managed.tree

    @property
    def companion_section(self) -> QWidget:
        """Section widget for companion processes."""
        return self._sections.companion.section

    @property
    def companion_tree(self) -> QTreeWidget:
        """Tree widget for companion processes."""
        return self._sections.companion.tree

    @property
    def service_section(self) -> QWidget:
        """Section widget for AMD system services."""
        return self._sections.service.section

    @property
    def service_tree(self) -> QTreeWidget:
        """Tree widget for AMD system services."""
        return self._sections.service.tree

    @property
    def _process_tables(self) -> list[QTreeWidget]:
        """All three process tree widgets for cross-table operations."""
        return [
            self._sections.managed.tree,
            self._sections.companion.tree,
            self._sections.service.tree,
        ]

    @property
    def _process_path_str(self) -> str:
        """Absolute path string for the target executable."""
        return str(self.process_path.absolute())

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct and lay out all widgets in the main window."""
        central = QWidget(self)
        central.setObjectName('central_widget')
        layout = QGridLayout(central)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)

        self._build_top_controls(layout)
        self._build_monitor_header(layout)
        self._build_monitor_sections(layout)

        self.setCentralWidget(central)
        self._apply_stylesheet()
        self._show_process_sections()

    def _create_action_button(
        self,
        text: str,
        tooltip: str,
        callback: Callable[[], None],
        *,
        obj_name: str | None = None,
    ) -> QPushButton:
        """Create a styled action button wired to a callback."""
        btn = QPushButton(text, self)
        btn.setMinimumHeight(40)
        btn.setToolTip(tooltip)
        if obj_name is not None:
            btn.setObjectName(obj_name)
        btn.clicked.connect(  # pyright: ignore[reportUnknownMemberType]
            callback,
        )
        return btn

    def _build_top_controls(self, layout: QGridLayout) -> None:
        """Build status labels and top action buttons."""
        restart_btn = self._create_action_button(
            'Restart Adrenalin',
            'Stops Radeon Software if running,'
            ' then starts a fresh instance.',
            self.restart_software,
        )
        start_btn = self._create_action_button(
            'Start Adrenalin',
            'Starts Radeon Software if it is not already running.',
            self.start_only,
            obj_name='start_btn',
        )
        stop_btn = self._create_action_button(
            'Stop Adrenalin',
            'Stops the main Radeon Software process'
            ' and its child processes.',
            self.stop_only,
            obj_name='stop_btn',
        )
        stop_all_btn = self._create_action_button(
            'Stop all AMD processes',
            'Stops Radeon Software and all monitored'
            ' AMD helper/service processes,'
            ' including their child processes.',
            self.stop_all,
            obj_name='stop_all_btn',
        )
        stop_all_btn.setMinimumHeight(38)

        start_services_btn = self._create_action_button(
            'Start AMD Services',
            'Starts all AMD system services'
            ' (External Events, Crash Defender, etc.).',
            self.start_services,
            obj_name='start_services_btn',
        )

        layout.addWidget(restart_btn, 0, 0)
        layout.addWidget(start_btn, 0, 1)
        layout.addWidget(stop_btn, 0, 2)
        layout.addWidget(stop_all_btn, 1, 0, 1, 3)
        layout.addWidget(start_services_btn, 2, 0, 1, 3)

    def _build_monitor_header(self, layout: QGridLayout) -> None:
        """Build the live monitor heading and status badge row."""
        monitor_header = QWidget(self)
        monitor_header.setObjectName('monitor_header')
        header_layout = QHBoxLayout(monitor_header)
        header_layout.setContentsMargins(0, 4, 0, 0)
        header_layout.setSpacing(10)

        monitor_label = QLabel('Live Process Monitor', self)
        monitor_label.setObjectName('monitor_label')
        header_layout.addWidget(monitor_label)
        header_layout.addWidget(self.status_badge)
        header_layout.addStretch()
        layout.addWidget(monitor_header, 3, 0, 1, 3)

    def _build_monitor_sections(self, layout: QGridLayout) -> None:
        """Build the process monitor scroll area and section tables."""
        monitor_scroll = QScrollArea(self)
        monitor_scroll.setObjectName('monitor_scroll')
        monitor_scroll.setWidgetResizable(True)
        monitor_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        if viewport := monitor_scroll.viewport():
            viewport.setObjectName('monitor_viewport')

        monitor_content = QWidget(monitor_scroll)
        monitor_content.setObjectName('monitor_content')
        monitor_layout = QVBoxLayout(monitor_content)
        monitor_layout.setContentsMargins(0, 0, 0, 0)
        monitor_layout.setSpacing(14)

        monitor_layout.addWidget(self.managed_section)
        monitor_layout.addWidget(self.companion_section)
        monitor_layout.addWidget(self.service_section)
        monitor_layout.addStretch()

        monitor_scroll.setWidget(monitor_content)
        layout.addWidget(monitor_scroll, 4, 0, 1, 3)

    def _apply_stylesheet(self) -> None:
        """Apply the main window stylesheet."""
        self.setStyleSheet(MAIN_STYLESHEET)

    def _show_process_sections(self) -> None:
        """Ensure all process sections are visible after UI construction."""
        self.managed_section.show()
        self.companion_section.show()
        self.service_section.show()

    # ------------------------------------------------------------------
    # Tree widget configuration
    # ------------------------------------------------------------------

    def _configure_common_view_interactions(
        self,
        view: QTreeWidget,
    ) -> None:
        """Apply shared selection, copy, and tracking settings to a view."""
        view.setMouseTracking(True)
        if viewport := view.viewport():
            viewport.setMouseTracking(True)
        view.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        view.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        view.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectItems)
        view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        copy_action = QAction(view)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

        def _on_copy(_checked: bool = False, v: QTreeWidget = view) -> None:
            copy_selected_cells(v)

        copy_action.triggered.connect(_on_copy)  # pyright: ignore[reportUnknownMemberType]
        view.addAction(copy_action)  # pyright: ignore[reportUnknownMemberType]
        view.itemSelectionChanged.connect(  # pyright: ignore[reportUnknownMemberType]
            lambda current_view=view:
                self._enforce_single_table_selection(current_view),
        )

    def _configure_process_tree_interactions(self, tree: QTreeWidget) -> None:
        """Enable selection, copy, and context menu on a process tree."""
        self._configure_common_view_interactions(tree)
        _ctx_signal = tree.customContextMenuRequested

        def _on_ctx_menu(pos: QPoint, t: QTreeWidget = tree) -> None:
            self.show_tree_context_menu(t, pos)

        def _on_expand(_idx: QModelIndex, t: QTreeWidget = tree) -> None:
            self._resize_tree_widget(t)

        def _on_collapse(_idx: QModelIndex, t: QTreeWidget = tree) -> None:
            self._resize_tree_widget(t)

        _ctx_signal.connect(_on_ctx_menu)  # pyright: ignore[reportUnknownMemberType]
        tree.expanded.connect(_on_expand)  # pyright: ignore[reportUnknownMemberType]
        tree.collapsed.connect(_on_collapse)  # pyright: ignore[reportUnknownMemberType]

    def _enforce_single_table_selection(
        self,
        active_table: QTreeWidget,
    ) -> None:
        """Clear selections in other process tables when active_table has selection."""
        if not active_table.selectedIndexes():
            return

        for table in self._process_tables:
            if table is active_table:
                continue

            if table.selectedIndexes():
                table.clearSelection()

    # ------------------------------------------------------------------
    # Section creation
    # ------------------------------------------------------------------

    def _create_process_section(
        self,
        parent: QWidget,
        title: str,
        description: str,
    ) -> tuple[QWidget, QTreeWidget]:
        """Create a labeled process section with a dedicated tree widget."""
        section = QWidget(parent)
        section.setObjectName('process_section')
        section.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(12, 12, 12, 12)
        section_layout.setSpacing(8)

        label = QLabel(title, section)
        label.setObjectName('section_header')
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        count_label = QLabel('(0)', section)
        count_label.setObjectName('section_count')
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        description_label = QLabel(description, section)
        description_label.setObjectName('section_description')
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        tree = QTreeWidget(section)
        tree.setObjectName('process_tree')
        tree.setColumnCount(6)
        tree.setHeaderLabels(  # pyright: ignore[reportUnknownMemberType]
            ['Name', 'Path', 'PID', 'CPU %', 'Memory', 'Status'],
        )
        if header := tree.header():
            self._configure_section_header_resize(header)
        tree.setRootIsDecorated(True)
        tree.setIndentation(20)
        tree.setUniformRowHeights(True)
        tree.setAnimated(False)
        self._configure_process_tree_interactions(tree)
        tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        header_row = QWidget(section)
        header_row_layout = QHBoxLayout(header_row)
        header_row_layout.setContentsMargins(0, 0, 0, 0)
        header_row_layout.setSpacing(6)
        header_row_layout.addStretch()
        header_row_layout.addWidget(label)
        header_row_layout.addWidget(count_label)
        header_row_layout.addStretch()

        section_layout.addWidget(header_row)
        section_layout.addWidget(description_label)
        section_layout.addWidget(tree)
        return section, tree

    def _create_managed_section(
        self,
        parent: QWidget,
        title: str,
        description: str,
    ) -> tuple[QWidget, QTreeWidget]:
        """Create the managed process section with a tree widget for hierarchy."""
        section = QWidget(parent)
        section.setObjectName('process_section')
        section.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(12, 12, 12, 12)
        section_layout.setSpacing(8)

        label = QLabel(title, section)
        label.setObjectName('section_header')
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        count_label = QLabel('(0)', section)
        count_label.setObjectName('section_count')
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        description_label = QLabel(description, section)
        description_label.setObjectName('section_description')
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        tree = QTreeWidget(section)
        tree.setObjectName('process_tree')
        tree.setColumnCount(6)
        tree.setHeaderLabels(  # pyright: ignore[reportUnknownMemberType]
            ['Name', 'Path', 'PID', 'CPU %', 'Memory', 'Status'],
        )
        if header := tree.header():
            self._configure_section_header_resize(header)
        tree.setRootIsDecorated(True)
        tree.setIndentation(20)
        tree.setUniformRowHeights(True)
        tree.setAnimated(False)
        self._configure_managed_tree_interactions(tree)
        tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        header_row = QWidget(section)
        header_row_layout = QHBoxLayout(header_row)
        header_row_layout.setContentsMargins(0, 0, 0, 0)
        header_row_layout.setSpacing(6)
        header_row_layout.addStretch()
        header_row_layout.addWidget(label)
        header_row_layout.addWidget(count_label)
        header_row_layout.addStretch()

        section_layout.addWidget(header_row)
        section_layout.addWidget(description_label)
        section_layout.addWidget(tree)
        return section, tree

    def _configure_managed_tree_interactions(self, tree: QTreeWidget) -> None:
        """Enable selection, copy, expand/collapse and context menu on the tree."""
        self._configure_common_view_interactions(tree)
        _ctx_signal = tree.customContextMenuRequested
        _ctx_signal.connect(  # pyright: ignore[reportUnknownMemberType]
            self.show_managed_tree_context_menu,
        )

        def _on_managed_expand(_idx: QModelIndex) -> None:
            self._resize_managed_tree()

        def _on_managed_collapse(_idx: QModelIndex) -> None:
            self._resize_managed_tree()

        tree.expanded.connect(_on_managed_expand)  # pyright: ignore[reportUnknownMemberType]
        tree.collapsed.connect(_on_managed_collapse)  # pyright: ignore[reportUnknownMemberType]

    @staticmethod
    def _configure_section_header_resize(header: QHeaderView) -> None:
        """Set standard column resize modes for process section headers."""
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (2, 3, 4, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
