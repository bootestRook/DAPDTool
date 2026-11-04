from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QHBoxLayout, QLineEdit, QStackedWidget, QVBoxLayout, QWidget
from ...media import Assets, description_assets
from ...model import make_plan, make_batch_plan
from ..widgets.batch_editor import BatchEditor
from ..controls import label, button, message
from ..dialogs.preview import PreviewDialog
from PySide6.QtCore import Signal
from ..destination import DestinationPicker

class CreatePage(QWidget):
    statusChanged = Signal(str)
    connectionRequested = Signal()
    manageTemplatesRequested = Signal()
    planReady = Signal(object)

    def __init__(self, store, session, runner, parent=None):
        super().__init__(parent)
        self.store, self.session, self.runner = store, session, runner
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(18)
        self.destination_picker = DestinationPicker(session, runner, self)
        self.destination_picker.statusChanged.connect(self.statusChanged.emit)
        self.destination_picker.connectionRequested.connect(self.connectionRequested.emit)
        self.destination_picker.changed.connect(self.update_actions)
        layout.addWidget(self.destination_picker)
        self.mode = QComboBox()
        self.mode.addItems(["空任务", "按模板批量创建"])
        self.mode.setAccessibleName("创建方式")
        row = QFormLayout()
        row.setHorizontalSpacing(20)
        row.addRow("创建方式", self.mode)
        layout.addLayout(row)
        self.inputs = QStackedWidget()
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(12)
        el.addWidget(label("任务标题", "section"))
        self.single_title = QLineEdit()
        self.single_title.setPlaceholderText("输入要创建的任务标题")
        self.single_title.setAccessibleName("空任务标题")
        el.addWidget(self.single_title)
        el.addWidget(label("只创建这一个任务，负责人、描述和日期留空。", "muted"))
        el.addStretch()
        self.inputs.addWidget(empty)
        batch = QWidget()
        bl = QVBoxLayout(batch)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(12)
        row = QHBoxLayout()
        row.addWidget(label("任务模板"))
        self.template_combo = QComboBox()
        self.template_combo.setAccessibleName("批量创建模板")
        row.addWidget(self.template_combo, 1)
        row.addWidget(button("管理模板", self.manageTemplatesRequested.emit))
        bl.addLayout(row)
        self.batch_entries = BatchEditor(self.template_combo.currentData)
        bl.addWidget(self.batch_entries, 1)
        self.batch_count = label("尚未选择模板。", "muted")
        bl.addWidget(self.batch_count)
        self.inputs.addWidget(batch)
        layout.addWidget(self.inputs, 1)
        row = QHBoxLayout()
        row.addWidget(label("提交前可查看完整任务树与创建数量。", "muted"), 1)
        self.preview_button = button("预览任务", self.preview, True)
        row.addWidget(self.preview_button)
        layout.addLayout(row)
        self.mode.currentIndexChanged.connect(self.inputs.setCurrentIndex)
        self.batch_entries.changed.connect(self.update_count)
        self.template_combo.currentIndexChanged.connect(self.update_count)
        runner.busyChanged.connect(self.update_actions)
        self.update_actions()

    def update_actions(self, *_):
        self.setEnabled(not self.runner.busy)
        self.preview_button.setEnabled(bool(self.destination_picker.group.currentData()) and bool(self.session.key) and not self.runner.busy)

    def set_templates(self, templates, selected=None):
        previous = selected or (self.template_combo.currentData() or {}).get("id")
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItem("请选择模板" if templates else "暂无模板，请先新建", None)
        for template in templates:
            prefix = "共享 · " if template.get("shared") else ""
            self.template_combo.addItem(prefix + template["name"], template)
            if template["id"] == previous:
                self.template_combo.setCurrentIndex(self.template_combo.count() - 1)
        self.template_combo.blockSignals(False)
        self.batch_entries.set_templates(templates)
        self.update_count()

    def preview(self):
        try:
            if self.mode.currentIndex() == 0:
                plan = make_plan([self.single_title.text()], [], self.destination_picker.destination())
            else:
                plan = make_batch_plan(self.batch_entries.entries(), self.destination_picker.destination())
            assets=Assets(self.store.directory)
            for node in plan["nodes"]:
                content=node["content"]
                for asset in [*description_assets(content).values(),*content["attachments"]]:assets.path(asset,verify_hash=True)
        except ValueError as exc:
            message(self, str(exc))
            return
        if PreviewDialog(plan, self,self.store.directory).exec() == QDialog.DialogCode.Accepted:
            self.planReady.emit(plan)

    def update_count(self):
        count = self.batch_entries.table.rowCount()
        total = 0
        for row in range(count):
            combo = self.batch_entries.table.cellWidget(row, 1)
            template = combo.currentData() if combo else None
            total += len(template["nodes"]) + 1 if template else 0
        self.batch_count.setText(f"{count} 个主任务 · 共 {total} 个任务节点。每行可选择不同模板。")
