"""Qt Widgets interface for the standalone task tool."""
import csv
import json
import threading
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QThread, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QStackedWidget,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QStyle,
)

from dapd_api import BASE_URL, DapdClient
from .engine import reset_absent, reset_absent_uploads, resolve_unknown, run_job, safe_error
from .catalog import group_id_from_text, locate_group, task_id_from_text, project_id_from_text
from .content_editor import ContentEditor
from .media import Assets, empty_content, image_assets, description_assets
from .model import make_plan, make_batch_plan, validate_template
from .batch_editor import BatchEditor
from .people import load_people


STATUS = {"pending": "等待创建", "started": "正在提交", "created": "已创建", "unverified": "已提交，待回读",
          "failed": "提交被拒绝", "unknown": "结果待核对", "paused": "已暂停", "running": "创建中",
          "completed": "已完成", "blocked": "待核对", "media_unknown":"上传结果待核对"}

STYLE = """
QWidget { font-family: 'Microsoft YaHei UI'; font-size: 10pt; color: #253440; }
QMainWindow, QDialog { background: #f4f6f8; }
QLabel { background: transparent; }
QLabel#heading { font-size: 20pt; font-weight: 600; color: #183c4a; }
QLabel#section { font-size: 12pt; font-weight: 600; }
QLabel#muted { color: #566875; }
QLabel#notice { background: #e9f2f3; padding: 12px; color: #244e58; border-radius: 6px; }
QPushButton { background: #fff; border: 1px solid #b9c6cd; border-radius: 5px; padding: 7px 14px; min-height: 20px; }
QPushButton:hover { background: #edf3f5; border-color: #728d98; }
QPushButton:pressed { background: #dce9ed; }
QPushButton:focus { border: 2px solid #147788; padding: 6px 13px; }
QPushButton:disabled { color: #78868e; background: #edf0f2; border-color: #d3dce0; }
QPushButton#primary { background: #146979; border-color: #146979; color: #fff; font-weight: 600; }
QPushButton#primary:hover { background: #0f5866; }
QPushButton#primary:disabled { background: #90afb5; border-color: #90afb5; color: #f5f8f9; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QTreeWidget, QListWidget { background: #fff; border: 1px solid #bdcad1; border-radius: 4px; selection-background-color: #d8edef; selection-color: #183c4a; }
QLineEdit, QPlainTextEdit, QTextEdit { placeholder-text-color: #566875; }
QLineEdit, QComboBox { padding: 7px 9px; min-height: 20px; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QTreeWidget:focus, QListWidget:focus { border: 1px solid #147788; }
QLineEdit:disabled, QComboBox:disabled { color: #78868e; background: #edf0f2; }
QComboBox QAbstractItemView { background: white; selection-background-color: #d8edef; }
QTreeWidget::item, QListWidget::item { padding: 7px 4px; min-height: 22px; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #d8edef; color: #183c4a; }
QHeaderView::section { background: #edf2f5; border: none; border-bottom: 1px solid #ced8dd; padding: 9px; font-weight: 600; }
QTabWidget::pane { border: 0; background: #f4f6f8; }
QTabBar::tab { background: transparent; border-bottom: 2px solid transparent; padding: 12px 25px; color: #566875; }
QTabBar::tab:selected { color: #125d6c; border-bottom-color: #146979; font-weight: 600; }
QTabBar::tab:focus { background: #e2edf0; }
QProgressBar { background: #e3eaee; border: none; border-radius: 3px; text-align: center; min-height: 8px; }
QProgressBar::chunk { background: #146979; border-radius: 3px; }
QSplitter::handle { background: #e0e7eb; }
"""


class NoTooltips(QObject):
    def eventFilter(self, obj, event):
        return event.type() == QEvent.Type.ToolTip


def label(text, kind=None):
    result = QLabel(text)
    result.setWordWrap(True)
    result.setTextFormat(Qt.TextFormat.PlainText)
    if kind:
        result.setObjectName(kind)
    return result


def button(text, action, primary=False):
    result = QPushButton(text)
    result.setAutoDefault(False)
    if primary:
        result.setObjectName("primary")
    result.clicked.connect(action)
    return result


def message(parent, text):
    box = QMessageBox(parent)
    box.setWindowTitle("DAPD 任务工具")
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Information)
    box.addButton("知道了", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def confirm(parent, text, action="确认"):
    box = QMessageBox(parent)
    box.setWindowTitle("请核对")
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(text)
    yes = box.addButton(action, QMessageBox.ButtonRole.AcceptRole)
    no = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(no)
    box.exec()
    return box.clickedButton() is yes


def task_url(identifier):
    return BASE_URL + "/task/" + identifier


def open_task(identifier):
    if identifier:
        QDesktopServices.openUrl(QUrl(task_url(identifier)))


class Worker(QThread):
    result = Signal(object)
    failure = Signal(str)
    update = Signal(object)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.result.emit(self.function(self.update.emit))
        except Exception as exc:
            self.failure.emit(safe_error(exc))


class Runner(QObject):
    busyChanged = Signal(bool)

    def __init__(self, parent):
        super().__init__(parent)
        self.worker = None
        self.on_result = self.on_error = self.on_update = None

    @property
    def busy(self):
        return self.worker is not None

    def start(self, function, result, error, update=lambda _: None):
        if self.busy:
            return False
        self.on_result, self.on_error, self.on_update = result, error, update
        self.worker = Worker(function, self)
        self.worker.result.connect(self.received)
        self.worker.failure.connect(self.failed)
        self.worker.update.connect(self.updated)
        self.worker.finished.connect(self.finished)
        self.busyChanged.emit(True)
        self.worker.start()
        return True

    @Slot(object)
    def received(self, value):
        self.on_result(value)

    @Slot(str)
    def failed(self, value):
        self.on_error(value)

    @Slot(object)
    def updated(self, value):
        self.on_update(value)

    @Slot()
    def finished(self):
        old, self.worker = self.worker, None
        old.deleteLater()
        self.busyChanged.emit(False)


def with_api(key, operation):
    api = DapdClient(key)
    try:
        return operation(api)
    finally:
        api.close()


class ConnectionDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.projects = None
        self.setWindowTitle("连接 DAPD")
        self.setMinimumWidth(550)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(label("连接 DAPD", "section"))
        layout.addWidget(label("在 DAPD 的个人设置 → 安全设置中生成 API Key。", "muted"))
        layout.addWidget(label("API Key"))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("粘贴完整的 dapd_ 开头的 API Key")
        self.key.setAccessibleName("DAPD API Key")
        try:
            self.key.setText(store.load_key())
        except ValueError:
            pass
        layout.addWidget(self.key)
        layout.addWidget(label("密钥使用 Windows 加密保存在本机。程序包不包含任何账号密钥。", "muted"))
        self.status = label("")
        layout.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch()
        self.cancel = button("取消", self.reject)
        self.save = button("验证并保存", self.connect_key, True)
        row.addWidget(self.cancel)
        row.addWidget(self.save)
        layout.addLayout(row)
        self.runner = Runner(self)
        self.runner.busyChanged.connect(self.busy_changed)
        self.key.returnPressed.connect(self.connect_key)

    def busy_changed(self, busy):
        self.key.setEnabled(not busy)
        self.cancel.setEnabled(not busy)
        self.save.setEnabled(not busy)
        if not busy and self.projects is not None:
            self.accept()

    def connect_key(self):
        import re
        key = self.key.text().strip()
        if not re.fullmatch(r"dapd_[0-9a-f]{64}", key):
            self.status.setText("API Key 格式不正确，请复制完整密钥。")
            return
        self.status.setText("正在验证连接…")
        def save(_):
            projects = with_api(key, lambda api: api.projects())
            self.store.save_key(key)
            return projects
        self.runner.start(save, self.connected, self.status.setText)

    def connected(self, projects):
        self.projects = projects

    def reject(self):
        if not self.runner.busy:
            super().reject()


class ParentDialog(QDialog):
    def __init__(self, key, project, group, parent=None):
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
        self.runner = Runner(self)
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


class TemplateDialog(QDialog):
    def __init__(self, store, template=None, parent=None, people=None):
        super().__init__(parent)
        self.store, self.template = store, template
        self.saved_id = None
        self.setWindowTitle("编辑模板" if template else "新建模板")
        self.resize(1120, 760)
        self.setMinimumSize(980, 680)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        form = QFormLayout()
        self.name = QLineEdit(template["name"] if template else "")
        self.name.setPlaceholderText("给这个模板起个名字")
        form.addRow("模板名称", self.name)
        layout.addLayout(form)
        layout.addWidget(label("主任务标题在创建时输入。双击子任务改名；选中任意节点，编辑其固定描述、图片和附件。", "muted"))
        row = QHBoxLayout()
        row.addWidget(button("添加同级", self.add_sibling))
        row.addWidget(button("添加子任务", self.add_child))
        row.addWidget(button("删除节点", self.remove))
        row.addStretch()
        layout.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("任务层级")
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.root = QTreeWidgetItem(["主任务标题（创建时填写）"])
        self.root.setData(0,Qt.ItemDataRole.UserRole,(template or {}).get("root",empty_content()))
        self.tree.addTopLevelItem(self.root)
        items = []
        for node in (template or {}).get("nodes", []):
            parent_item = self.root if node["parent"] is None else items[node["parent"]]
            items.append(self.new_item(node["title"], parent_item,node.get("content",empty_content())))
        self.tree.expandAll()
        self.tree.setCurrentItem(self.root)
        split=QSplitter()
        split.addWidget(self.tree)
        self.editor=ContentEditor(store.directory)
        if people:
            self.editor.set_people(people)
        split.addWidget(self.editor)
        split.setSizes([380,650])
        layout.addWidget(split,1)
        self.editing_item=self.root
        self.editor.set_content(self.root.data(0,Qt.ItemDataRole.UserRole))
        self.tree.currentItemChanged.connect(self.node_changed)
        row = QHBoxLayout()
        row.addWidget(button("上移", lambda: self.move(-1)))
        row.addWidget(button("下移", lambda: self.move(1)))
        row.addWidget(button("降为子级", self.indent))
        row.addWidget(button("升为上级", self.outdent))
        row.addStretch()
        layout.addLayout(row)
        self.error = label("")
        layout.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("取消", self.reject))
        row.addWidget(button("保存模板", self.save, True))
        layout.addLayout(row)
        self.initial = (self.name.text(), self.nodes(),self.root.data(0,Qt.ItemDataRole.UserRole))

    def new_item(self, title, parent, content=None):
        item = QTreeWidgetItem([title])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setData(0,Qt.ItemDataRole.UserRole,content if content is not None else empty_content())
        parent.addChild(item)
        return item

    def flush_content(self):
        if self.editing_item is not None:
            self.editing_item.setData(0,Qt.ItemDataRole.UserRole,self.editor.content())

    def node_changed(self,current,previous):
        if previous is not None and previous is self.editing_item:
            try:
                self.flush_content()
            except ValueError as exc:
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(previous)
                self.tree.blockSignals(False)
                self.error.setText(str(exc))
                return
        self.editing_item=current
        self.editor.setEnabled(current is not None)
        if current:
            self.editor.heading.setText("固定描述 · " + ("主任务" if current is self.root else current.text(0)))
            self.editor.set_content(current.data(0,Qt.ItemDataRole.UserRole) or empty_content())

    def add_sibling(self):
        current = self.tree.currentItem() or self.root
        parent = current.parent() or self.root
        item = self.new_item("新任务", parent)
        if current is not self.root:
            parent.takeChild(parent.indexOfChild(item))
            parent.insertChild(parent.indexOfChild(current) + 1, item)
        parent.setExpanded(True)
        self.tree.setCurrentItem(item)
        self.tree.editItem(item, 0)

    def add_child(self):
        parent = self.tree.currentItem() or self.root
        item = self.new_item("新任务", parent)
        parent.setExpanded(True)
        self.tree.setCurrentItem(item)
        self.tree.editItem(item, 0)

    def remove(self):
        item = self.tree.currentItem()
        if item and item is not self.root:
            if item.childCount() and not confirm(self, "删除这个节点及其所有子任务？", "删除"):
                return
            parent=item.parent()
            self.tree.setCurrentItem(parent)
            parent.removeChild(item)

    def move(self, step):
        item = self.tree.currentItem()
        if not item or item is self.root:
            return
        parent = item.parent()
        index = parent.indexOfChild(item)
        if 0 <= index + step < parent.childCount():
            parent.takeChild(index)
            parent.insertChild(index + step, item)
            self.tree.setCurrentItem(item)

    def indent(self):
        item = self.tree.currentItem()
        if not item or item is self.root:
            return
        parent = item.parent()
        index = parent.indexOfChild(item)
        if index:
            new_parent = parent.child(index - 1)
            parent.takeChild(index)
            new_parent.addChild(item)
            new_parent.setExpanded(True)
            self.tree.setCurrentItem(item)

    def outdent(self):
        item = self.tree.currentItem()
        if not item or item is self.root or item.parent() is self.root:
            return
        parent = item.parent()
        grandparent = parent.parent()
        parent.takeChild(parent.indexOfChild(item))
        grandparent.insertChild(grandparent.indexOfChild(parent) + 1, item)
        self.tree.setCurrentItem(item)

    def nodes(self):
        if hasattr(self,"editing_item"):
            self.flush_content()
        result = []
        def walk(parent, parent_index):
            for index in range(parent.childCount()):
                item = parent.child(index)
                position = len(result)
                node={"title": item.text(0), "parent": parent_index}
                content=item.data(0,Qt.ItemDataRole.UserRole) or empty_content()
                if content["parts"] or content["attachments"] or content.get("html") or content.get("assignee"):
                    node["content"]=content
                result.append(node)
                walk(item, position)
        walk(self.root, None)
        return result

    def save(self):
        self.tree.clearFocus()
        try:
            nodes=self.nodes()
            self.saved_id = self.store.save_template(self.name.text(), nodes, (self.template or {}).get("id"),self.root.data(0,Qt.ItemDataRole.UserRole))
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()

    def reject(self):
        if (self.name.text(), self.nodes(),self.root.data(0,Qt.ItemDataRole.UserRole)) != self.initial and not confirm(self, "模板尚未保存，放弃本次修改？", "放弃修改"):
            return
        super().reject()


def fill_plan(tree, plan):
    tree.clear()
    items = []
    for node in plan["nodes"]:
        item = QTreeWidgetItem([node["title"]])
        if node["parent"] is None:
            tree.addTopLevelItem(item)
        else:
            items[node["parent"]].addChild(item)
        items.append(item)
    tree.expandAll()


class PreviewDialog(QDialog):
    def __init__(self, plan, parent=None, directory=None):
        super().__init__(parent)
        self.setWindowTitle("核对创建清单")
        self.resize(1050, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        dest = plan["destination"]
        roots = sum(node["parent"] is None for node in plan["nodes"])
        total = len(plan["nodes"])
        layout.addWidget(label(f"将创建 {total} 个任务", "heading"))
        layout.addWidget(label(f"{roots} 个主任务 · {total - roots} 个模板子任务", "muted"))
        layout.addWidget(label(f"项目：{dest['projectName']}\n任务组：{dest['groupName']}\n父任务：{dest.get('parentTitle') or '无（任务组顶层）'}", "notice"))
        tree = QTreeWidget()
        tree.setHeaderLabel("创建后的层级")
        fill_plan(tree, plan)
        if directory is not None:
            split=QSplitter()
            split.addWidget(tree)
            content=ContentEditor(directory,readonly=True)
            content.note.setText("将按模板写入以下固定内容。附件会关联到这个任务。")
            split.addWidget(content)
            split.setSizes([380,600])
            items=[]
            def collect(item):
                items.append(item)
                for i in range(item.childCount()):collect(item.child(i))
            for i in range(tree.topLevelItemCount()):collect(tree.topLevelItem(i))
            for i,item in enumerate(items):item.setData(0,Qt.ItemDataRole.UserRole,i)
            def selected():
                item=tree.currentItem()
                if item:
                    content.set_content(plan["nodes"][item.data(0,Qt.ItemDataRole.UserRole)].get("content",empty_content()))
            tree.itemSelectionChanged.connect(selected)
            tree.setCurrentItem(tree.topLevelItem(0))
            layout.addWidget(split,1)
        else:
            layout.addWidget(tree,1)
        images=sum(len(image_assets(n.get("content",empty_content()))) for n in plan["nodes"])
        attachments=sum(len(n.get("content",empty_content())["attachments"]) for n in plan["nodes"])
        layout.addWidget(label(f"描述图片 {images} 张 · 附件 {attachments} 个。负责人和日期留空，停止时保留已完成进度。", "muted"))
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("返回修改", self.reject))
        row.addWidget(button(f"创建 {total} 个任务", self.accept, True))
        layout.addLayout(row)


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.key = ""
        self.parent_task = None
        self.active_job = None
        self.stop_event = threading.Event()
        self.runner = Runner(self)
        self.setWindowTitle("DAPD 任务工具")
        self.resize(1120, 800)
        self.setMinimumSize(920, 680)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(18)
        row = QHBoxLayout()
        title = QVBoxLayout()
        title.addWidget(label("DAPD 任务工具", "heading"))
        title.addWidget(label("组织任务层级，批量完成创建。", "muted"))
        row.addLayout(title, 1)
        self.connection_status = label("未连接", "muted")
        row.addWidget(self.connection_status)
        self.connect_button = button("连接设置", self.connect_dialog)
        self.refresh_button = button("刷新项目", self.load_projects)
        row.addWidget(self.refresh_button)
        row.addWidget(self.connect_button)
        layout.addLayout(row)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.build_create_tab()
        self.build_templates_tab()
        self.build_history_tab()
        from .updates_ui import UpdatesPage
        self.updates = UpdatesPage(self)
        self.tabs.addTab(self.updates, "更新与共享")
        from .task_browser import TaskBrowser
        self.task_browser = TaskBrowser(self)
        self.tabs.addTab(self.task_browser, "我创建的任务")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.status = label("首次使用请连接 DAPD。模板库初始为空，可在“我的模板”中新建。", "muted")
        row.addWidget(self.status, 1)
        self.stop_button = button("停止创建", self.stop_creation)
        self.stop_button.setVisible(False)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        self.runner.busyChanged.connect(self.busy_changed)
        self.refresh_templates()
        self.refresh_history()
        self.busy_changed(False)

    def build_create_tab(self):
        self.create_page = QWidget()
        self.tabs.addTab(self.create_page, "创建任务")
        layout = QVBoxLayout(self.create_page)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(18)
        self.destination_box = QWidget()
        form = QFormLayout(self.destination_box)
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
        layout.addWidget(self.destination_box)
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
        row.addWidget(button("管理模板", lambda: self.tabs.setCurrentIndex(1)))
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
        self.project.currentIndexChanged.connect(self.project_changed)
        self.group.currentIndexChanged.connect(self.group_changed)
        self.batch_entries.changed.connect(self.update_count)
        self.template_combo.currentIndexChanged.connect(self.update_count)

    def build_templates_tab(self):
        page = QWidget()
        self.tabs.addTab(page, "我的模板")
        layout = QVBoxLayout(page)
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

    def build_history_tab(self):
        page = QWidget()
        self.tabs.addTab(page, "创建记录")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(12)
        self.history_info = label("每次创建都会保存记录。暂停后可继续，已成功的任务不会再次提交。", "muted")
        layout.addWidget(self.history_info)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.history = QTreeWidget()
        self.history.setRootIsDecorated(False)
        self.history.setHeaderLabels(["创建时间", "项目 / 任务组", "进度", "状态"])
        self.history.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.history.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.history.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.records = QTreeWidget()
        self.records.setHeaderLabels(["任务标题", "状态", "任务 ID"])
        self.records.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.records.setColumnWidth(1, 160)
        self.records.setColumnWidth(2, 290)
        splitter.addWidget(self.history)
        splitter.addWidget(self.records)
        splitter.setSizes([170, 300])
        layout.addWidget(splitter, 1)
        self.record_message = label("暂无创建记录。", "muted")
        layout.addWidget(self.record_message)
        row = QHBoxLayout()
        self.open_button = button("打开所选任务", self.open_selected)
        self.export_button = button("导出记录", self.export_record)
        self.resolve_button = button("关联已创建任务", self.resolve_selected)
        self.reset_button = button("确认未创建", self.reset_selected)
        self.reset_uploads_button=button("确认文件未上传",self.reset_selected_uploads)
        self.resume_button = button("继续此批次", self.resume, True)
        for b in (self.open_button, self.export_button, self.resolve_button, self.reset_button,self.reset_uploads_button):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.resume_button)
        layout.addLayout(row)
        self.history.itemSelectionChanged.connect(self.show_job)
        self.records.itemSelectionChanged.connect(self.record_selected)
        self.records.itemDoubleClicked.connect(lambda *_: self.open_selected())

    def start(self):
        try:
            self.key = self.store.load_key()
        except ValueError as exc:
            self.status.setText(str(exc))
        if self.key:
            self.load_projects()

        self.updates.start()

    def connect_dialog(self):
        dialog = ConnectionDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.key = self.store.load_key()
            self.set_projects(dialog.projects)
            self.status.setText("连接成功，请选择项目和任务组。")

    def load_projects(self):
        if not self.key:
            self.connect_dialog()
            return
        if self.runner.busy:
            return
        self.project.blockSignals(True)
        self.project.clear()
        self.project.addItem("正在加载项目…", None)
        self.project.blockSignals(False)
        self.clear_groups()
        self.status.setText("正在读取 DAPD 项目…")
        self.runner.start(lambda _: with_api(self.key, lambda api: api.projects()), self.set_projects, self.network_error)

    def set_projects(self, projects):
        self.project.blockSignals(True)
        self.project.clear()
        self.project.addItem("请选择项目" if projects else "此账号没有可用项目", None)
        for project in projects:
            self.project.addItem(project["name"], project)
        self.project.blockSignals(False)
        self.clear_groups()
        self.connection_status.setText("已连接 DAPD")
        self.status.setText(f"已读取 {len(projects)} 个项目。")

    def clear_groups(self):
        self.group.blockSignals(True)
        self.group.clear()
        self.group.addItem("请先选择项目", None)
        self.group.blockSignals(False)
        self.clear_parent()

    def project_changed(self):
        self.clear_groups()
        project = self.project.currentData()
        if project is None or self.runner.busy:
            return
        self.group.setItemText(0, "正在加载任务组…")
        self.status.setText("正在读取任务组…")
        self.runner.start(lambda _: with_api(self.key, lambda api: api.groups(project["id"])), self.set_groups, self.network_error)

    def set_groups(self, groups):
        self.group.clear()
        groups = [g for g in groups if g.get("status") != "archived"]
        self.group.addItem("请选择任务组" if groups else "这个项目没有可用任务组", None)
        for group in groups:
            self.group.addItem(group["name"], group)
        self.status.setText(f"已读取 {len(groups)} 个任务组。请选择任务组。")

    def group_from_link(self):
        if not self.key:
            self.connect_dialog()
            if not self.key:
                return
        value, accepted = QInputDialog.getText(self, "粘贴任务组链接", "粘贴任务组链接，或 DAPD 复制出的整段文字（含名称和链接）：")
        if not accepted:
            return
        try:
            identifier = group_id_from_text(value)
        except ValueError as exc:
            message(self, str(exc))
            return
        self.status.setText("正在按链接定位项目和任务组…")
        self.runner.start(lambda _: with_api(self.key, lambda api: locate_group(api, identifier)), self.group_located, self.network_error)

    def project_from_link(self):
        if not self.key:
            self.connect_dialog()
            if not self.key:return
        value,accepted=QInputDialog.getText(self,"粘贴项目链接","粘贴项目链接，或 DAPD 复制出的整段项目文字：")
        if not accepted:return
        try:identifier=project_id_from_text(value)
        except ValueError as exc:
            message(self,str(exc));return
        def locate(api):
            projects=api.projects()
            project=next((p for p in projects if p['id']==identifier),None)
            if not project:raise ValueError("当前账号无法访问这个项目，请检查链接或项目权限。")
            return {"projects":projects,"project":project,"groups":api.groups(identifier)}
        self.status.setText("正在按链接定位项目…")
        self.runner.start(lambda _:with_api(self.key,locate),self.project_located,self.network_error)

    def project_located(self,result):
        self.set_projects(result["projects"])
        self.project.blockSignals(True)
        for index in range(self.project.count()):
            if (self.project.itemData(index) or {}).get("id")==result["project"]["id"]:
                self.project.setCurrentIndex(index);break
        self.project.blockSignals(False)
        self.set_groups(result["groups"])
        self.status.setText(f"已定位项目：{result['project']['name']}。请选择任务组。")

    def group_located(self, result):
        self.set_projects(result["projects"])
        self.project.blockSignals(True)
        for index in range(self.project.count()):
            if (self.project.itemData(index) or {}).get("id") == result["project"]["id"]:
                self.project.setCurrentIndex(index)
                break
        self.project.blockSignals(False)
        self.set_groups(result["groups"])
        for index in range(self.group.count()):
            if (self.group.itemData(index) or {}).get("id") == result["group"]["id"]:
                self.group.setCurrentIndex(index)
                break
        self.status.setText(f"已定位：{result['project']['name']} / {result['group']['name']}。可继续选择父任务。")

    def group_changed(self):
        self.clear_parent()
        self.busy_changed(self.runner.busy)

    def choose_parent(self):
        project, group = self.project.currentData(), self.group.currentData()
        if not project or not group:
            message(self, "请先选择项目和任务组。")
            return
        dialog = ParentDialog(self.key, project, group, self)
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

    def preview(self):
        try:
            if self.mode.currentIndex() == 0:
                plan = make_plan([self.single_title.text()], [], self.destination())
            else:
                plan = make_batch_plan(self.batch_entries.entries(), self.destination())
            assets=Assets(self.store.directory)
            for node in plan["nodes"]:
                content=node["content"]
                for asset in [*description_assets(content).values(),*content["attachments"]]:assets.path(asset,verify_hash=True)
        except ValueError as exc:
            message(self, str(exc))
            return
        if PreviewDialog(plan, self,self.store.directory).exec() == QDialog.DialogCode.Accepted:
            self.start_job(self.store.add_job(plan))

    def update_count(self):
        count = self.batch_entries.table.rowCount()
        total = 0
        for row in range(count):
            combo = self.batch_entries.table.cellWidget(row, 1)
            template = combo.currentData() if combo else None
            total += len(template["nodes"]) + 1 if template else 0
        self.batch_count.setText(f"{count} 个主任务 · 共 {total} 个任务节点。每行可选择不同模板。")

    def refresh_templates(self, selected=None):
        previous = selected or (self.template_combo.currentData() or {}).get("id")
        templates = self.store.templates()
        from .content_packs import load_shared
        try:
            templates += load_shared(self.store.directory)["templates"]
        except Exception:
            self.status.setText("共享模板无法读取，可在“更新与共享”重新同步。")
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItem("请选择模板" if templates else "暂无模板，请先新建", None)
        self.template_list.clear()
        for template in templates:
            prefix = "共享 · " if template.get("shared") else ""
            self.template_combo.addItem(prefix + template["name"], template)
            item = QListWidgetItem(f"{prefix}{template['name']}\n{len(template['nodes'])} 个子任务" + (f" · v{template['content_version']}" if template.get("shared") else ""))
            item.setData(Qt.ItemDataRole.UserRole, template)
            self.template_list.addItem(item)
            if template["id"] == previous:
                self.template_combo.setCurrentIndex(self.template_combo.count() - 1)
                self.template_list.setCurrentItem(item)
        self.template_combo.blockSignals(False)
        self.batch_entries.set_templates(templates)
        self.template_empty.setVisible(not templates)
        self.template_selected()
        self.update_count()

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
                self.status.setText("模板已保存。")
        if self.key:
            self.status.setText("正在读取可选负责人…")
            project = self.project.currentData()
            self.runner.start(lambda _: with_api(self.key, lambda api: load_people(api, project)), opened, lambda error: message(self, error))
        else:
            opened(None)

    def import_template_file(self):
        from .template_files import import_templates
        path, _ = QFileDialog.getOpenFileName(self, "导入模板", "", "DAPD 模板 (*.dapd-template)")
        if path:
            self.runner.start(lambda _: import_templates(self.store, path), self.templates_imported, lambda error: message(self, error))

    def templates_imported(self, identifiers):
        self.refresh_templates(identifiers[-1] if identifiers else None)
        self.status.setText(f"已导入 {len(identifiers)} 个个人模板，同名模板会另存副本。")

    def export_template_file(self):
        from .template_files import export_templates
        item = self.template_list.currentItem()
        if not item:
            message(self, "请先选择要导出的模板。")
            return
        template = item.data(Qt.ItemDataRole.UserRole)
        path, _ = QFileDialog.getSaveFileName(self, "导出模板（包含图片和附件）", "模板.dapd-template", "DAPD 模板 (*.dapd-template)")
        if path:
            self.runner.start(lambda _: export_templates(self.store, [template], path), lambda _: self.status.setText("模板已导出：" + path), lambda error: message(self, error))

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
        from .updates_ui import ExportContentDialog
        ExportContentDialog(self.store, self).exec()

    def delete_selected_template(self):
        item = self.template_list.currentItem()
        if item:
            template = item.data(Qt.ItemDataRole.UserRole)
            if template.get("shared"):
                return
            if confirm(self, f"删除模板“{template['name']}”？已有 DAPD 任务和创建记录会保留。", "删除模板"):
                self.store.delete_template(template["id"])
                self.refresh_templates()

    def refresh_history(self, selected=None):
        current = self.history.currentItem()
        selected = selected or (current.data(0, Qt.ItemDataRole.UserRole) if current else None)
        self.history.blockSignals(True)
        self.history.clear()
        for job in self.store.jobs():
            dest = json.loads(job["plan"])["destination"]
            item = QTreeWidgetItem([job["created"][:19].replace("T", " "), f"{dest['projectName']} / {dest['groupName']}", f"{job['done']} / {job['total']}", STATUS[job["status"]]])
            item.setData(0, Qt.ItemDataRole.UserRole, job["id"])
            self.history.addTopLevelItem(item)
            if selected == job["id"]:
                self.history.setCurrentItem(item)
        self.history.blockSignals(False)
        if self.history.currentItem() is None and self.history.topLevelItemCount():
            self.history.setCurrentItem(self.history.topLevelItem(0))
        self.show_job()

    def selected_job(self):
        item = self.history.currentItem()
        return self.store.job(item.data(0, Qt.ItemDataRole.UserRole)) if item else None

    def show_job(self):
        job = self.selected_job()
        previous = self.records.currentItem()
        position = previous.data(0, Qt.ItemDataRole.UserRole) if previous else None
        self.records.clear()
        if job:
            items = []
            for row, node in zip(job["nodes"], job["plan"]["nodes"]):
                item = QTreeWidgetItem([node["title"], STATUS[row["status"]], row["task_id"] or ""])
                item.setData(0, Qt.ItemDataRole.UserRole, row["position"])
                if node["parent"] is None:
                    self.records.addTopLevelItem(item)
                else:
                    items[node["parent"]].addChild(item)
                items.append(item)
                if position == row["position"]:
                    self.records.setCurrentItem(item)
            self.records.expandAll()
            dest = job["plan"]["destination"]
            self.record_message.setText(job["error"] or f"父任务：{dest.get('parentTitle') or '无（任务组顶层）'}")
        else:
            self.record_message.setText("暂无创建记录。")
        self.record_selected()

    def record_selected(self):
        job = self.selected_job()
        item = self.records.currentItem()
        row = job["nodes"][item.data(0, Qt.ItemDataRole.UserRole)] if job and item else None
        unknown = bool(row and row["status"] == "unknown")
        upload_unknown=bool(row and any(u["node"]==row["position"] and u["status"] in ("started","unknown") for u in job["uploads"]))
        idle = not self.runner.busy
        self.open_button.setEnabled(bool(row and row["task_id"]))
        self.export_button.setEnabled(bool(job))
        self.resolve_button.setVisible(unknown)
        self.reset_button.setVisible(unknown)
        self.reset_uploads_button.setVisible(upload_unknown)
        self.reset_uploads_button.setEnabled(idle)
        self.resolve_button.setEnabled(idle and bool(self.key))
        self.reset_button.setEnabled(idle)
        self.resume_button.setEnabled(bool(job and job["status"] != "completed" and self.key) and idle)
        if row and row["error"]:
            self.record_message.setText(row["error"])
        elif unknown:
            self.record_message.setText("请先在 DAPD 核对：已创建则关联任务；确认未创建后才可重新提交。")
        if upload_unknown:
            self.record_message.setText("文件上传结果待核对。继续此批次会先查询已上传文件；无法确认时不会重复上传。")

    def start_job(self, identifier):
        if self.runner.busy:
            return
        self.active_job = identifier
        self.stop_event.clear()
        self.tabs.setCurrentIndex(2)
        self.refresh_history(identifier)
        self.status.setText("正在创建任务…")
        self.runner.start(lambda update: with_api(self.key, lambda api: run_job(self.store, api, identifier, self.stop_event, update)), self.job_finished, self.network_error, self.job_progress)

    def job_progress(self, job):
        done = sum(n["status"] == "created" for n in job["nodes"])
        total = len(job["nodes"])
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.status.setText(f"已创建并核对 {done} / {total} 个任务。")
        self.refresh_history(job["id"])

    def job_finished(self, job):
        self.job_progress(job)
        if job["status"] == "completed":
            self.status.setText(f"创建完成：{len(job['nodes'])} 个任务。可选中任务打开 DAPD，或导出创建记录。")
        else:
            self.status.setText(f"{STATUS[job['status']]}。{job['error'] or '已成功的任务已保留，可稍后继续。'}")
        self.active_job = None

    def stop_creation(self):
        self.stop_event.set()
        self.stop_button.setEnabled(False)
        self.status.setText("正在停止：等待当前请求结束，然后保留进度。")

    def resume(self):
        job = self.selected_job()
        if not job:
            return
        if any(n["status"] == "unknown" for n in job["nodes"]):
            message(self, "请先选中“结果待核对”的任务，关联已创建任务或确认未创建。")
            return
        remaining = sum(n["status"] != "created" for n in job["nodes"])
        if confirm(self, f"继续此批次的 {remaining} 个未完成任务？\n将使用记录中原来的项目、任务组和父任务。", "继续创建"):
            self.start_job(job["id"])

    def open_selected(self):
        job, item = self.selected_job(), self.records.currentItem()
        if job and item:
            open_task(job["nodes"][item.data(0, Qt.ItemDataRole.UserRole)]["task_id"])

    def export_record(self):
        job = self.selected_job()
        if not job:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出创建记录", "DAPD创建记录.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as output:
                writer = csv.writer(output)
                writer.writerow(["序号", "标题", "父节点序号", "状态", "任务 ID", "链接"])
                for row, node in zip(job["nodes"], job["plan"]["nodes"]):
                    title = node["title"]
                    if title.startswith(("=", "+", "-", "@", "\t", "\r")):
                        title = "'" + title
                    writer.writerow([row["position"] + 1, title, "" if node["parent"] is None else node["parent"] + 1,
                                     STATUS[row["status"]], row["task_id"] or "", task_url(row["task_id"]) if row["task_id"] else ""])
            self.status.setText("创建记录已导出。")
        except OSError:
            message(self, "无法写入文件，请选择可写目录，并关闭正在使用此文件的程序。")

    def resolve_selected(self):
        job, item = self.selected_job(), self.records.currentItem()
        if not job or not item:
            return
        index = item.data(0, Qt.ItemDataRole.UserRole)
        value, accepted = QInputDialog.getText(self, "关联已创建任务", "粘贴已核对的 DAPD 任务链接或任务 ID：")
        if accepted and value.strip():
            try:
                identifier = task_id_from_text(value)
            except ValueError as exc:
                message(self, str(exc))
                return
            if not identifier:
                message(self, "请输入完整的 DAPD 任务链接或任务 ID。")
                return
            self.runner.start(lambda _: with_api(self.key, lambda api: resolve_unknown(self.store, api, job["id"], index, identifier)),
                              lambda _: self.refresh_history(job["id"]), self.network_error)

    def reset_selected(self):
        job, item = self.selected_job(), self.records.currentItem()
        if not job or not item:
            return
        index = item.data(0, Qt.ItemDataRole.UserRole)
        title = job["plan"]["nodes"][index]["title"]
        if confirm(self, f"请先在 DAPD 中核对“{title}”确实没有创建成功。\n如果它已存在，再次提交会生成重复任务。", "已核对未创建"):
            reset_absent(self.store, job["id"], index)
            self.refresh_history(job["id"])

    def reset_selected_uploads(self):
        job,item=self.selected_job(),self.records.currentItem()
        if not job or not item:return
        index=item.data(0,Qt.ItemDataRole.UserRole)
        names=[u['name'] for u in job['uploads'] if u['node']==index and u['status'] in ('unknown','started')]
        if confirm(self,"请先在 DAPD 任务附件或项目文件中核对这些文件确实不存在：\n"+'\n'.join(names)+"\n\n如果文件已存在，重新上传可能重复。", "已核对未上传"):
            reset_absent_uploads(self.store,job['id'],index)
            self.refresh_history(job['id'])

    def network_error(self, text):
        self.status.setText(text)
        self.active_job = None
        self.refresh_history()

    def busy_changed(self, busy):
        self.connect_button.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
        self.create_page.setEnabled(not busy)
        self.parent_button.setEnabled(bool(self.group.currentData()) and not busy)
        self.clear_parent_button.setEnabled(bool(self.parent_task) and not busy)
        self.preview_button.setEnabled(bool(self.group.currentData()) and bool(self.key) and not busy)
        self.stop_button.setVisible(busy and bool(self.active_job))
        self.stop_button.setEnabled(not self.stop_event.is_set())
        self.record_selected()

    def closeEvent(self, event):
        if self.updates.runner.busy:
            message(self, "正在下载或检查更新，请等待当前操作结束后关闭。")
            event.ignore()
        elif self.runner.busy:
            if self.active_job:
                self.stop_creation()
            message(self, "正在等待当前网络请求结束。进度会保留，请稍后关闭窗口。")
            event.ignore()
        else:
            event.accept()


def configure_app(app):
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setWindowIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
    app.setStyleSheet(STYLE)
    app.no_tooltips = NoTooltips(app)
    app.installEventFilter(app.no_tooltips)
