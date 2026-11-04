import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
from dapd_tool.storage import Store
from dapd_tool.media import empty_content
from dapd_tool.model import make_plan, make_batch_plan, node_payload
from dapd_tool.engine import run_job


class BatchCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "data")

    def test_root_and_child_default_assignees_reach_payload(self):
        content = {**empty_content(), "assignee": {"id":"member", "name":"负责人"}}
        plan = make_plan(["主任务"], [{"title":"子任务", "parent":None, "content":content}], {"projectId":"p", "taskGroupId":"g"}, content)
        self.assertEqual(node_payload(plan, 0, {})["assigneeId"], "member")
        self.assertEqual(node_payload(plan, 1, {0:"root"})["assigneeId"], "member")

    def test_mixed_template_batch_preserves_each_hierarchy(self):
        a = {"root":empty_content(), "nodes":[{"title":"子一", "parent":None}]}
        b = {"root":empty_content(), "nodes":[{"title":"子二", "parent":None}, {"title":"孙任务", "parent":0}]}
        plan = make_batch_plan([("一",a), ("二",b)], {"projectId":"p", "taskGroupId":"g"})
        self.assertEqual([n["parent"] for n in plan["nodes"]], [None,0,None,2,3])
        self.assertEqual(a["nodes"][0]["parent"], None)

    def test_invalid_child_assignee_blocks_batch_before_first_write(self):
        content={**empty_content(),'assignee':{'id':'outsider','name':'外部成员'}}
        plan=make_plan(['主任务'],[{'title':'子任务','parent':None,'content':content}],{'projectId':'p','taskGroupId':'g'})
        identifier=self.store.add_job(plan)
        api=Mock();api.members.return_value=[]
        result=run_job(self.store,api,identifier,threading.Event())
        self.assertEqual(result['status'],'paused')
        api.create.assert_not_called()
