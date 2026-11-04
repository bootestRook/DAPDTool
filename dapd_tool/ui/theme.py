from PySide6.QtCore import QObject, QEvent
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QStyle


STYLE = """
QWidget { font-family: 'Microsoft YaHei UI'; font-size: 10pt; color: #253440; }
QMainWindow, QDialog { background: #f4f6f8; }
QLabel { background: transparent; }
QLabel#heading { font-size: 20pt; font-weight: 600; color: #183c4a; }
QLabel#section { font-size: 12pt; font-weight: 600; }
QLabel#muted { color: #566875; }
QLabel#notice { background: #e9f2f3; padding: 12px; color: #244e58; border-radius: 6px; }
QLabel#updateDot { background: #c9363e; border-radius: 4px; }
QPushButton { background: #fff; border: 1px solid #b9c6cd; border-radius: 5px; padding: 7px 14px; min-height: 20px; }
QPushButton:hover { background: #edf3f5; border-color: #728d98; }
QPushButton:pressed { background: #dce9ed; }
QPushButton:focus { border: 2px solid #147788; padding: 6px 13px; }
QPushButton:disabled { color: #78868e; background: #edf0f2; border-color: #d3dce0; }
QPushButton#primary { background: #146979; border-color: #146979; color: #fff; font-weight: 600; }
QPushButton#primary:hover { background: #0f5866; }
QPushButton#primary:disabled { background: #90afb5; border-color: #90afb5; color: #f5f8f9; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QTreeView, QListWidget { background: #fff; border: 1px solid #bdcad1; border-radius: 4px; selection-background-color: #d8edef; selection-color: #183c4a; }
QLineEdit, QPlainTextEdit, QTextEdit { placeholder-text-color: #566875; }
QLineEdit, QComboBox { padding: 7px 9px; min-height: 20px; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QTreeView:focus, QListWidget:focus { border: 1px solid #147788; }
QLineEdit:disabled, QComboBox:disabled { color: #78868e; background: #edf0f2; }
QComboBox QAbstractItemView { background: white; selection-background-color: #d8edef; }
QTreeView::item, QListWidget::item { padding: 7px 4px; min-height: 22px; }
QTreeView::item:selected, QListWidget::item:selected { background: #d8edef; color: #183c4a; }
QHeaderView::section { background: #edf2f5; border: none; border-bottom: 1px solid #ced8dd; padding: 9px; font-weight: 600; }
QTabWidget::pane { border: 0; background: #f4f6f8; }
QTabBar::tab { background: transparent; border-bottom: 2px solid transparent; padding: 12px 25px; color: #566875; }
QTabBar::tab:selected { color: #125d6c; border-bottom-color: #146979; font-weight: 600; }
QTabBar::tab:focus { background: #e2edf0; }
QProgressBar { background: #e3eaee; border: none; border-radius: 3px; text-align: center; min-height: 8px; }
QProgressBar::chunk { background: #146979; border-radius: 3px; }
QSplitter::handle { background: #e0e7eb; }
"""


class NoTooltips(QObject):
    def eventFilter(self, obj, event):
        return event.type() == QEvent.Type.ToolTip


def configure_app(app):
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setWindowIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
    app.setStyleSheet(STYLE)
    app.no_tooltips = NoTooltips(app)
    app.installEventFilter(app.no_tooltips)
