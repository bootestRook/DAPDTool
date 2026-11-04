"""Compose desktop pages and connect their public signals."""
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QProgressBar, QTabBar, QTabWidget, QVBoxLayout, QWidget

from .activity import ActivityState
from .connection_controller import ConnectionController
from .controls import button, label, message
from .job_controller import JobController
from .pages.create import CreatePage
from .pages.history import HistoryPage
from .pages.task_browser import TaskBrowser
from .pages.templates import TemplatesPage
from .pages.updates import UpdatesPage
from .runner import Runner
from .session import Session


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.activity = ActivityState(self)
        self.session = Session(self)
        self.runner = Runner(self, self.activity)
        self.jobs = JobController(store, self.session, self.runner, self)
        self.connection = ConnectionController(store, self.session, self.runner, self)
        self.setWindowTitle("DAPD 任务工具")
        self.resize(1120, 800)
        self.setMinimumSize(920, 680)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(18)
        self.build_header(layout)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.build_pages(store)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.status = label("首次使用请连接 DAPD。模板库初始为空，可在“我的模板”中新建。", "muted")
        row.addWidget(self.status, 1)
        self.stop_button = button("停止创建", self.jobs.stop)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        self.connect_pages()
        self.templates_page.refresh_templates()
        self.updates.refresh_actions()
        self.busy_changed()

    def build_header(self, layout):
        row = QHBoxLayout()
        title = QVBoxLayout()
        title.addWidget(label("DAPD 任务工具", "heading"))
        title.addWidget(label("组织任务层级，批量完成创建。", "muted"))
        row.addLayout(title, 1)
        self.connection_status = label("未连接", "muted")
        row.addWidget(self.connection_status)
        self.connect_button = button("连接设置", self.connect_account)
        self.refresh_button = button("刷新项目", self.refresh_projects)
        row.addWidget(self.refresh_button)
        row.addWidget(self.connect_button)
        layout.addLayout(row)

    def build_pages(self, store):
        self.create_page = CreatePage(store, self.session, self.runner, self)
        self.templates_page = TemplatesPage(store, self.session, self.runner, self)
        self.history_page = HistoryPage(store, self.session, self.runner, self.jobs, self)
        self.updates = UpdatesPage(store, self.activity, self)
        self.task_browser = TaskBrowser(store, self.session, self.runner, self)
        for page, title in [(self.create_page, "创建任务"), (self.templates_page, "我的模板"),
                            (self.history_page, "创建记录"), (self.updates, "更新与共享"),
                            (self.task_browser, "我创建的任务")]:
            self.tabs.addTab(page, title)
        self.update_dot = QLabel()
        self.update_dot.setObjectName("updateDot")
        self.update_dot.setFixedSize(8, 8)
        self.update_dot.setAccessibleName("有可用更新")
        self.tabs.tabBar().setTabButton(self.tabs.indexOf(self.updates), QTabBar.ButtonPosition.RightSide, self.update_dot)
        self.update_dot.hide()

    def connect_pages(self):
        for source in (self.create_page, self.templates_page, self.history_page, self.jobs, self.connection):
            source.statusChanged.connect(self.status.setText)
        self.create_page.connectionRequested.connect(self.connect_account)
        self.create_page.manageTemplatesRequested.connect(lambda: self.tabs.setCurrentWidget(self.templates_page))
        self.create_page.planReady.connect(self.jobs.create)
        self.templates_page.templatesChanged.connect(self.create_page.set_templates)
        self.updates.templatesChanged.connect(self.templates_page.refresh_templates)
        self.updates.availableChanged.connect(self.show_update_available)
        self.updates.restartRequested.connect(self.close)
        self.jobs.started.connect(lambda _: self.tabs.setCurrentWidget(self.history_page))
        self.jobs.progressChanged.connect(self.show_progress)
        self.jobs.changed.connect(self.busy_changed)
        self.activity.changed.connect(self.busy_changed)
        self.connection.loading.connect(self.create_page.destination_picker.show_loading)
        self.session.projectsChanged.connect(self.show_connection)

    def start(self):
        self.connection.start()
        self.updates.start()

    def show_update_available(self, available):
        index = self.tabs.indexOf(self.updates)
        self.tabs.setTabText(index, "更新与共享（有更新）" if available else "更新与共享")
        self.tabs.tabBar().setAccessibleTabName(index, "更新与共享，有可用更新" if available else "更新与共享")
        self.update_dot.setVisible(available)

    def connect_account(self):
        self.connection.configure(self)

    def refresh_projects(self):
        if self.session.key:
            self.connection.refresh()
        else:
            self.connect_account()

    def show_connection(self, _projects):
        self.connection_status.setText("已连接 DAPD" if self.session.key else "未连接")

    def show_progress(self, job):
        self.progress.setRange(0, len(job["nodes"]))
        self.progress.setValue(sum(node["status"] == "created" for node in job["nodes"]))

    def busy_changed(self, *_):
        self.connect_button.setEnabled(not self.runner.busy)
        self.refresh_button.setEnabled(not self.runner.busy)
        self.stop_button.setVisible(bool(self.jobs.active_job))
        self.stop_button.setEnabled(not self.jobs.stop_event.is_set())

    def closeEvent(self, event):
        if self.activity.busy:
            self.jobs.stop()
            message(self, "正在等待当前操作结束。进度会保留，请稍后关闭窗口。")
            event.ignore()
        else:
            event.accept()
