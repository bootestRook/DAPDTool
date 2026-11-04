import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
from ...engine import reset_absent, reset_absent_uploads, resolve_unknown
from ...catalog import task_id_from_text
from ..controls import label, button, message, confirm
from ..task_links import open_task
from ...records import STATUS
from dapd_api import with_api
from PySide6.QtCore import Signal
from ...records import export_job

class HistoryPage(QWidget):
    statusChanged = Signal(str)

    def __init__(self, store, session, runner, jobs, parent=None):
        super().__init__(parent)
        self.store, self.session, self.runner, self.jobs = store, session, runner, jobs
        layout = QVBoxLayout(self)
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
        runner.busyChanged.connect(self.record_selected)
        session.accountChanged.connect(self.record_selected)
        jobs.started.connect(self.refresh_history)
        jobs.progressChanged.connect(lambda job: self.refresh_history(job["id"]))
        jobs.failed.connect(self.refresh_history)
        self.refresh_history()

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

    def record_selected(self, *_):
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
        self.resolve_button.setEnabled(idle and bool(self.session.key))
        self.reset_button.setEnabled(idle)
        self.resume_button.setEnabled(bool(job and job["status"] != "completed" and self.session.key) and idle)
        if row and row["error"]:
            self.record_message.setText(row["error"])
        elif unknown:
            self.record_message.setText("请先在 DAPD 核对：已创建则关联任务；确认未创建后才可重新提交。")
        if upload_unknown:
            self.record_message.setText("文件上传结果待核对。继续此批次会先查询已上传文件；无法确认时不会重复上传。")

    def resume(self):
        job = self.selected_job()
        if not job:
            return
        if any(n["status"] == "unknown" for n in job["nodes"]):
            message(self, "请先选中“结果待核对”的任务，关联已创建任务或确认未创建。")
            return
        remaining = sum(n["status"] != "created" for n in job["nodes"])
        if confirm(self, f"继续此批次的 {remaining} 个未完成任务？\n将使用记录中原来的项目、任务组和父任务。", "继续创建"):
            self.jobs.start(job["id"])

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
            export_job(job, path)
            self.statusChanged.emit("创建记录已导出。")
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
            self.runner.start(lambda _: with_api(self.session.key, lambda api: resolve_unknown(self.store, api, job["id"], index, identifier)),
                              lambda _: self.refresh_history(job["id"]), self.statusChanged.emit)

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
