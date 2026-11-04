"""Own a creation batch's execution, cancellation and progress notifications."""
import threading

from PySide6.QtCore import QObject, Signal

from dapd_api import with_api
from ..engine import run_job
from ..records import STATUS


class JobController(QObject):
    started = Signal(str)
    progressChanged = Signal(object)
    statusChanged = Signal(str)
    changed = Signal()
    failed = Signal()

    def __init__(self, store, session, runner, parent=None):
        super().__init__(parent)
        self.store = store
        self.session = session
        self.runner = runner
        self.active_job = None
        self.stop_event = threading.Event()

    def create(self, plan):
        if not self.runner.busy:
            self.start(self.store.add_job(plan))

    def start(self, identifier):
        if self.runner.busy:
            return False
        self.active_job = identifier
        self.stop_event.clear()
        key = self.session.key
        self.started.emit(identifier)
        self.statusChanged.emit("正在创建任务…")
        self.changed.emit()
        return self.runner.start(
            lambda update: with_api(key, lambda api: run_job(
                self.store, api, identifier, self.stop_event, update)),
            self.completed, self.error, self.progress,
        )

    def progress(self, job):
        done = sum(node["status"] == "created" for node in job["nodes"])
        self.statusChanged.emit(f"已创建并核对 {done} / {len(job['nodes'])} 个任务。")
        self.progressChanged.emit(job)

    def completed(self, job):
        self.progress(job)
        if job["status"] == "completed":
            text = f"创建完成：{len(job['nodes'])} 个任务。可选中任务打开 DAPD，或导出创建记录。"
        else:
            text = f"{STATUS[job['status']]}。{job['error'] or '已成功的任务已保留，可稍后继续。'}"
        self.active_job = None
        self.statusChanged.emit(text)
        self.changed.emit()

    def error(self, text):
        self.active_job = None
        self.statusChanged.emit(text)
        self.failed.emit()
        self.changed.emit()

    def stop(self):
        if self.active_job:
            self.stop_event.set()
            self.statusChanged.emit("正在停止：等待当前请求结束，然后保留进度。")
            self.changed.emit()
