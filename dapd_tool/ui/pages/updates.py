from PySide6.QtCore import Signal
import uuid
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget
from ...content_packs import install_pack, load_shared
from ...updates import ProgramUpdater, ReleaseClient, auto_check_due, record_check, update_error, version_tuple
from ..runner import Runner
from ..controls import button, label, message
from ..dialogs.restart_update import RestartUpdateDialog


class UpdatesPage(QWidget):
    templatesChanged = Signal()
    availableChanged = Signal(bool)
    restartRequested = Signal()

    def __init__(self, store, activity, parent=None):
        super().__init__(parent)
        self.store, self.activity = store, activity
        self.runner = Runner(self, activity)
        self.updater = ProgramUpdater()
        self.available = {"program": None, "content": None}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(12)
        row = QHBoxLayout()
        row.addWidget(label("来自 bootestRook/DAPDTool 的公开发布。启动时每天检查一次。", "muted"), 1)
        self.check_button = button("检查更新", self.check)
        row.addWidget(self.check_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(label("程序更新", "section"), 1)
        self.program_action = button("下载程序更新", self.program_clicked, True)
        row.addWidget(self.program_action)
        layout.addLayout(row)
        self.program_status = label(f"当前版本 {self.updater.current_version} · 尚未检查", "muted")
        layout.addWidget(self.program_status)
        self.program_notes = QPlainTextEdit()
        self.program_notes.setReadOnly(True)
        self.program_notes.setAccessibleName("程序更新说明")
        self.program_notes.setPlaceholderText("检查后显示程序版本与更新说明。")
        layout.addWidget(self.program_notes, 1)
        row = QHBoxLayout()
        row.addWidget(label("共享模板与素材", "section"), 1)
        self.content_action = button("同步共享内容", self.sync_content)
        row.addWidget(self.content_action)
        layout.addLayout(row)
        self.content_status = label("", "muted")
        layout.addWidget(self.content_status)
        self.content_notes = QPlainTextEdit()
        self.content_notes.setReadOnly(True)
        self.content_notes.setAccessibleName("共享内容更新说明")
        self.content_notes.setPlaceholderText("发布者上传内容包后，可在这里同步模板、图片和附件。")
        layout.addWidget(self.content_notes, 1)
        layout.addWidget(label("共享模板可直接创建任务；复制为个人模板后可编辑。同步只更新共享库。", "muted"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.status = label("检查更新后可分别下载程序或同步内容。", "muted")
        layout.addWidget(self.status)
        self.runner.busyChanged.connect(self.refresh_actions)
        activity.changed.connect(self.refresh_actions)
        self.refresh_content_status()
        self.refresh_actions()

    def refresh_content_status(self):
        try:
            self.content_version = load_shared(self.store.directory)["version"]
            self.content_status.setText(f"已同步版本 {self.content_version}" if self.content_version else "尚未同步共享内容")
        except Exception:
            self.content_version = None
            self.content_status.setText("本地共享目录无法读取，请重新同步。")

    def refresh_actions(self, *_):
        busy = self.runner.busy
        self.check_button.setEnabled(not busy)
        ready, program = bool(self.updater.ready), self.available["program"]
        newer = bool(program and version_tuple(program["version"]) > version_tuple(self.updater.current_version))
        self.program_action.setText("重启并安装更新" if ready else "下载程序更新")
        self.program_action.setEnabled(not busy and self.updater.installed and (ready or newer) and not (ready and self.activity.busy))
        content = self.available["content"]
        newer_content = bool(content and (not self.content_version or version_tuple(content["version"]) > version_tuple(self.content_version)))
        self.content_action.setEnabled(not busy and newer_content)
        self.availableChanged.emit(bool(ready or newer or newer_content))
        if ready and self.activity.busy:
            self.status.setText("程序已下载，当前操作结束后可重启安装。")
        elif ready and not busy and self.status.text() in {
                "程序已下载，当前操作结束后可重启安装。", "请等待当前操作结束后再安装程序更新。"}:
            self.status.setText("当前操作已结束，程序已下载。可以点击“重启并安装更新”。")

    def start(self):
        if self.updater.ready:
            self.status.setText("已下载的程序更新待安装，空闲时点击“重启并安装更新”。")
        if auto_check_due(self.store.directory):
            QTimer.singleShot(3000, self.check)

    def operation(self, function, result, *, progress=False):
        def run(update):
            try:
                return function(update)
            except Exception as exc:
                raise ValueError(update_error(exc)) from None
        self.progress.setRange(0, 100 if progress else 0)
        self.progress.setValue(0)
        def success(value):
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            result(value)
        def failed(text):
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.status.setText(text)
        self.runner.start(run, success, failed, self.progress.setValue)

    def check(self):
        if self.runner.busy:
            return
        self.status.setText("正在检查程序与共享内容版本…")
        def fetch(_):
            with ReleaseClient() as client:
                return client.releases()
        self.operation(fetch, self.checked)

    def checked(self, available):
        self.available = available
        record_check(self.store.directory)
        program, content = available["program"], available["content"]
        found = False
        if program:
            newer = version_tuple(program["version"]) > version_tuple(self.updater.current_version)
            self.program_status.setText(f"当前 {self.updater.current_version} · {'可更新至' if newer else '最新发布'} {program['version']}")
            self.program_notes.setPlainText(program["notes"])
            found |= newer
        else:
            self.program_status.setText(f"当前 {self.updater.current_version} · 发布者尚未上传程序更新")
        if not self.updater.installed:
            self.program_status.setText(self.program_status.text() + "\n请运行完整便携包中的程序，以启用软件内升级。")
        self.refresh_content_status()
        if content:
            self.content_status.setText(self.content_status.text() + f" · 最新发布 {content['version']}")
            self.content_notes.setPlainText(content["notes"])
            found |= not self.content_version or version_tuple(content["version"]) > version_tuple(self.content_version)
        else:
            self.content_notes.setPlainText("发布者尚未发布共享内容。可以继续使用个人模板。")
        self.status.setText("发现新版本，可分别更新程序或同步共享内容。" if found else "检查完成，当前没有需要下载的更新。")
        self.refresh_actions()

    def program_clicked(self):
        if self.runner.busy:
            return
        if self.updater.ready:
            if self.activity.busy:
                self.status.setText("请等待当前操作结束后再安装程序更新。")
                return
            self.prompt_restart()
            return
        release = self.available["program"]
        if release:
            self.status.setText("正在下载并校验程序更新，可继续查看其他页面。")
            self.operation(lambda update: self.updater.download(release, update),
                           self.program_downloaded, progress=True)

    def program_downloaded(self, _):
        self.status.setText("程序已下载并校验，准备重启安装更新。")
        self.refresh_actions()
        self.prompt_restart()

    def prompt_restart(self):
        dialog = RestartUpdateDialog(self.activity, self)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.status.setText("程序更新已准备好，稍后可点击“重启并安装更新”。")
                return
        finally:
            dialog.deleteLater()
        # A new operation can start while the modal dialog is closing.
        if self.activity.busy:
            self.status.setText("请等待当前操作结束后再安装程序更新。")
            return
        try:
            self.updater.launch_update()
            self.restartRequested.emit()
        except Exception as exc:
            self.status.setText(update_error(exc))

    def sync_content(self):
        release = self.available["content"]
        if not release or self.runner.busy:
            return
        self.status.setText("正在下载并校验共享模板与素材…")
        def sync(update):
            cache = self.store.directory / "downloads"
            cache.mkdir(parents=True, exist_ok=True)
            package = cache / (uuid.uuid4().hex + ".zip")
            try:
                with ReleaseClient() as client:
                    client.download_content(release, package, update)
                return install_pack(self.store.directory, package, release["version"], self.updater.current_version)
            finally:
                package.unlink(missing_ok=True)
        def done(result):
            self.refresh_content_status()
            self.templatesChanged.emit()
            self.status.setText(f"共享内容 {result['version']} 已同步：{result['templates']} 个模板、{result['files']} 个文件。")
            self.refresh_actions()
            message(self, self.status.text() + "\n现在可直接使用，无需重启。")
        self.operation(sync, done, progress=True)
