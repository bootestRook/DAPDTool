import threading
from dapd_api import DapdError
from dapd_tool.engine import reset_absent, resolve_unknown
from dapd_tool.model import make_plan, node_payload
from dapd_tool.storage import Store
from creation_fixture import CreationCase

class CreationEngineTests(CreationCase):
    def test_nested_batch_exact_hierarchy_and_no_optional_fields(self):
        job = self.run_job(self.add())
        self.assertEqual(job["status"], "completed")
        self.assertEqual(len(self.tasks), 10)
        for offset in (0, 5):
            for child, parent in [(0, "container"), (1, 0), (2, 1), (3, 2), (4, 0)]:
                task = self.tasks[job["nodes"][offset + child]["task_id"]]
                if isinstance(parent, int):
                    parent = job["nodes"][offset + parent]["task_id"]
                self.assertEqual(task["parentTaskId"], parent)
                self.assertEqual(task["title"], job["plan"]["nodes"][offset + child]["title"])
                self.assertEqual(task["taskGroupId"], "g")
                self.assertEqual(set(task), {"id", "title", "projectId", "taskGroupId", "parentTaskId"})
        self.assert_display_matches_plan(job)

    def test_top_level_batch_matches_input_order(self):
        destination = {"projectId": "p", "taskGroupId": "g"}
        identifier = self.store.add_job(make_plan(["第一项", "第二项", "第三项"], [], destination))
        job = self.run_job(identifier)
        self.assertEqual(job["status"], "completed")
        self.assertEqual([node["title"] for node in job["plan"]["nodes"]], ["第一项", "第二项", "第三项"])
        self.assert_display_matches_plan(job)

    def test_sibling_order_at_every_level_with_interleaved_template(self):
        tree = [
            {"title": "第一项", "parent": None},
            {"title": "第二项", "parent": None},
            {"title": "第一项的子任务甲", "parent": 0},
            {"title": "第一项的子任务乙", "parent": 0},
            {"title": "子任务甲的子任务一", "parent": 2},
            {"title": "子任务甲的子任务二", "parent": 2},
            {"title": "第二项的子任务", "parent": 1},
            {"title": "第三项", "parent": None},
        ]
        job = self.run_job(self.add(tree=tree))
        self.assertEqual(job["status"], "completed")
        created = list(self.tasks)
        for index, task in enumerate(self.tasks.values()):
            parent = task.get("parentTaskId")
            if parent != "container":
                self.assertIn(parent, created[:index])
        self.assert_display_matches_plan(job)

    def test_empty_task_top_level_omits_parent(self):
        plan = make_plan(["空任务"], [], {"projectId": "p", "taskGroupId": "g"})
        self.assertEqual(node_payload(plan, 0, {}), {"title": "空任务", "projectId": "p", "taskGroupId": "g"})

    def test_resume_completed_is_idempotent(self):
        identifier = self.add()
        self.run_job(identifier)
        job = self.run_job(identifier)
        self.assertEqual(self.api.create.call_count, 10)
        self.assert_display_matches_plan(job)

    def test_cancel_and_resume_never_recreates_success(self):
        identifier = self.add()
        stop = threading.Event()

        def stop_after_siblings(job):
            if sum(row["status"] == "created" for row in job["nodes"]) == 3:
                stop.set()

        job = self.run_job(identifier, stop, stop_after_siblings)
        self.assertEqual(job["status"], "paused")
        self.assertEqual(len(self.tasks), 3)
        self.store = Store(self.temp.name)
        job = self.run_job(identifier)
        self.assertEqual(self.api.create.call_count, 10)
        self.assert_display_matches_plan(job)

    def test_timeout_stops_and_blocks_automatic_retry(self):
        identifier = self.add()
        self.api.create.side_effect = DapdError("网络失败", uncertain=True)
        job = self.run_job(identifier)
        self.assertEqual(job["nodes"][5]["status"], "unknown")
        self.assertEqual(job["status"], "blocked")
        self.run_job(identifier)
        self.assertEqual(self.api.create.call_count, 1)

    def test_known_write_with_failed_readback_only_rechecks(self):
        identifier = self.add()
        self.api.task.side_effect = DapdError("网络失败")
        job = self.run_job(identifier)
        self.assertEqual(job["nodes"][5]["status"], "unverified")
        self.api.task.side_effect = lambda identifier: self.tasks[identifier]
        self.run_job(identifier)
        self.assertEqual(self.api.create.call_count, 10)

    def test_timeout_after_siblings_resolves_without_changing_order(self):
        identifier = self.add()

        def create_then_timeout(payload):
            task = self.create(payload)
            if len(self.tasks) == 3:
                raise DapdError("网络失败", uncertain=True)
            return task

        self.api.create.side_effect = create_then_timeout
        job = self.run_job(identifier)
        self.assertEqual(job["status"], "blocked")
        row = next(row for row in job["nodes"] if row["status"] == "unknown")
        self.assertEqual(row["position"], 6)
        resolve_unknown(self.store, self.api, identifier, row["position"], "task-2")
        self.api.create.side_effect = self.create
        job = self.run_job(identifier)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(self.api.create.call_count, 10)
        self.assert_display_matches_plan(job)

    def test_readback_mismatch_stops_children(self):
        identifier = self.add()
        self.api.task.side_effect = lambda identifier: dict(self.tasks[identifier], parentTaskId="wrong")
        job = self.run_job(identifier)
        self.assertEqual(job["status"], "paused")
        self.assertEqual(self.api.create.call_count, 1)

    def test_server_rejection_is_retryable_but_not_automatically(self):
        identifier = self.add()
        self.api.create.side_effect = DapdError("请求被拒绝")
        job = self.run_job(identifier)
        self.assertEqual(job["nodes"][5]["status"], "failed")
        self.assertEqual(self.api.create.call_count, 1)
        self.api.create.side_effect = self.create
        self.run_job(identifier)
        self.assertEqual(len(self.tasks), 10)

    def test_crash_started_recovers_as_unknown(self):
        identifier = self.add()
        self.store.set_job(identifier, "running")
        self.store.set_node(identifier, 0, "started", payload=node_payload(self.store.job(identifier)["plan"], 0, {}))
        self.store.recover_interrupted()
        job = self.run_job(identifier)
        self.assertEqual(job["status"], "blocked")
        self.api.create.assert_not_called()

    def test_resolve_unknown_checks_scope_then_resumes(self):
        identifier = self.add()
        payload = node_payload(self.store.job(identifier)["plan"], 0, {})
        self.store.set_node(identifier, 0, "unknown", payload=payload)
        task = self.create(payload)
        self.tasks["wrong"] = dict(task, id="wrong", taskGroupId="other")
        with self.assertRaises(ValueError):
            resolve_unknown(self.store, self.api, identifier, 0, "wrong")
        del self.tasks["wrong"]
        resolve_unknown(self.store, self.api, identifier, 0, task["id"])
        self.run_job(identifier)
        self.assertEqual(self.api.create.call_count, 9)

    def test_explicit_absent_reset_only_on_unknown(self):
        identifier = self.add()
        with self.assertRaises(ValueError):
            reset_absent(self.store, identifier, 0)
        self.store.set_node(identifier, 0, "unknown", payload={"title": "a"})
        reset_absent(self.store, identifier, 0)
        self.assertEqual(self.store.job(identifier)["nodes"][0]["status"], "pending")
