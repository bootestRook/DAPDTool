import tempfile
import threading
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject

from dapd_tool.model import make_plan
from dapd_tool.storage import Store
from dapd_tool.ui.activity import ActivityState
from dapd_tool.ui.job_controller import JobController
from dapd_tool.ui.runner import Runner
from dapd_tool.ui.session import Session
from qt_fixture import QtCase


class JobControllerTests(QtCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.owner = QObject()
        self.activity = ActivityState(self.owner)
        self.runner = Runner(self.owner, self.activity)
        self.session = Session(self.owner)
        self.session.set_key("test")
        self.store = Store(self.temp.name)
        self.jobs = JobController(self.store, self.session, self.runner, self.owner)
        self.addCleanup(self.owner.deleteLater)

    def test_cancel_resume_and_progress_preserve_created_tasks(self):
        api = Mock()
        api.validate_task.side_effect = lambda payload: payload
        created = []
        submitted = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def create(payload):
            task = {**payload, "id": f"task-{len(created)}"}
            created.append(task)
            if len(created) == 1:
                submitted.set()
                release.wait(3)
            return task

        api.create.side_effect = create
        api.task.side_effect = lambda identifier: next(task for task in created if task["id"] == identifier)
        started, progress = [], []
        self.jobs.started.connect(started.append)
        self.jobs.progressChanged.connect(progress.append)
        plan = make_plan(["first", "second"], [], {"projectId": "p", "taskGroupId": "g"})
        with patch("dapd_tool.ui.job_controller.with_api", side_effect=lambda key, op: op(api)):
            self.jobs.create(plan)
            self.assertTrue(submitted.wait(1))
            self.assertTrue(self.activity.busy)
            self.assertFalse(self.jobs.start("another-job"))
            self.jobs.stop()
            release.set()
            self.wait_idle(self.activity)
            identifier = started[0]
            self.assertEqual(self.store.job(identifier)["status"], "paused")
            self.assertIsNone(self.jobs.active_job)
            self.jobs.start(identifier)
            self.wait_idle(self.activity)
        self.assertEqual(self.store.job(identifier)["status"], "completed")
        self.assertEqual(len(created), 2)
        self.assertEqual(progress[-1]["status"], "completed")
        self.assertFalse(self.jobs.stop_event.is_set())

    def test_failed_operation_releases_global_activity(self):
        errors = []
        self.jobs.statusChanged.connect(errors.append)
        identifier = self.store.add_job(make_plan(["task"], [], {"projectId": "p", "taskGroupId": "g"}))
        with patch("dapd_tool.ui.job_controller.with_api", side_effect=ValueError("cannot connect")):
            self.jobs.start(identifier)
            self.wait_idle(self.activity)
        self.assertIsNone(self.jobs.active_job)
        self.assertIn("cannot connect", errors[-1])
        self.assertFalse(self.runner.busy)
