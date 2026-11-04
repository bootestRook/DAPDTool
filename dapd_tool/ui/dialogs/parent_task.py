from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QHeaderView, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout
from ...catalog import task_id_from_text
from ..controls import label, button
from ..runner import Runner
from dapd_api import with_api


class ParentDialog(QDialog):
    def __init__(self, key, project, group, activity, parent=None):
        super().__init__(parent)
        self.key, self.project, self.group = key, project, group
        self.selected = None
        self.setWindowTitle("选择父任务")
        self.resize(760, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        layout.addWidget(label(f"{project['name']}  /  {group['name']}", "section"))
        layout.addWidget(label("输入标题关键词，或粘贴 DAPD 复制的整段任务文字（含链接）。只显示当前项目、任务组中的任务。", "muted"))
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("任务标题关键词 / 任务链接 / 任务 ID")
        self.query.setAccessibleName("父任务搜索")
        self.search_button = button("查找", self.search)
        row.addWidget(self.query, 1)
        row.addWidget(self.search_button)
        layout.addLayout(row)
        self.list = QTreeWidget()
        self.list.setHeaderLabels(["任务标题", "任务 ID"])
        self.list.setRootIsDecorated(False)
        self.list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.list, 1)
        self.status = label("输入关键词后点击查找。", "muted")
        layout.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch()
        self.cancel = button("取消", self.reject)
        self.choose_button = button("使用所选父任务", self.choose, True)
        self.choose_button.setEnabled(False)
        row.addWidget(self.cancel)
        row.addWidget(self.choose_button)
        layout.addLayout(row)
        self.runner = Runner(self, activity)
        self.runner.busyChanged.connect(self.busy_changed)
        self.query.returnPressed.connect(self.search)
        self.list.itemSelectionChanged.connect(lambda: self.choose_button.setEnabled(bool(self.list.currentItem()) and not self.runner.busy))
        self.list.itemDoubleClicked.connect(lambda *_: self.choose())

    def busy_changed(self, busy):
        self.search_button.setEnabled(not busy)
        self.query.setEnabled(not busy)
        self.cancel.setEnabled(not busy)
        self.choose_button.setEnabled(not busy and bool(self.list.currentItem()))

    def search(self):
        query = self.query.text().strip()
        if not query:
            self.status.setText("请先输入搜索关键词。")
            return
        try:
            identifier = task_id_from_text(query)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.list.clear()
        self.status.setText("正在查找…")
        def search(api):
            if identifier:
                task = api.task(identifier)
                if task.get("projectId") != self.project["id"] or task.get("taskGroupId") != self.group["id"]:
                    raise ValueError("这个父任务不属于当前项目和任务组，请先更改归属选择。")
                return {"tasks": [task], "truncated": False}
            return api.search(self.project["id"], query)
        self.runner.start(lambda _: with_api(self.key, search), self.show_results, self.status.setText)

    def show_results(self, result):
        tasks = [t for t in result["tasks"] if t.get("projectId") == self.project["id"] and t.get("taskGroupId") == self.group["id"]]
        for task in tasks:
            item = QTreeWidgetItem([task["title"], task["id"]])
            item.setData(0, Qt.ItemDataRole.UserRole, task)
            self.list.addTopLevelItem(item)
        self.status.setText(f"找到 {len(tasks)} 个任务。" + ("搜索结果较多，请使用更具体的关键词。" if result.get("truncated") else ""))

    def choose(self):
        item = self.list.currentItem()
        if item and not self.runner.busy:
            self.selected = item.data(0, Qt.ItemDataRole.UserRole)
            self.accept()

    def reject(self):
        if not self.runner.busy:
            super().reject()
