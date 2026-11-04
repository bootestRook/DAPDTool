"""Connect an account and refresh its project catalog."""
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog

from dapd_api import with_api
from .dialogs.connection import ConnectionDialog


class ConnectionController(QObject):
    statusChanged = Signal(str)
    loading = Signal()

    def __init__(self, store, session, runner, parent=None):
        super().__init__(parent)
        self.store, self.session, self.runner = store, session, runner

    def start(self):
        try:
            self.session.set_key(self.store.load_key())
        except ValueError as exc:
            self.statusChanged.emit(str(exc))
        if self.session.key:
            self.refresh()

    def configure(self, parent):
        if self.runner.busy:
            return
        dialog = ConnectionDialog(self.store, self.runner.activity, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.session.set_key(self.store.load_key())
            self.session.set_projects(dialog.projects)
            self.statusChanged.emit("连接成功，请选择项目和任务组。")

    def refresh(self):
        if not self.session.key or self.runner.busy:
            return
        key = self.session.key
        self.loading.emit()
        self.statusChanged.emit("正在读取 DAPD 项目…")
        self.runner.start(lambda _: with_api(key, lambda api: api.projects()),
                          self.loaded, self.statusChanged.emit)

    def loaded(self, projects):
        self.session.set_projects(projects)
        self.statusChanged.emit(f"已读取 {len(projects)} 个项目。")
