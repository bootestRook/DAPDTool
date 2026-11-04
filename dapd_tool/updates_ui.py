"""Native update controls and the shared-content export dialog."""
from pathlib import Path
import uuid
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget)
from .content_packs import export_pack, install_pack, load_shared
from .updates import ProgramUpdater, ReleaseClient, auto_check_due, record_check, update_error, version_tuple
from .ui import Runner, button, confirm, label, message


class UpdatesPage(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.runner = Runner(self)
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
        window.runner.busyChanged.connect(self.refresh_actions)
        self.refresh_content_status()
        self.refresh_actions()

    def refresh_content_status(self):
        try:
            self.content_version = load_shared(self.window.store.directory)["version"]
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
        self.program_action.setEnabled(not busy and self.updater.installed and (ready or newer) and not (ready and self.window.runner.busy))
        content = self.available["content"]
        newer_content = bool(content and (not self.content_version or version_tuple(content["version"]) > version_tuple(self.content_version)))
        self.content_action.setEnabled(not busy and newer_content)
        index = self.window.tabs.indexOf(self)
        if index >= 0:
            self.window.tabs.setTabText(index, "更新与共享（有更新）" if ready or newer or newer_content else "更新与共享")
        if ready and self.window.runner.busy:
            self.status.setText("程序已下载，当前操作结束后可重启安装。")
        elif ready and not busy and self.status.text() in {
                "程序已下载，当前操作结束后可重启安装。", "请等待当前操作结束后再安装程序更新。"}:
            self.status.setText("当前操作已结束，程序已下载。可以点击“重启并安装更新”。")

    def start(self):
        if self.updater.ready:
            self.status.setText("已下载的程序更新待安装，空闲时点击“重启并安装更新”。")
        if auto_check_due(self.window.store.directory):
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
        record_check(self.window.store.directory)
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
        self.window.tabs.setTabText(self.window.tabs.indexOf(self), "更新与共享（有更新）" if found else "更新与共享")
        self.status.setText("发现新版本，可分别更新程序或同步共享内容。" if found else "检查完成，当前没有需要下载的更新。")
        self.refresh_actions()

    def program_clicked(self):
        if self.updater.ready:
            if self.window.runner.busy or self.runner.busy:
                self.status.setText("请等待当前操作结束后再安装程序更新。")
                return
            if not confirm(self, "即将关闭并更新程序，完成后自动重新打开。\n已保存的模板、密钥和记录会保留；尚未提交的标题输入需要重新填写。", "重启并安装"):
                return
            try:
                self.updater.launch_update()
                self.window.close()
            except Exception as exc:
                self.status.setText(update_error(exc))
            return
        release = self.available["program"]
        if release:
            self.status.setText("正在下载并校验程序更新，可继续查看其他页面。")
            self.operation(lambda update: self.updater.download(release, update),
                           lambda _: self.status.setText("程序已下载并校验。空闲时点击“重启并安装更新”。"), progress=True)

    def sync_content(self):
        release = self.available["content"]
        if not release or self.runner.busy:
            return
        self.status.setText("正在下载并校验共享模板与素材…")
        def sync(update):
            cache = self.window.store.directory / "downloads"
            cache.mkdir(parents=True, exist_ok=True)
            package = cache / (uuid.uuid4().hex + ".zip")
            try:
                with ReleaseClient() as client:
                    client.download_content(release, package, update)
                return install_pack(self.window.store.directory, package, release["version"], self.updater.current_version)
            finally:
                package.unlink(missing_ok=True)
        def done(result):
            self.refresh_content_status()
            self.window.refresh_templates()
            self.status.setText(f"共享内容 {result['version']} 已同步：{result['templates']} 个模板、{result['files']} 个文件。")
        self.operation(sync, done, progress=True)


class ExportContentDialog(QDialog):
    def __init__(self, store, parent):
        super().__init__(parent)
        self.store = store
        self.runner = Runner(self)
        self.runner.busyChanged.connect(self.busy_changed)
        self.setWindowTitle("导出共享内容包")
        self.resize(600, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(label("勾选要发布的个人模板。导出包包含对应描述、图片和附件；上传公开仓库后任何人都可下载。", "notice"))
        self.templates = QListWidget()
        self.templates.setAccessibleName("选择要发布的模板")
        for template in store.templates():
            item = QListWidgetItem(template["name"])
            item.setData(Qt.ItemDataRole.UserRole, template)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.templates.addItem(item)
        layout.addWidget(self.templates, 1)
        form = QFormLayout()
        self.version = QLineEdit()
        self.version.setPlaceholderText("例如 1.0.0，每次发布递增")
        form.addRow("内容版本", self.version)
        layout.addLayout(form)
        layout.addWidget(label("更新说明"))
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(100)
        layout.addWidget(self.notes)
        self.status = label("勾选模板后选择导出位置。清空勾选可发布空共享库。", "muted")
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.cancel_button = button("取消", self.reject)
        row.addWidget(self.cancel_button)
        row.addStretch()
        self.export_button = button("导出内容包", self.export, True)
        row.addWidget(self.export_button)
        layout.addLayout(row)

    def busy_changed(self, busy):
        for widget in (self.templates, self.version, self.notes, self.cancel_button, self.export_button):
            widget.setEnabled(not busy)

    def reject(self):
        if not self.runner.busy:
            super().reject()

    def closeEvent(self, event):
        if self.runner.busy:
            event.ignore()
        else:
            super().closeEvent(event)

    def export(self):
        if self.runner.busy:
            return
        try:
            version = self.version.text().strip()
            version_tuple(version)
            selected = [self.templates.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.templates.count())
                        if self.templates.item(i).checkState() == Qt.CheckState.Checked]
            if not selected and not confirm(self, "未勾选模板。发布空内容包后，同事同步时共享库将变为空，个人模板保留。", "导出空共享库"):
                return
            folder = QFileDialog.getExistingDirectory(self, "选择内容包保存文件夹")
            if not folder:
                return
            path = Path(folder) / f"dapd-content-{version}.zip"
            if path.exists() and not confirm(self, f"覆盖已有内容包 {path.name}？", "覆盖"):
                return
            notes = self.notes.toPlainText()
            self.status.setText("正在校验素材并导出，请等待完成…")
            def run(_):
                try:
                    return export_pack(self.store.directory, selected, version, notes, path)
                except Exception as exc:
                    raise ValueError(update_error(exc)) from None
            def done(result):
                self.status.setText(f"已导出 {result['templates']} 个模板和 {result['files']} 个文件。")
                message(self, f"内容包已保存到：\n{path}\n\n使用项目中的发布工具上传，或在 GitHub Releases 新建 content-v{version} 并上传此 ZIP。")
            self.runner.start(run, done, self.status.setText)
        except Exception as exc:
            self.status.setText(update_error(exc))
