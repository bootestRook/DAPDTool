from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from dapd_api import task_url


def open_task(identifier):
    if identifier:
        QDesktopServices.openUrl(QUrl(task_url(identifier)))
