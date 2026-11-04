import threading
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout, QHBoxLayout, QTreeView, QLineEdit, QListWidget, QListWidgetItem, QSplitter, QProgressBar, QAbstractItemView, QCheckBox
from ...tasks import list_created_tasks, edit_context
from ..widgets.task_tree import TaskTreeModel
from ..controls import label, button
from dapd_api import with_api
from ..dialogs.task_edit import TaskEditDialog


class TaskBrowser(QWidget):
    def __init__(self, store, session, runner, parent=None):
        super().__init__(parent)
        self.store, self.session, self.runner = store, session, runner
        self.data = None
        self.cache = {}
        self.account_key = session.key
        self.stop = threading.Event()
        self.reading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(12)
        split = QSplitter()
        sidebar = QWidget()
        sidebar.setMinimumWidth(180)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 8, 0)
        sidebar_layout.setSpacing(10)
        self.project_count = label("我的项目", "section")
        sidebar_layout.addWidget(self.project_count)
        self.project_search = QLineEdit()
        self.project_search.setPlaceholderText("搜索项目")
        self.project_search.setAccessibleName("搜索我的项目")
        self.project_search.textChanged.connect(self.filter_projects)
        sidebar_layout.addWidget(self.project_search)
        self.project_empty = label("", "muted")
        self.project_empty.hide()
        sidebar_layout.addWidget(self.project_empty)
        self.projects = QListWidget()
        self.projects.setAccessibleName("我的项目列表")
        self.projects.currentItemChanged.connect(self.project_changed)
        sidebar_layout.addWidget(self.projects, 1)
        sidebar_layout.addWidget(label("选择项目后读取该项目中由我创建的任务。", "muted"))
        split.addWidget(sidebar)
        panel = QWidget()
        content = QVBoxLayout(panel)
        content.setContentsMargins(8, 0, 0, 0)
        content.setSpacing(12)
        row = QHBoxLayout()
        self.project_title = label("选择项目", "section")
        row.addWidget(self.project_title, 1)
        self.refresh = button("读取项目任务", self.load, True)
        row.addWidget(self.refresh)
        self.cancel = button("取消读取", self.cancel_read)
        self.cancel.hide()
        row.addWidget(self.cancel)
        content.addLayout(row)
        self.search = QLineEdit()
        self.search.setPlaceholderText("筛选任务标题、任务组或负责人")
        self.search.setAccessibleName("筛选当前项目的任务")
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(150)
        self.search_timer.timeout.connect(self.filter)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        search_row = QHBoxLayout()
        search_row.addWidget(self.search, 1)
        self.highlight_own = QCheckBox("高亮我创建的任务")
        self.highlight_own.setChecked(False)
        search_row.addWidget(self.highlight_own)
        content.addLayout(search_row)
        self.note = label("连接 DAPD 后，从左侧选择项目。", "muted")
        content.addWidget(self.note)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        content.addWidget(self.progress)
        self.tree = QTreeView()
        self.tree.setAccessibleName("当前项目中我创建的任务")
        self.model = TaskTreeModel(self)
        self.highlight_own.toggled.connect(self.model.set_highlight_own)
        self.tree.setModel(self.model)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for column, width in enumerate([320, 140, 100, 85, 70, 160, 160, 160, 100, 290]):
            self.tree.setColumnWidth(column, width)
        self.tree.setUniformRowHeights(True)
        self.tree.doubleClicked.connect(lambda *_: self.edit())
        self.tree.selectionModel().selectionChanged.connect(self.update_actions)
        self.tree.setExpandsOnDoubleClick(False)
        content.addWidget(self.tree, 1)
        self.empty = label("选择左侧项目，即可查看任务。", "muted")
        content.addWidget(self.empty)
        row = QHBoxLayout()
        row.addWidget(button("全部展开", self.tree.expandAll))
        row.addWidget(button("全部收起", self.tree.collapseAll))
        row.addStretch()
        self.edit_button = button("编辑所选任务", self.edit)
        row.addWidget(self.edit_button)
        content.addLayout(row)
        split.addWidget(panel)
        split.setStretchFactor(1, 1)
        split.setCollapsible(0, False)
        split.setCollapsible(1, False)
        split.setSizes([210, 820])
        layout.addWidget(split, 1)
        self.runner.busyChanged.connect(self.busy_changed)
        session.projectsChanged.connect(self.set_projects)
        self.update_actions()

    def selected_project(self):
        item = self.projects.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def set_projects(self, projects):
        selected = self.selected_project()
        if self.account_key != self.session.key:
            self.cache.clear()
            selected = None
            self.account_key = self.session.key
        self.projects.blockSignals(True)
        self.projects.clear()
        for project in projects:
            item = QListWidgetItem(project["name"])
            item.setData(Qt.ItemDataRole.UserRole, project)
            self.projects.addItem(item)
            self.update_project_label(item)
            if selected and project["id"] == selected["id"]:
                self.projects.setCurrentItem(item)
        self.projects.blockSignals(False)
        self.cache = {key: value for key, value in self.cache.items() if key in {p["id"] for p in projects}}
        self.project_count.setText(f"我的项目 · {len(projects)}")
        self.filter_projects()
        self.project_changed()

    def update_project_label(self, item):
        project = item.data(Qt.ItemDataRole.UserRole)
        data = self.cache.get(project["id"])
        summary = "尚未读取"
        if data:
            summary = f"{len(data['own_ids'])} 个我创建的任务" + (" · 未读完" if not data["complete"] else "")
        item.setText(project["name"] + "\n" + summary)

    def filter_projects(self):
        text = self.project_search.text().strip().casefold()
        visible = 0
        for row in range(self.projects.count()):
            item = self.projects.item(row)
            item.setHidden(text not in item.data(Qt.ItemDataRole.UserRole)["name"].casefold())
            visible += not item.isHidden()
        self.project_empty.setText("没有匹配的项目。" if self.projects.count() else "连接 DAPD 后显示项目。")
        self.project_empty.setVisible(visible == 0)

    def project_changed(self, *_):
        project = self.selected_project()
        self.project_title.setText(project["name"] if project else "选择项目")
        self.data = self.cache.get(project["id"]) if project else None
        self.refresh.setText("刷新项目任务" if self.data else "读取项目任务")
        self.model.replace(self.data or {"tasks": [], "groups": {}, "statuses": {}})
        self.update_actions()
        if self.data:
            self.show_data()
        elif project:
            self.note.setText("点击“读取项目任务”加载当前项目。")
            self.empty.setText("此项目尚未读取。")
            self.empty.show()
            if not self.runner.busy:
                self.load()
        else:
            self.note.setText("从左侧选择项目后读取任务。" if self.projects.count() else "暂无可用项目，请连接 DAPD 或刷新项目。")
            self.empty.setText("选择左侧项目，即可查看任务。" if self.projects.count() else "连接后将在这里显示任务。")
            self.empty.show()

    def busy_changed(self, busy):
        if not busy:
            self.reading = False
        self.cancel.setVisible(self.reading)
        self.progress.setVisible(self.reading)
        self.update_actions()

    def update_actions(self, *_):
        busy = self.runner.busy
        self.projects.setEnabled(not busy)
        self.refresh.setEnabled(not busy and bool(self.session.key) and bool(self.selected_project()))
        self.edit_button.setEnabled(not busy and bool(self.selected_task()) and not self.selected_task().get("contextOnly"))

    def selected_task(self):
        return self.tree.currentIndex().data(Qt.ItemDataRole.UserRole)

    def load(self):
        if not self.session.key:
            self.note.setText("请先通过“连接设置”填写 API Key。")
            return
        project = self.selected_project()
        if not project or self.runner.busy:
            return
        self.stop.clear()
        self.reading = True
        self.cancel.setEnabled(True)
        self.note.setText("正在读取当前项目的任务…")
        key = self.session.key
        self.runner.start(lambda emit: with_api(key, lambda api: list_created_tasks(api, project["id"], emit, self.stop)),
            self.loaded, self.failed, self.read_progress)

    def read_progress(self, text):
        if not self.stop.is_set():
            self.note.setText(text)

    def cancel_read(self):
        self.stop.set()
        self.cancel.setEnabled(False)
        self.note.setText("正在取消，等待当前请求结束；已读取的任务会保留。")

    def failed(self, text):
        self.note.setText(text + (" 当前仍显示上次读取的数据。" if self.data else " 请点击“读取项目任务”重试。"))

    def loaded(self, data):
        if not data["complete"] and self.data and (self.data["complete"] or not data["tasks"]):
            self.note.setText("已取消读取，保留上次读取的数据。")
            return
        self.model.replace(data)
        self.data = data
        self.cache[data["project_id"]] = data
        item = self.projects.currentItem()
        if item:
            self.update_project_label(item)
        self.show_data()

    def show_data(self):
        data = self.data
        self.refresh.setText("刷新项目任务")
        status = "读取完成" if data["complete"] else "已取消读取，结果不完整，请刷新重新读取"
        self.note.setText(f"{data['user'].get('name', '当前用户')} · {len(data['own_ids'])} 个我创建的任务 · {status}。他人创建的父任务仅展示。")
        self.filter()
        self.update_actions()

    def filter(self):
        self.model.set_query(self.search.text())
        if self.search.text().strip():
            self.tree.expandAll()
        else:
            self.tree.expandToDepth(0)
        self.empty.setVisible(self.model.matches == 0)
        if self.data:
            self.empty.setText("没有匹配的任务，请调整筛选词。" if self.search.text().strip() else
                "当前项目中没有我创建的任务。" if self.data["complete"] else "读取已取消，尚未读取到任务；可重新读取。")
        self.update_actions()

    def edit(self):
        task = self.selected_task()
        if not task or not self.session.key or self.runner.busy:
            return
        if task.get("contextOnly"):
            self.note.setText("这个父任务由其他用户创建，仅用于显示层级。请选择自己创建的任务。")
            return
        self.note.setText("正在读取任务详情…")
        self.runner.start(lambda _: with_api(self.session.key, lambda api: edit_context(api, task["id"])), self.open_editor, self.note.setText)

    def open_editor(self, context):
        dialog = TaskEditDialog(context, self.store, self.session.key, self.runner.activity, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved:
            identifier = dialog.saved["id"]
            self.data["tasks"] = [dialog.saved if t["id"] == identifier else t for t in self.data["tasks"]]
            self.loaded(self.data)
            self.note.setText("任务已更新，已从 DAPD 回读确认。")
