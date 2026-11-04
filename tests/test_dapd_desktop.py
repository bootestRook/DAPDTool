import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

import httpx

from dapd_api import DapdClient, DapdError
from dapd_tool.engine import reset_absent, resolve_unknown, run_job
from dapd_tool.model import creation_order, make_plan, node_payload, validate_template
from dapd_tool.storage import Store
from dapd_tool.catalog import group_id_from_text, locate_group, task_id_from_text


DEST = {"projectId": "p", "taskGroupId": "g", "projectName": "项目", "groupName": "任务组", "parentTaskId": "container", "parentTitle": "总单"}
TREE = [{"title": "美术", "parent": None}, {"title": "特效", "parent": 0}, {"title": "技能特效", "parent": 1}, {"title": "程序", "parent": None}]


class DesktopEngineTests(unittest.TestCase):
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

    def test_empty_library_and_user_templates_survive_restart(self):
        self.assertEqual(self.store.templates(), [])
        tid = self.store.save_template("测试模板", TREE)
        self.assertEqual(Store(self.temp.name).templates()[0]["nodes"], TREE)
        self.store.save_template("新名称", TREE[:1], tid)
        self.assertEqual(len(self.store.templates()), 1)
        self.store.delete_template(tid)
        self.assertEqual(self.store.templates(), [])

    def test_template_cycles_invalid_parent_and_blank_titles_rejected(self):
        for nodes in [[{"title": "a", "parent": 0}], [{"title": "a", "parent": -1}], [{"title": "a", "parent": True}], [{"title": " ", "parent": None}]]:
            with self.assertRaises(ValueError):
                validate_template(nodes)

    def test_duplicate_roots_and_missing_destination_rejected(self):
        for titles, dest in [(["a", "a"], DEST), (["a"], {}), ([], DEST)]:
            with self.assertRaises(ValueError):
                make_plan(titles, TREE, dest)

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

    def test_deep_template_does_not_depend_on_python_recursion(self):
        tree = [{"title": str(index), "parent": index - 1 if index else None} for index in range(1100)]
        plan = make_plan(["主任务"], tree, DEST)
        self.assertEqual(list(creation_order(plan)), list(range(1101)))

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

    def test_plan_is_snapshot_not_live_template(self):
        template_id = self.store.save_template("t", TREE)
        identifier = self.add()
        self.store.save_template("t", [], template_id)
        self.assertEqual(len(self.store.job(identifier)["plan"]["nodes"]), 10)

    def test_encrypted_key_roundtrip_does_not_store_plaintext(self):
        key = "dapd_" + "b" * 64
        self.store.save_key(key)
        self.assertEqual(self.store.load_key(), key)
        self.assertNotIn(key.encode(), (Path(self.temp.name) / "credential.bin").read_bytes())

    def test_actual_http_adapter_end_to_end(self):
        def handler(request):
            name = request.url.path.split("/")[-1]
            data = json.loads(request.content) if request.method == "POST" else json.loads(request.url.params["input"])
            if name == "project.getProjects":
                value = [{"id": "p", "name": "项目"}]
            elif name == "taskGroup.getTaskGroups":
                value = [{"id": "g", "name": "任务组", "status": "in_progress"}]
            elif name == "task.getTaskById":
                value = dict(DEST, id="container", title="总单") if data["id"] == "container" else self.tasks[data["id"]]
            elif name == "task.createTask":
                value = self.create(data)
            else:
                self.fail(name)
            return httpx.Response(200, json={"result": {"data": value}})
        api = DapdClient("test", transport=httpx.MockTransport(handler))
        self.addCleanup(api.close)
        job = run_job(self.store, api, self.add(), threading.Event())
        self.assertEqual(job["status"], "completed")
        self.assertEqual(len(self.tasks), 10)

    def test_copied_group_link_with_chinese_name_and_query(self):
        text = "示例版本（测试）（ https://dapd.dodjoy.com/groups/11111111-2222-4333-8444-555555555555?only=true ）"
        self.assertEqual(group_id_from_text(text), "11111111-2222-4333-8444-555555555555")
        for invalid in ["https://example.com/groups/11111111-2222-4333-8444-555555555555", "示例版本", text + " https://dapd.dodjoy.com/groups/11111111-2222-4333-8444-555555555556"]:
            with self.assertRaises(ValueError):
                group_id_from_text(invalid)

    def test_group_link_resolves_project_by_id_not_name(self):
        self.api.projects.return_value = [{"id":"p1","name":"同名项目"}, {"id":"p2","name":"同名项目"}]
        self.api.groups.side_effect = lambda p: [{"id":"g1" if p=="p1" else "g2", "name":"同名任务组"}]
        result = locate_group(self.api, "g2")
        self.assertEqual(result["project"]["id"], "p2")
        self.assertEqual(result["group"]["id"], "g2")
        with self.assertRaises(ValueError):
            locate_group(self.api, "missing")

    def test_copied_parent_link_or_id_or_search_term(self):
        identifier = "22222222-3333-4444-8555-666666666666"
        text = f"DAPD任务：【示例】主任务（ https://dapd.dodjoy.com/task/{identifier} ）"
        self.assertEqual(task_id_from_text(text), identifier)
        self.assertEqual(task_id_from_text(identifier), identifier)
        self.assertIsNone(task_id_from_text("【示例】主任务"))
        with self.assertRaises(ValueError):
            task_id_from_text("https://other.example/task/" + identifier)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from dapd_tool.ui import MainWindow, TemplateDialog, PreviewDialog, configure_app


class DesktopUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        configure_app(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.window = MainWindow(self.store)
        self.addCleanup(self.window.close)

    def test_fresh_ui_no_templates_and_submission_disabled(self):
        self.assertEqual(self.window.template_list.count(), 0)
        self.assertIsNone(self.window.template_combo.currentData())
        self.assertFalse(self.window.preview_button.isEnabled())
        self.assertEqual(self.window.history.topLevelItemCount(), 0)

    def test_destination_change_clears_parent(self):
        self.window.parent_task = {"id": "old", "title": "旧父任务"}
        self.window.group.addItem("测试任务组", {"id": "g", "name": "测试任务组"})
        self.window.group.setCurrentIndex(1)
        self.assertIsNone(self.window.parent_task)

    def test_template_tree_edit_reparent_and_persist(self):
        dialog = TemplateDialog(self.store)
        dialog.name.setText("自建模板")
        first = dialog.new_item("美术", dialog.root)
        second = dialog.new_item("特效", dialog.root)
        dialog.tree.setCurrentItem(second)
        dialog.indent()
        self.assertEqual(dialog.nodes(), TREE[:2])
        dialog.outdent()
        self.assertEqual(dialog.nodes()[1]["parent"], None)
        dialog.indent()
        dialog.save()
        self.window.refresh_templates(dialog.saved_id)
        self.assertEqual(self.window.template_combo.currentData()["name"], "自建模板")
        self.assertEqual(self.window.template_tree.topLevelItem(0).child(0).child(0).text(0), "特效")

    def test_no_tooltip_events(self):
        self.assertTrue(self.app.no_tooltips.eventFilter(self.window, QEvent(QEvent.Type.ToolTip)))
        self.assertFalse(self.app.no_tooltips.eventFilter(self.window, QEvent(QEvent.Type.Enter)))


if __name__ == "__main__":
    unittest.main()
