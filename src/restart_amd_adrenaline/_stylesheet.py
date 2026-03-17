"""Application stylesheet for the AMD Adrenalin Control main window."""

MAIN_STYLESHEET: str = """
QMainWindow {
    background-color: #0f141d;
}
QWidget#central_widget,
QWidget#monitor_content,
QWidget#monitor_viewport {
    background-color: #0f141d;
}
QLabel {
    color: #e9eef8;
    font-size: 13px;
}
QPushButton {
    background-color: #1f6feb;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    padding: 8px 12px;
}
QPushButton:hover {
    background-color: #3a82f7;
}
QPushButton:pressed {
    background-color: #1759bf;
}
QPushButton#start_btn {
    background-color: #15803d;
}
QPushButton#start_btn:hover {
    background-color: #16a34a;
}
QPushButton#start_btn:pressed {
    background-color: #166534;
}
QPushButton#stop_btn {
    background-color: #b91c1c;
}
QPushButton#stop_btn:hover {
    background-color: #dc2626;
}
QPushButton#stop_btn:pressed {
    background-color: #991b1b;
}
QPushButton#stop_all_btn {
    background-color: #7f1d1d;
    border: 1px solid #991b1b;
}
QPushButton#stop_all_btn:hover {
    background-color: #991b1b;
}
QPushButton#stop_all_btn:pressed {
    background-color: #7a1616;
}
QTableWidget#process_table {
    background-color: #0d1220;
    color: #c9d8f0;
    border: 1px solid #1e2d45;
    border-radius: 6px;
    gridline-color: #1a2540;
    font-size: 12px;
    outline: 0;
}
QTableWidget#process_table::item {
    padding: 6px 10px;
    border: none;
}
QTableWidget#process_table::item:hover {
    background-color: #233a5d;
    color: #f4f8ff;
}
QTableWidget#process_table::item:selected {
    background-color: #1c2e4a;
    color: #e9eef8;
}
QTableWidget#process_table::item:selected:hover {
    background-color: #294874;
    color: #f4f8ff;
}
QHeaderView::section {
    background-color: #141c2e;
    color: #6a9fd8;
    font-size: 11px;
    font-weight: 700;
    padding: 6px 10px;
    border: none;
    border-bottom: 1px solid #1e2d45;
}
QHeaderView::section:vertical {
    width: 0px;
    padding: 0px;
    margin: 0px;
    border: none;
    background: transparent;
    color: transparent;
}
QTableCornerButton::section {
    border: none;
    background: transparent;
}
QMenu {
    background-color: #0d1220;
    color: #e9eef8;
    border: 1px solid #1e2d45;
    padding: 6px;
}
QMenu::item {
    padding: 6px 20px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #1c2e4a;
}
QMenu::separator {
    height: 1px;
    background: #4f6b90;
    margin: 6px 10px;
}
QLabel#monitor_label {
    color: #6a9fd8;
    font-size: 11px;
    font-weight: 700;
}
QLabel#section_header {
    color: #6a9fd8;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.6px;
}
QLabel#section_description {
    color: #8ea7c7;
    font-size: 11px;
}
QLabel#badge_running {
    color: #22c55e;
    font-size: 11px;
    font-weight: 700;
}
QLabel#badge_stopped {
    color: #ef4444;
    font-size: 11px;
    font-weight: 700;
}
QWidget#process_section {
    background-color: #0b111d;
    border: 1px solid #182338;
    border-radius: 8px;
}
QScrollArea {
    background: transparent;
}
QScrollArea#monitor_scroll {
    border: none;
    background-color: #0f141d;
}
"""
