LIGHT_THEME = """
QMainWindow, QWidget {
    background: #f7f8fb;
    color: #111827;
    font-family: Inter, Segoe UI, Arial;
    font-size: 13px;
}
QFrame#Sidebar {
    background: #ffffff;
    border-right: 1px solid #e5e7eb;
}
QLabel#Brand {
    font-size: 22px;
    font-weight: 700;
    color: #111827;
}
QLabel#MetricValue {
    font-size: 22px;
    font-weight: 700;
}
QLabel#SectionTitle {
    font-size: 16px;
    font-weight: 700;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QDateEdit {
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 8px;
    padding: 7px 9px;
    selection-background-color: #2563eb;
}
QPushButton {
    background: #111827;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 13px;
    font-weight: 600;
}
QPushButton:hover { background: #1f2937; }
QPushButton:pressed { background: #374151; }
QPushButton#SecondaryButton {
    background: #ffffff;
    color: #111827;
    border: 1px solid #d8dee8;
}
QTableWidget {
    background: #ffffff;
    gridline-color: #eef2f7;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
}
QHeaderView::section {
    background: #f3f4f6;
    color: #374151;
    border: none;
    padding: 8px;
    font-weight: 700;
}
QListWidget {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget::item {
    border-radius: 8px;
    margin: 3px 10px;
    padding: 10px;
}
QListWidget::item:selected {
    background: #111827;
    color: #ffffff;
}
QTabWidget::pane {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #ffffff;
}
QTabBar::tab {
    padding: 9px 14px;
    margin-right: 4px;
    border-radius: 8px;
}
QTabBar::tab:selected {
    background: #111827;
    color: #ffffff;
}
"""

DARK_THEME = """
QMainWindow, QWidget {
    background: #0e1116;
    color: #e5e7eb;
    font-family: Inter, Segoe UI, Arial;
    font-size: 13px;
}
QFrame#Sidebar {
    background: #121720;
    border-right: 1px solid #252d3a;
}
QLabel#Brand {
    font-size: 22px;
    font-weight: 700;
    color: #ffffff;
}
QLabel#MetricValue {
    font-size: 22px;
    font-weight: 700;
}
QLabel#SectionTitle {
    font-size: 16px;
    font-weight: 700;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QDateEdit {
    background: #151b24;
    border: 1px solid #2d3645;
    border-radius: 8px;
    padding: 7px 9px;
    selection-background-color: #3b82f6;
}
QPushButton {
    background: #f9fafb;
    color: #111827;
    border: none;
    border-radius: 8px;
    padding: 8px 13px;
    font-weight: 600;
}
QPushButton:hover { background: #e5e7eb; }
QPushButton:pressed { background: #d1d5db; }
QPushButton#SecondaryButton {
    background: #151b24;
    color: #e5e7eb;
    border: 1px solid #2d3645;
}
QTableWidget {
    background: #151b24;
    gridline-color: #252d3a;
    border: 1px solid #252d3a;
    border-radius: 8px;
}
QHeaderView::section {
    background: #10151d;
    color: #cbd5e1;
    border: none;
    padding: 8px;
    font-weight: 700;
}
QListWidget {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget::item {
    border-radius: 8px;
    margin: 3px 10px;
    padding: 10px;
}
QListWidget::item:selected {
    background: #f9fafb;
    color: #111827;
}
QTabWidget::pane {
    border: 1px solid #252d3a;
    border-radius: 8px;
    background: #151b24;
}
QTabBar::tab {
    padding: 9px 14px;
    margin-right: 4px;
    border-radius: 8px;
}
QTabBar::tab:selected {
    background: #f9fafb;
    color: #111827;
}
"""
