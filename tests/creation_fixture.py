import tempfile
import threading
import unittest
from unittest.mock import Mock
from dapd_tool.engine import run_job
from dapd_tool.model import make_plan
from dapd_tool.storage import Store

DEST = {"projectId": "p", "taskGroupId": "g", "projectName": "项目", "groupName": "任务组", "parentTaskId": "container", "parentTitle": "总单"}
TREE = [{"title": "美术", "parent": None}, {"title": "特效", "parent": 0}, {"title": "技能特效", "parent": 1}, {"title": "程序", "parent": None}]

class CreationCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.tasks = {}
        self.siblings = {}
        self.api = Mock()
        self.api.validate_task.side_effect = lambda p: p
        self.api.create.side_effect = self.create
        self.api.task.side_effect = lambda identifier: self.tasks[identifier]

    def create(self, payload):
        task = dict(payload, id="task-" + str(len(self.tasks)))
        self.tasks[task["id"]] = task
        # DAPD inserts each new task at the front of its sibling list.
        self.siblings.setdefault(task.get("parentTaskId"), []).insert(0, task["id"])
        return task

    def add(self, titles=("示例技能一（别名一）", "示例技能二（别名二）"), tree=TREE):
        return self.store.add_job(make_plan(titles, tree, DEST))

    def run_job(self, identifier, stop=None, progress=lambda _: None):
        return run_job(self.store, self.api, identifier, stop or threading.Event(), progress)

    def assert_display_matches_plan(self, job):
        expected = {}
        for node, row in zip(job["plan"]["nodes"], job["nodes"]):
            parent = job["plan"]["destination"].get("parentTaskId") if node["parent"] is None else job["nodes"][node["parent"]]["task_id"]
            expected.setdefault(parent, []).append(row["task_id"])
        self.assertEqual(self.siblings, expected)
