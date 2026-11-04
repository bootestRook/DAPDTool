from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QMessageBox


def label(text, kind=None):
    result = QLabel(text)
    result.setWordWrap(True)
    result.setTextFormat(Qt.TextFormat.PlainText)
    if kind:
        result.setObjectName(kind)
    return result


def button(text, action, primary=False):
    result = QPushButton(text)
    result.setAutoDefault(False)
    if primary:
        result.setObjectName("primary")
    result.clicked.connect(action)
    return result


def message(parent, text):
    box = QMessageBox(parent)
    box.setWindowTitle("DAPD 任务工具")
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Information)
    box.addButton("知道了", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def confirm(parent, text, action="确认"):
    box = QMessageBox(parent)
    box.setWindowTitle("请核对")
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(text)
    yes = box.addButton(action, QMessageBox.ButtonRole.AcceptRole)
    no = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(no)
    box.exec()
    return box.clickedButton() is yes
