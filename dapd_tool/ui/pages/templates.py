from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QInputDialog, QListWidget, QListWidgetItem, QSplitter, QTreeWidget, QVBoxLayout, QWidget
from ...people import load_people
from ..controls import label, button, message, confirm
from ..dialogs.template import TemplateDialog
from ..widgets.plan_tree import fill_plan
from dapd_api import with_api
from PySide6.QtCore import Signal

class TemplatesPage(QWidget):
    statusChanged = Signal(str)
    templatesChanged = Signal(list, object)

    def __init__(self, store, session, runner, parent=None):
        super().__init__(parent)
        self.store, self.session, self.runner = store, session, runner
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(14)
        row = QHBoxLayout()
        row.addWidget(label("保存常用子任务结构，下次直接复用。", "muted"), 1)
        self.new_template = button("新建模板", lambda: self.edit_template())
        self.edit_template_button = button("编辑", self.edit_selected_template)
        self.delete_template_button = button("删除", self.delete_selected_template)
        row.addWidget(self.new_template)
        row.addWidget(self.edit_template_button)
        row.addWidget(self.delete_template_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.copy_template_button = button("复制为个人模板", self.copy_selected_template)
        row.addWidget(self.copy_template_button)
        row.addStretch()
        row.addWidget(button("导入模板文件", self.import_template_file))
        row.addWidget(button("导出所选模板", self.export_template_file))
        row.addWidget(button("导出共享内容包", self.export_content_pack))
        layout.addLayout(row)
        self.template_empty = label("还没有模板。点击“新建模板”，添加你需要的任务层级。", "notice")
        layout.addWidget(self.template_empty)
        splitter = QSplitter()
        self.template_list = QListWidget()
        self.template_list.setAccessibleName("我的模板列表")
        self.template_tree = QTreeWidget()
        self.template_tree.setHeaderLabel("模板子任务结构")
        splitter.addWidget(self.template_list)
        splitter.addWidget(self.template_tree)
        splitter.setSizes([300, 700])
        layout.addWidget(splitter, 1)
        self.template_list.currentItemChanged.connect(self.template_selected)
        self.template_list.itemDoubleClicked.connect(lambda *_: self.edit_selected_template())
        runner.busyChanged.connect(lambda busy: self.setEnabled(not busy))

    def refresh_templates(self, selected=None):
        current = self.template_list.currentItem()
        previous = selected or (current.data(Qt.ItemDataRole.UserRole)["id"] if current else None)
        templates = self.store.templates()
        from ...content_packs import load_shared
        try:
            templates += load_shared(self.store.directory)["templates"]
        except Exception:
            self.statusChanged.emit("共享模板无法读取，可在“更新与共享”重新同步。")
        self.template_list.clear()
        for template in templates:
            prefix = "共享 · " if template.get("shared") else ""
            item = QListWidgetItem(f"{prefix}{template['name']}\n{len(template['nodes'])} 个子任务" + (f" · v{template['content_version']}" if template.get("shared") else ""))
            item.setData(Qt.ItemDataRole.UserRole, template)
            self.template_list.addItem(item)
            if template["id"] == previous:
                self.template_list.setCurrentItem(item)
        self.template_empty.setVisible(not templates)
        self.template_selected()
        self.templatesChanged.emit(templates, selected)

    def template_selected(self, *_):
        item = self.template_list.currentItem()
        self.template_tree.clear()
        shared = bool(item and item.data(Qt.ItemDataRole.UserRole).get("shared"))
        self.edit_template_button.setEnabled(bool(item) and not shared)
        self.delete_template_button.setEnabled(bool(item) and not shared)
        self.copy_template_button.setEnabled(bool(item))
        if item:
            template = item.data(Qt.ItemDataRole.UserRole)
            nodes = [{"title": "主任务标题（创建时填写）", "parent": None}]
            nodes += [{"title": n["title"], "parent": 0 if n["parent"] is None else n["parent"] + 1} for n in template["nodes"]]
            fill_plan(self.template_tree, {"nodes": nodes})

    def edit_template(self, template=None):
        def opened(people):
            dialog = TemplateDialog(self.store, template, self, people)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh_templates(dialog.saved_id)
                self.statusChanged.emit("模板已保存。")
        if self.session.key:
            self.statusChanged.emit("正在读取可选负责人…")
            project = self.session.project
            self.runner.start(lambda _: with_api(self.session.key, lambda api: load_people(api, project)), opened, lambda error: message(self, error))
        else:
            opened(None)

    def import_template_file(self):
        from ...template_files import import_templates
        path, _ = QFileDialog.getOpenFileName(self, "导入模板", "", "DAPD 模板 (*.dapd-template)")
        if path:
            self.runner.start(lambda _: import_templates(self.store, path), self.templates_imported, lambda error: message(self, error))

    def templates_imported(self, identifiers):
        self.refresh_templates(identifiers[-1] if identifiers else None)
        self.statusChanged.emit(f"已导入 {len(identifiers)} 个个人模板，同名模板会另存副本。")

    def export_template_file(self):
        from ...template_files import export_templates
        item = self.template_list.currentItem()
        if not item:
            message(self, "请先选择要导出的模板。")
            return
        template = item.data(Qt.ItemDataRole.UserRole)
        path, _ = QFileDialog.getSaveFileName(self, "导出模板（包含图片和附件）", "模板.dapd-template", "DAPD 模板 (*.dapd-template)")
        if path:
            self.runner.start(lambda _: export_templates(self.store, [template], path), lambda _: self.statusChanged.emit("模板已导出：" + path), lambda error: message(self, error))

    def edit_selected_template(self):
        item = self.template_list.currentItem()
        if item:
            template = item.data(Qt.ItemDataRole.UserRole)
            if template.get("shared"):
                message(self, "共享模板由发布者维护。请点击“复制为个人模板”后编辑。")
            else:
                self.edit_template(template)

    def copy_selected_template(self):
        item = self.template_list.currentItem()
        if not item:
            return
        template = item.data(Qt.ItemDataRole.UserRole)
        name, accepted = QInputDialog.getText(self, "复制为个人模板", "个人模板名称：", text=template["name"] + "（副本）")
        if accepted:
            try:
                identifier = self.store.save_template(name, template["nodes"], root=template["root"])
                self.refresh_templates(identifier)
            except ValueError as exc:
                message(self, str(exc))

    def export_content_pack(self):
        from ..dialogs.export_content import ExportContentDialog
        ExportContentDialog(self.store, self.runner.activity, self).exec()

    def delete_selected_template(self):
        item = self.template_list.currentItem()
        if item:
            template = item.data(Qt.ItemDataRole.UserRole)
            if template.get("shared"):
                return
            if confirm(self, f"删除模板“{template['name']}”？已有 DAPD 任务和创建记录会保留。", "删除模板"):
                self.store.delete_template(template["id"])
                self.refresh_templates()
