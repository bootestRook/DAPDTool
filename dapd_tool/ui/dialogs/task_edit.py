import copy
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox, QListWidget, QListWidgetItem, QSplitter, QScrollArea, QLabel, QDoubleSpinBox, QCheckBox, QSizePolicy
from ..widgets.content_editor import ContentEditor
from ...media import empty_content
from ...tasks import task_values, save_task, reset_unknown_uploads
from ..widgets.task_tree import date_label
from ..controls import label, button, confirm
from ..runner import Runner
from dapd_api import with_api


def check_list(options, selected):
    widget = QListWidget()
    widget.setMaximumHeight(105)
    for identifier, name in options:
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, identifier)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if identifier in selected else Qt.CheckState.Unchecked)
        widget.addItem(item)
    return widget


def checked(widget):
    return [widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget.count()) if widget.item(i).checkState() == Qt.CheckState.Checked]


class TaskEditDialog(QDialog):
    def __init__(self, context, store, key, activity, parent=None):
        super().__init__(parent)
        self.store, self.key, self.task = store, key, context["task"]
        self.runner = Runner(self, activity)
        self.saved = None
        self.setWindowTitle("编辑 DAPD 任务")
        self.resize(1220, 820)
        self.setMinimumSize(1000, 700)
        layout = QVBoxLayout(self)
        layout.addWidget(label(self.task["title"], "heading"))
        layout.addWidget(label(f"创建于 {date_label(self.task.get('createdAt'))} · 更新于 {date_label(self.task.get('updatedAt'))}", "muted"))
        split = QSplitter()
        form_panel = QWidget()
        form = QFormLayout(form_panel)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.title = QLineEdit(self.task["title"])
        self.title.setMaxLength(255)
        form.addRow("标题", self.title)
        project = self.task.get("project") or {}
        project_label = label(project.get("name") or self.task["projectId"])
        project_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        form.addRow("项目", project_label)
        self.group = QComboBox()
        for group in context["groups"]:
            self.group.addItem(group["name"], group["id"])
        self.group.setCurrentIndex(self.group.findData(self.task["taskGroupId"]))
        form.addRow("任务组", self.group)
        self.parent_id = QLineEdit(self.task.get("parentTaskId") or "")
        self.parent_id.setPlaceholderText("父任务链接或 ID；留空为顶层")
        form.addRow("父任务", self.parent_id)
        self.status = QComboBox()
        for state in context["statuses"]:
            self.status.addItem(state["name"], state["key"])
        if self.status.findData(self.task["status"]) < 0:
            self.status.addItem(self.task["status"], self.task["status"])
        self.status.setCurrentIndex(self.status.findData(self.task["status"]))
        self.status.setEnabled(not self.task.get("workflowId"))
        form.addRow("状态", self.status)
        if self.task.get("workflowId"):
            form.addRow(label("此任务使用工作流，节点流转请在 DAPD 中操作。", "muted"))
        self.priority = QComboBox()
        for key, name in [("low", "低"), ("medium", "中"), ("high", "高"), ("urgent", "紧急")]:
            self.priority.addItem(name, key)
        self.priority.setCurrentIndex(self.priority.findData(self.task["priority"]))
        form.addRow("优先级", self.priority)
        self.due = QLineEdit(self.task.get("dueDate") or "")
        self.due.setPlaceholderText("2026-11-04 或日期时间；留空清除")
        form.addRow("截止时间", self.due)
        values = task_values(self.task)
        self.tags = check_list([(t["id"], t["name"]) for t in context["tags"]], values["tags"])
        form.addRow("标签", self.tags)
        self.copied = check_list([(m["id"], m["name"]) for m in context["members"]], values["copiedUserIds"])
        form.addRow("抄送成员", self.copied)
        self.related = QLineEdit(", ".join(values["relatedTaskIds"]))
        self.related.setPlaceholderText("任务 ID，以逗号或空格分隔")
        form.addRow("关联任务", self.related)
        self.custom = []
        for field in context["fields"]:
            if field["isSystem"] and field["key"] != "startDate":
                continue
            value = next((v["value"] for v in self.task.get("fieldValues", []) if v["fieldId"] == field["id"]), None)
            kind = field["type"]
            options = (field.get("config") or {}).get("options", [])
            if kind in ("single_select", "user"):
                widget = QComboBox()
                widget.addItem("未设置", None)
                for option in (context["members"] if kind == "user" else options):
                    widget.addItem(option.get("name", option.get("label", "")), option.get("id", option.get("value")))
                widget.setCurrentIndex(max(0, widget.findData(value)))
                getter = widget.currentData
            elif kind in ("multi_select", "multi_user"):
                candidates = context["members"] if kind == "multi_user" else options
                widget = check_list([(o.get("id", o.get("value")), o.get("name", o.get("label", ""))) for o in candidates], value or [])
                getter = lambda w=widget: checked(w)
            elif kind == "number":
                widget = QDoubleSpinBox(); widget.setRange(-1e12, 1e12); widget.setDecimals(4); widget.setValue(value or 0)
                getter = widget.value
            elif kind == "boolean":
                widget = QCheckBox(); widget.setChecked(bool(value)); getter = widget.isChecked
            else:
                widget = QLineEdit(str(value or "")); getter = lambda w=widget: w.text().strip() or None
            form.addRow(field["name"], widget)
            self.custom.append((field, getter, value))
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(form_panel)
        split.addWidget(scroll)
        self.editor = ContentEditor(store.directory)
        self.editor.heading.setText("任务描述")
        self.editor.assignee_label.setText("负责人")
        self.editor.upload_action = "保存更新时上传。"
        self.editor.note.setText("支持标题、列表、文字格式与直接粘贴图片。点击“保存更新”后写入 DAPD。")
        self.editor.set_people(context["people"])
        content = {**empty_content(), "html": self.task.get("description") or ""}
        if self.task.get("assigneeId"):
            content["assignee"] = {"id": self.task["assigneeId"], "name": (self.task.get("assignee") or {}).get("name") or self.task["assigneeId"]}
        self.editor.set_content(content)
        # Existing remote attachments remain visible alongside newly added files.
        self.remote = QLabel("已有附件：" + ("、".join(a.get("name", "附件") for a in self.task.get("attachments", [])) or "无"))
        self.remote.setWordWrap(True)
        self.editor.layout().addWidget(self.remote)
        split.addWidget(self.editor); split.setSizes([350, 820]); layout.addWidget(split, 1)
        self.error = label(""); layout.addWidget(self.error)
        row = QHBoxLayout()
        reset = button("重置待核对上传", self.reset_uploads)
        row.addWidget(reset); row.addStretch()
        row.addWidget(button("取消", self.reject))
        self.save_button = button("保存更新", self.save, True); row.addWidget(self.save_button)
        layout.addLayout(row)
        self.runner.busyChanged.connect(lambda busy: (split.setEnabled(not busy), self.save_button.setEnabled(not busy), reset.setEnabled(not busy)))
        self.initial = self.values()

    def values(self):
        from ...catalog import task_id_from_text
        from dapd_api import CHINA_TIME
        content = self.editor.content()
        due = self.due.text().strip()
        if due:
            parsed = datetime.fromisoformat(due.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=CHINA_TIME)
            due = parsed.isoformat()
        parent = self.parent_id.text().strip()
        if parent:
            parent = task_id_from_text(parent)
            if not parent:
                raise ValueError("请输入完整父任务链接或 ID。")
        fields = copy.deepcopy(self.task.get("fieldValues", []))
        for field, getter, initial in self.custom:
            value = getter()
            if value != initial:
                fields = [v for v in fields if v["fieldId"] != field["id"]]
                fields.append({"fieldId": field["id"], "fieldKey": field["key"], "value": value})
        values = {"title": self.title.text().strip(), "description": content.get("html", ""),
                  "assigneeId": (content.get("assignee") or {}).get("id"), "taskGroupId": self.group.currentData(),
                  "parentTaskId": parent or None, "status": self.status.currentData(), "priority": self.priority.currentData(),
                  "dueDate": due or None, "tags": checked(self.tags), "copiedUserIds": checked(self.copied),
                  "relatedTaskIds": self.related.text().replace(",", " ").split(), "fieldValues": fields}
        return values, content

    def save(self):
        try:
            values, content = self.values()
            changes = {k: v for k, v in values.items() if v != self.initial[0][k]}
            self.error.setText("正在保存并核对 DAPD 内容…")
            self.runner.start(lambda _: with_api(self.key, lambda api: save_task(self.store, api, self.task, changes, content)), self.done_saving, self.failed)
        except (ValueError, TypeError) as exc:
            self.error.setText(str(exc))

    def failed(self, error):
        self.error.setText(error)

    def done_saving(self, task):
        self.saved = task
        self.accept()

    def reset_uploads(self):
        if confirm(self, "请先到 DAPD 项目文件中核对上传确实不存在，再重置。", "已核对不存在"):
            reset_unknown_uploads(self.store, self.task["id"])
            self.error.setText("已重置待核对上传，可以重新保存。")

    def reject(self):
        if self.runner.busy:
            self.error.setText("正在等待网络请求结束，请稍候。")
            return
        try:
            dirty = self.values() != self.initial
        except ValueError:
            dirty = True
        if dirty and not confirm(self, "放弃尚未保存的任务修改？", "放弃修改"):
            return
        super().reject()
