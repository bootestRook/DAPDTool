import copy
import json
import os
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from dapd_api import DapdClient, DapdError
from dapd_tool.tasks import list_created_tasks, task_hierarchy


def task(identifier, parent=None, **values):
    return {"id": identifier, "title": identifier, "projectId": "p", "taskGroupId": "g",
            "createdById": "me", "parentTaskId": parent, "status": "active", "priority": "medium", **values}


def snapshot(tasks, project="p", complete=True):
    return {"tasks": tasks, "project_id": project, "user": {"id": "me", "name": "我"},
            "own_ids": {t["id"] for t in tasks if not t.get("contextOnly")},
            "groups": {"g": "任务组"}, "statuses": {project: {"active": "进行中"}}, "complete": complete}


class TaskReadTests(unittest.TestCase):
    def make_api(self, tasks, parents=None, override=None):
        self.calls = []

        def handler(request):
            name = request.url.path.split("/")[-1]
            payload = json.loads(request.url.params["input"])
            self.calls.append((name, payload))
            if override:
                response = override(name, payload)
                if response is not None:
                    return response
            if name == "userSetting.getSettings":
                result = {"userId": "me"}
            elif name == "user.getById":
                result = {"id": "me", "name": "我"}
            elif name == "task.getTasks":
                self.assertEqual(payload["projectId"], "p")
                self.assertEqual(payload["createdById"], "me")
                self.assertFalse(payload["onlyRootTasks"])
                result = tasks[payload["offset"]:payload["offset"] + 100]
            elif name == "task.getTaskById":
                result = copy.deepcopy(parents[payload["id"]])
            elif name == "taskGroup.getTaskGroups":
                result = [{"id": "g", "name": "任务组"}]
            elif name == "taskStatusConfig.listByProject":
                result = [{"key": "active", "name": "进行中"}]
            else:
                self.fail(name)
            return httpx.Response(200, json={"result": {"data": result}})

        api = DapdClient("test", transport=httpx.MockTransport(handler))
        self.addCleanup(api.close)
        return api

    def test_project_pagination_and_shared_ancestor_fetched_once(self):
        tasks = [task(str(i), "parent") for i in range(201)]
        api = self.make_api(tasks, {"parent": task("parent", createdById="other")})
        progress = []
        data = list_created_tasks(api, "p", progress.append)
        self.assertTrue(data["complete"])
        self.assertEqual(len(data["own_ids"]), 201)
        self.assertEqual(len(data["tasks"]), 202)
        self.assertTrue(data["tasks"][-1]["contextOnly"])
        self.assertEqual([p["offset"] for n, p in self.calls if n == "task.getTasks"], [0, 100, 200])
        self.assertEqual(sum(n == "task.getTaskById" for n, _ in self.calls), 1)
        self.assertTrue(any("父任务" in text for text in progress))
        self.assertTrue(any("任务组" in text for text in progress))

    def test_repeated_task_page_stops(self):
        tasks = [task(str(i)) for i in range(100)]
        def repeat(name, payload):
            if name == "task.getTasks":
                return httpx.Response(200, json={"result": {"data": tasks}})
        api = self.make_api(tasks, override=repeat)
        with self.assertRaisesRegex(ValueError, "分页重复"):
            list_created_tasks(api, "p")
        self.assertEqual(sum(n == "task.getTasks" for n, _ in self.calls), 2)

    def test_repeated_group_page_stops(self):
        groups = [{"id": str(i), "name": str(i)} for i in range(100)]
        def repeat(name, payload):
            if name == "taskGroup.getTaskGroups":
                return httpx.Response(200, json={"result": {"data": groups}})
        api = self.make_api([task("a")], override=repeat)
        with self.assertRaisesRegex(ValueError, "任务组分页重复"):
            list_created_tasks(api, "p")
        self.assertEqual(sum(n == "taskGroup.getTaskGroups" for n, _ in self.calls), 2)

    def test_cycle_is_rejected_before_view_and_metadata(self):
        api = self.make_api([task("a", "b")], {"b": task("b", "a", createdById="other")})
        with self.assertRaisesRegex(ValueError, "循环"):
            list_created_tasks(api, "p")
        self.assertFalse(any(n == "taskGroup.getTaskGroups" for n, _ in self.calls))
        with self.assertRaisesRegex(ValueError, "循环"):
            task_hierarchy([task("a", "a")])

    def test_scope_is_checked_for_tasks_and_ancestors(self):
        for tasks, parents in [([task("a", projectId="other")], {}),
                               ([task("a", createdById="other")], {}),
                               ([task("a", "b")], {"b": task("b", projectId="other")})]:
            with self.subTest(tasks=tasks):
                api = self.make_api(tasks, parents)
                with self.assertRaisesRegex(ValueError, "项目|创建者"):
                    list_created_tasks(api, "p")

    def test_cancel_keeps_received_page_and_skips_next_request(self):
        stop = threading.Event()
        tasks = [task(str(i)) for i in range(200)]
        def cancel(name, payload):
            if name == "task.getTasks":
                stop.set()
        api = self.make_api(tasks, override=cancel)
        data = list_created_tasks(api, "p", stop=stop)
        self.assertFalse(data["complete"])
        self.assertEqual(len(data["own_ids"]), 100)
        self.assertEqual(sum(n == "task.getTasks" for n, _ in self.calls), 1)
        self.assertFalse(any(n == "taskGroup.getTaskGroups" for n, _ in self.calls))

    def test_cancel_during_group_pagination(self):
        stop = threading.Event()
        def cancel(name, payload):
            if name == "taskGroup.getTaskGroups":
                stop.set()
                return httpx.Response(200, json={"result": {"data": [{"id": str(i), "name": str(i)} for i in range(100)]}})
        api = self.make_api([task("a")], override=cancel)
        data = list_created_tasks(api, "p", stop=stop)
        self.assertFalse(data["complete"])
        self.assertEqual(len(data["tasks"]), 1)
        self.assertEqual(sum(n == "taskGroup.getTaskGroups" for n, _ in self.calls), 1)
        self.assertFalse(any(n == "taskStatusConfig.listByProject" for n, _ in self.calls))

    def test_empty_project_does_not_fetch_metadata(self):
        data = list_created_tasks(self.make_api([]), "p")
        self.assertTrue(data["complete"])
        self.assertEqual(data["tasks"], [])
        self.assertFalse(any(n == "taskGroup.getTaskGroups" for n, _ in self.calls))

    def test_cancel_between_identity_requests(self):
        stop = threading.Event()
        def cancel(name, payload):
            if name == "userSetting.getSettings":
                stop.set()
        data = list_created_tasks(self.make_api([], override=cancel), "p", stop=stop)
        self.assertFalse(data["complete"])
        self.assertEqual(len(self.calls), 1)

    def test_timeout_is_reported_and_never_retried(self):
        def timeout(name, payload):
            if name == "task.getTasks":
                raise httpx.ReadTimeout("slow")
        with self.assertRaisesRegex(DapdError, "超时"):
            list_created_tasks(self.make_api([], override=timeout), "p")
        self.assertEqual(sum(n == "task.getTasks" for n, _ in self.calls), 1)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtTest import QAbstractItemModelTester, QTest
from PySide6.QtWidgets import QApplication, QWidget
from dapd_tool.ui.pages.task_browser import TaskBrowser
from dapd_tool.ui.widgets.task_tree import TaskTreeModel
from dapd_tool.ui.runner import Runner
from dapd_tool.ui.activity import ActivityState
from dapd_tool.ui.session import Session
from dapd_tool.ui.theme import configure_app


class TaskBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        configure_app(cls.app)

    def setUp(self):
        self.window = QWidget()
        self.session = Session(self.window)
        self.session.set_key("test")
        self.runner = Runner(self.window, ActivityState(self.window))
        self.browser = TaskBrowser(None, self.session, self.runner, self.window)
        self.addCleanup(self.window.deleteLater)

    def wait_idle(self):
        deadline = time.monotonic() + 5
        while self.runner.busy:
            self.assertLess(time.monotonic(), deadline, "读取未结束")
            QTest.qWait(10)

    def test_model_parent_filter_and_qt_contract(self):
        model = TaskTreeModel()
        tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
        model.replace(snapshot([task("parent", contextOnly=True), task("child", "parent", title="美术特效"), task("other")]))
        model.set_query("特效")
        self.assertEqual(model.rowCount(), 1)
        parent = model.index(0, 0)
        child = model.index(0, 0, parent)
        self.assertEqual(child.data(), "美术特效")
        self.assertEqual(model.parent(child), parent)
        self.assertEqual(model.matches, 1)
        self.assertIsNone(child.data(Qt.ItemDataRole.ToolTipRole))
        model.set_query("no match")
        self.assertEqual(model.rowCount(), 0)
        model.set_query("")
        self.assertEqual(model.rowCount(), 2)
        self.assertIsNotNone(tester)

    def test_deep_hierarchy_filter_is_iterative(self):
        model = TaskTreeModel()
        model.replace(snapshot([task(str(i), str(i - 1) if i else None) for i in range(1500)]))
        model.set_query("1499")
        self.assertEqual(len(model.rows), 1500)
        self.assertEqual(model.matches, 1)

    def test_project_switch_cache_and_account_reset(self):
        self.browser.set_projects([{"id": "p", "name": "项目甲"}, {"id": "q", "name": "项目乙"}])
        with patch("dapd_tool.ui.pages.task_browser.list_created_tasks", side_effect=lambda api, p, *args: snapshot([task(p, projectId=p)], p)) as read:
            with patch("dapd_tool.ui.pages.task_browser.with_api", side_effect=lambda key, op: op(None)):
                self.browser.projects.setCurrentRow(0)
                self.wait_idle()
                self.browser.projects.setCurrentRow(1)
                self.wait_idle()
                self.browser.projects.setCurrentRow(0)
                self.assertEqual(read.call_count, 2)
        self.assertEqual(self.browser.data["project_id"], "p")
        self.assertEqual(self.browser.model.rowCount(), 1)
        self.browser.project_search.setText("乙")
        self.assertTrue(self.browser.projects.item(0).isHidden())
        self.assertFalse(self.browser.projects.item(1).isHidden())
        self.session.set_key("new-account")
        self.browser.set_projects([{"id": "p", "name": "项目甲"}])
        self.assertEqual(self.browser.cache, {})
        self.assertIsNone(self.browser.data)

    def test_error_preserves_last_data_and_reenables_controls(self):
        self.browser.set_projects([{"id": "p", "name": "项目"}])
        with patch("dapd_tool.ui.pages.task_browser.list_created_tasks", return_value=snapshot([task("a")])):
            with patch("dapd_tool.ui.pages.task_browser.with_api", side_effect=lambda key, op: op(None)):
                self.browser.projects.setCurrentRow(0)
                self.wait_idle()
        with patch("dapd_tool.ui.pages.task_browser.with_api", side_effect=DapdError("请求超时")):
            self.browser.load()
            self.wait_idle()
        self.assertIn("上次", self.browser.note.text())
        self.assertEqual(self.browser.model.rowCount(), 1)
        self.assertTrue(self.browser.refresh.isEnabled())
        self.assertTrue(self.browser.projects.isEnabled())

    def test_cancel_ui_returns_partial_data(self):
        started = threading.Event()
        def read(api, p, progress, stop):
            started.set()
            stop.wait(3)
            return snapshot([task("a")], complete=False)
        self.browser.set_projects([{"id": "p", "name": "项目"}])
        with patch("dapd_tool.ui.pages.task_browser.list_created_tasks", side_effect=read):
            with patch("dapd_tool.ui.pages.task_browser.with_api", side_effect=lambda key, op: op(None)):
                self.browser.projects.setCurrentRow(0)
                self.assertTrue(started.wait(1))
                self.assertFalse(self.browser.projects.isEnabled())
                self.browser.cancel_read()
                self.wait_idle()
        self.assertFalse(self.browser.data["complete"])
        self.assertIn("不完整", self.browser.note.text())
        self.assertIn("未读完", self.browser.projects.item(0).text())
        self.assertTrue(self.browser.cancel.isHidden())

    def test_cancel_refresh_preserves_complete_snapshot(self):
        self.browser.data = snapshot([task("a"), task("b")])
        self.browser.model.replace(self.browser.data)
        self.browser.loaded(snapshot([task("a")], complete=False))
        self.assertTrue(self.browser.data["complete"])
        self.assertEqual(self.browser.model.rowCount(), 2)
        self.assertIn("保留上次", self.browser.note.text())

    def test_model_selection_edits_own_task_and_blocks_context_only(self):
        own = task("own")
        self.browser.loaded(snapshot([task("context", contextOnly=True), own]))
        self.browser.tree.setCurrentIndex(self.browser.model.index(1, 0))
        self.assertTrue(self.browser.edit_button.isEnabled())
        with patch("dapd_tool.ui.pages.task_browser.with_api", side_effect=lambda key, op: op(None)):
            with patch("dapd_tool.ui.pages.task_browser.edit_context", return_value={"task": own}) as read:
                with patch.object(self.browser, "open_editor") as opened:
                    self.browser.edit()
                    self.wait_idle()
                    read.assert_called_once_with(None, "own")
                    opened.assert_called_once_with({"task": own})
        self.browser.tree.setCurrentIndex(self.browser.model.index(0, 0))
        self.assertFalse(self.browser.edit_button.isEnabled())
        self.browser.edit()
        self.assertFalse(self.runner.busy)
        self.assertIn("其他用户", self.browser.note.text())


if __name__ == "__main__":
    unittest.main()
