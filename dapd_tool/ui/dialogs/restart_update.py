"""Offer an immediate restart or count down while all background work is idle."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout

from ..controls import button, label


class RestartUpdateDialog(QDialog):
    def __init__(self, activity, parent=None):
        super().__init__(parent)
        self.activity = activity
        self.remaining = 5
        self.setWindowTitle("程序更新已准备好")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(label("程序更新已下载并校验完成", "section"))
        layout.addWidget(label("将在 5 秒后重启并安装更新，安装后自动重新打开。\n已保存的模板、密钥和记录会保留；未提交的输入需要重新填写。", "muted"))
        self.status = label("")
        layout.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch()
        self.later_button = button("稍后重启", self.reject)
        row.addWidget(self.later_button)
        self.restart_button = button("", self.restart, True)
        self.restart_button.setMinimumWidth(200)
        row.addWidget(self.restart_button)
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.finished.connect(self.timer.stop)
        activity.changed.connect(self.busy_changed)
        self.busy_changed()

    def showEvent(self, event):
        super().showEvent(event)
        self.busy_changed()

    def busy_changed(self, *_):
        self.timer.stop()
        self.remaining = 5
        busy = self.activity.busy
        self.restart_button.setEnabled(not busy)
        if busy:
            self.restart_button.setText("等待当前操作结束")
            self.status.setText("当前仍有操作正在进行，结束后将重新开始 5 秒倒计时。")
        else:
            self.restart_button.setText("立即重启（5 秒后自动）")
            self.status.setText("可以立即重启，或选择稍后重启。")
            if self.isVisible():
                self.timer.start()

    def tick(self):
        if self.activity.busy:
            self.busy_changed()
            return
        self.remaining -= 1
        if self.remaining <= 0:
            self.restart()
        else:
            self.restart_button.setText(f"立即重启（{self.remaining} 秒后自动）")

    def restart(self):
        if self.activity.busy:
            self.busy_changed()
            return
        self.accept()
