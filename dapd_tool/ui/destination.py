from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QHBoxLayout, QInputDialog, QWidget
from ..catalog import group_id_from_text, locate_group, locate_project, project_id_from_text
from .controls import label, button, message
from .dialogs.parent_task import ParentDialog
from dapd_api import with_api
from PySide6.QtCore import Signal

class DestinationPicker(QWidget):
    changed = Signal()
    statusChanged = Signal(str)
    connectionRequested = Signal()

    def __init__(self, session, runner, parent=None):
        super().__init__(parent)
        self.session, self.runner = session, runner
        self.parent_task = None
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(20)
        self.project = QComboBox()
        self.project.setAccessibleName("项目")
        self.group = QComboBox()
        self.group.setAccessibleName("任务组")
        self.project.addItem("请先连接 DAPD", None)
        self.group.addItem("请先选择项目", None)
        project_row=QHBoxLayout()
        project_row.addWidget(self.project,1)
        self.project_link_button=button("粘贴项目链接",self.project_from_link)
        project_row.addWidget(self.project_link_button)
        form.addRow("项目",project_row)
        group_row = QHBoxLayout()
        group_row.addWidget(self.group, 1)
        self.group_link_button = button("粘贴任务组链接", self.group_from_link)
        group_row.addWidget(self.group_link_button)
        form.addRow("任务组", group_row)
        row = QHBoxLayout()
        self.parent_label = label("无 · 在任务组顶层创建", "muted")
        self.parent_button = button("选择父任务", self.choose_parent)
        self.clear_parent_button = button("清除", self.clear_parent)
        row.addWidget(self.parent_label, 1)
        row.addWidget(self.parent_button)
        row.addWidget(self.clear_parent_button)
        form.addRow("父任务", row)
        self.project.currentIndexChanged.connect(self.project_changed)
        self.group.currentIndexChanged.connect(self.group_changed)
        session.projectsChanged.connect(self.set_projects)
        runner.busyChanged.connect(self.busy_changed)
        self.busy_changed(runner.busy)

    def busy_changed(self, busy):
        self.setEnabled(not busy)
        self.parent_button.setEnabled(bool(self.group.currentData()) and not busy)
        self.clear_parent_button.setEnabled(bool(self.parent_task) and not busy)

    def show_loading(self):
        self.project.blockSignals(True)
        self.project.clear()
        self.project.addItem("正在加载项目…", None)
        self.project.blockSignals(False)
        self.session.set_project(None)
        self.clear_groups()
        self.changed.emit()

    def set_projects(self, projects):
        self.project.blockSignals(True)
        self.project.clear()
        self.project.addItem("请选择项目" if projects else "此账号没有可用项目", None)
        for project in projects:
            self.project.addItem(project["name"], project)
        self.project.blockSignals(False)
        self.session.set_project(None)
        self.clear_groups()
        self.changed.emit()

    def clear_groups(self):
        self.group.blockSignals(True)
        self.group.clear()
        self.group.addItem("请先选择项目", None)
        self.group.blockSignals(False)
        self.clear_parent()
        self.changed.emit()
        self.busy_changed(self.runner.busy)

    def project_changed(self):
        self.clear_groups()
        project = self.project.currentData()
        self.session.set_project(project)
        if project is None or self.runner.busy:
            return
        self.group.setItemText(0, "正在加载任务组…")
        self.statusChanged.emit("正在读取任务组…")
        self.runner.start(lambda _: with_api(self.session.key, lambda api: api.groups(project["id"])), self.set_groups, self.statusChanged.emit)

    def set_groups(self, groups):
        self.group.clear()
        groups = [g for g in groups if g.get("status") != "archived"]
        self.group.addItem("请选择任务组" if groups else "这个项目没有可用任务组", None)
        for group in groups:
            self.group.addItem(group["name"], group)
        self.statusChanged.emit(f"已读取 {len(groups)} 个任务组。请选择任务组。")

    def group_from_link(self):
        if not self.session.key:
            self.connectionRequested.emit()
            if not self.session.key:
                return
        value, accepted = QInputDialog.getText(self, "粘贴任务组链接", "粘贴任务组链接，或 DAPD 复制出的整段文字（含名称和链接）：")
        if not accepted:
            return
        try:
            identifier = group_id_from_text(value)
        except ValueError as exc:
            message(self, str(exc))
            return
        self.statusChanged.emit("正在按链接定位项目和任务组…")
        self.runner.start(lambda _: with_api(self.session.key, lambda api: locate_group(api, identifier)), self.group_located, self.statusChanged.emit)

    def project_from_link(self):
        if not self.session.key:
            self.connectionRequested.emit()
            if not self.session.key:return
        value,accepted=QInputDialog.getText(self,"粘贴项目链接","粘贴项目链接，或 DAPD 复制出的整段项目文字：")
        if not accepted:return
        try:identifier=project_id_from_text(value)
        except ValueError as exc:
            message(self,str(exc));return
        self.statusChanged.emit("正在按链接定位项目…")
        self.runner.start(lambda _: with_api(self.session.key, lambda api: locate_project(api, identifier)),
                          self.project_located, self.statusChanged.emit)

    def project_located(self,result):
        self.session.set_projects(result["projects"])
        self.project.blockSignals(True)
        for index in range(self.project.count()):
            if (self.project.itemData(index) or {}).get("id")==result["project"]["id"]:
                self.project.setCurrentIndex(index);break
        self.project.blockSignals(False)
        self.session.set_project(result["project"])
        self.set_groups(result["groups"])
        self.statusChanged.emit(f"已定位项目：{result['project']['name']}。请选择任务组。")

    def group_located(self, result):
        self.session.set_projects(result["projects"])
        self.project.blockSignals(True)
        for index in range(self.project.count()):
            if (self.project.itemData(index) or {}).get("id") == result["project"]["id"]:
                self.project.setCurrentIndex(index)
                break
        self.project.blockSignals(False)
        self.session.set_project(result["project"])
        self.set_groups(result["groups"])
        for index in range(self.group.count()):
            if (self.group.itemData(index) or {}).get("id") == result["group"]["id"]:
                self.group.setCurrentIndex(index)
                break
        self.statusChanged.emit(f"已定位：{result['project']['name']} / {result['group']['name']}。可继续选择父任务。")

    def group_changed(self):
        self.clear_parent()
        self.changed.emit()
        self.busy_changed(self.runner.busy)

    def choose_parent(self):
        project, group = self.project.currentData(), self.group.currentData()
        if not project or not group:
            message(self, "请先选择项目和任务组。")
            return
        dialog = ParentDialog(self.session.key, project, group, self.runner.activity, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.parent_task = dialog.selected
            self.parent_label.setText(self.parent_task["title"])
            self.clear_parent_button.setEnabled(True)

    def clear_parent(self):
        self.parent_task = None
        self.parent_label.setText("无 · 在任务组顶层创建")
        self.clear_parent_button.setEnabled(False)

    def destination(self):
        project, group = self.project.currentData(), self.group.currentData()
        if not project or not group:
            raise ValueError("请先选择项目和任务组。")
        result = {"projectId": project["id"], "projectName": project["name"], "taskGroupId": group["id"], "groupName": group["name"]}
        if self.parent_task:
            result.update(parentTaskId=self.parent_task["id"], parentTitle=self.parent_task["title"])
        return result
