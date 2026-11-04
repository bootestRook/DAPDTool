from PySide6.QtWidgets import QDialog, QHBoxLayout, QLineEdit, QVBoxLayout
from ..controls import label, button
from ..runner import Runner
from dapd_api import with_api


class ConnectionDialog(QDialog):
    def __init__(self, store, activity, parent=None):
        super().__init__(parent)
        self.store = store
        self.projects = None
        self.setWindowTitle("连接 DAPD")
        self.setMinimumWidth(550)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(label("连接 DAPD", "section"))
        layout.addWidget(label("在 DAPD 的个人设置 → 安全设置中生成 API Key。", "muted"))
        layout.addWidget(label("API Key"))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("粘贴完整的 dapd_ 开头的 API Key")
        self.key.setAccessibleName("DAPD API Key")
        try:
            self.key.setText(store.load_key())
        except ValueError:
            pass
        layout.addWidget(self.key)
        layout.addWidget(label("密钥使用 Windows 加密保存在本机。程序包不包含任何账号密钥。", "muted"))
        self.status = label("")
        layout.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch()
        self.cancel = button("取消", self.reject)
        self.save = button("验证并保存", self.connect_key, True)
        row.addWidget(self.cancel)
        row.addWidget(self.save)
        layout.addLayout(row)
        self.runner = Runner(self, activity)
        self.runner.busyChanged.connect(self.busy_changed)
        self.key.returnPressed.connect(self.connect_key)

    def busy_changed(self, busy):
        self.key.setEnabled(not busy)
        self.cancel.setEnabled(not busy)
        self.save.setEnabled(not busy)
        if not busy and self.projects is not None:
            self.accept()

    def connect_key(self):
        import re
        key = self.key.text().strip()
        if not re.fullmatch(r"dapd_[0-9a-f]{64}", key):
            self.status.setText("API Key 格式不正确，请复制完整密钥。")
            return
        self.status.setText("正在验证连接…")
        def save(_):
            projects = with_api(key, lambda api: api.projects())
            self.store.save_key(key)
            return projects
        self.runner.start(save, self.connected, self.status.setText)

    def connected(self, projects):
        self.projects = projects

    def reject(self):
        if not self.runner.busy:
            super().reject()
