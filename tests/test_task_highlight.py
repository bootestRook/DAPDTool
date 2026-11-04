import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QAbstractItemModelTester, QSignalSpy
from PySide6.QtWidgets import QApplication, QWidget

from dapd_tool.ui.activity import ActivityState
from dapd_tool.ui.pages.task_browser import TaskBrowser
from dapd_tool.ui.runner import Runner
from dapd_tool.ui.session import Session
from dapd_tool.ui.theme import configure_app


def snapshot():
    return {"project_id": "p", "user": {"id": "me", "name": "我"}, "complete": True,
        "own_ids": {"child", "own-root"}, "groups": {}, "statuses": {}, "tasks": [
            {"id": "parent", "title": "其他人创建的父任务", "projectId": "p", "contextOnly": True},
            {"id": "child", "title": "我创建的子单", "parentTaskId": "parent", "projectId": "p"},
            {"id": "own-root", "title": "我创建的主单", "projectId": "p"}]}


class TaskHighlightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        configure_app(cls.app)

    def setUp(self):
        self.host = QWidget()
        self.session = Session(self.host)
        self.session.key = "test"
        self.runner = Runner(self.host, ActivityState(self.host))
        self.browser = TaskBrowser(None, self.session, self.runner, self.host)
        self.addCleanup(self.host.deleteLater)
        self.browser.loaded(snapshot())

    def test_default_off_and_toggle_marks_child_without_marking_foreign_parent(self):
        model = self.browser.model
        tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
        parent = model.index(0, 0)
        child = model.index(0, 0, parent)
        root = model.index(1, 0)
        self.assertFalse(self.browser.highlight_own.isChecked())
        self.assertIsNone(child.data(Qt.ItemDataRole.BackgroundRole))
        self.assertEqual(child.data(), "我创建的子单")
        self.browser.tree.setCurrentIndex(child)
        resets = QSignalSpy(model.modelReset)
        changes = QSignalSpy(model.dataChanged)

        self.browser.highlight_own.click()
        self.assertIsNone(parent.data(Qt.ItemDataRole.BackgroundRole))
        self.assertIsNotNone(child.data(Qt.ItemDataRole.BackgroundRole))
        self.assertIsNotNone(root.data(Qt.ItemDataRole.BackgroundRole))
        self.assertTrue(child.data(Qt.ItemDataRole.FontRole).bold())
        self.assertEqual(child.data(), "我创建的 · 我创建的子单")
        self.assertEqual(parent.data(), "其他人创建的父任务（父任务，仅展示）")
        self.assertEqual(self.browser.tree.currentIndex(), child)
        self.assertEqual(resets.count(), 0)
        self.assertGreater(changes.count(), 0)
        self.assertIsNone(child.data(Qt.ItemDataRole.ToolTipRole))
        self.assertIsNotNone(tester)

        self.browser.highlight_own.click()
        self.assertEqual(child.data(), "我创建的子单")
        self.assertIsNone(child.data(Qt.ItemDataRole.BackgroundRole))
        self.assertIsNone(child.data(Qt.ItemDataRole.FontRole))

    def test_highlight_survives_reload_and_filter_but_new_browser_starts_off(self):
        self.browser.highlight_own.click()
        self.browser.loaded(snapshot())
        self.browser.model.set_query("子单")
        parent = self.browser.model.index(0, 0)
        child = self.browser.model.index(0, 0, parent)
        self.assertIsNone(parent.data(Qt.ItemDataRole.BackgroundRole))
        self.assertIsNotNone(child.data(Qt.ItemDataRole.BackgroundRole))
        self.assertEqual(child.data(Qt.ItemDataRole.UserRole)["id"], "child")
        # A missing contextOnly flag must never turn an ancestor into an owned task.
        data = snapshot()
        data["tasks"][0].pop("contextOnly")
        self.browser.loaded(data)
        self.assertIsNone(self.browser.model.index(0, 0).data(Qt.ItemDataRole.BackgroundRole))
        other = TaskBrowser(None, self.session, self.runner, self.host)
        self.assertFalse(other.highlight_own.isChecked())


if __name__ == "__main__":
    unittest.main()
