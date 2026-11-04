from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QVBoxLayout
from ...content_packs import export_pack
from ...updates import update_error, version_tuple
from ..runner import Runner
from ..controls import button, confirm, label, message


class ExportContentDialog(QDialog):
    def __init__(self, store, activity, parent=None):
        super().__init__(parent)
        self.store = store
        self.runner = Runner(self, activity)
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
