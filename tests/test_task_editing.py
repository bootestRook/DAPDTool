import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from dapd_tool.storage import Store
from dapd_tool.media import empty_content
from dapd_tool.tasks import list_created_tasks, save_task


class TaskEditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "data")

    def test_task_pagination_and_other_creator_ancestor(self):
        api=Mock()
        tasks=[{'id':str(i),'createdById':'me','parentTaskId':'ancestor' if i==0 else None,'projectId':'p','taskGroupId':'g'} for i in range(101)]
        def request(method,procedure,payload):
            if procedure=='userSetting.getSettings':return {'userId':'me'}
            if procedure=='user.getById':return {'id':'me','name':'我'}
            if procedure=='task.getTasks':return tasks[payload['offset']:payload['offset']+100]
            if procedure=='task.getTaskById':return {'id':'ancestor','parentTaskId':None,'createdById':'other','projectId':'p','taskGroupId':'g'}
            if procedure=='taskStatusConfig.listByProject':return []
            self.fail(procedure)
        api.request.side_effect=request;api.groups.return_value=[{'id':'g','name':'任务组'}]
        result=list_created_tasks(api, 'p')
        self.assertEqual(len(result['own_ids']),101)
        self.assertEqual(len(result['tasks']),102)
        self.assertTrue(result['tasks'][-1]['contextOnly'])

    def test_update_conflict_stops_before_post(self):
        api=Mock();original={'id':'t','createdById':'me','title':'原始','projectId':'p'}
        latest={**original,'title':'别人已改'}
        api.request.side_effect=lambda method,name,data: {'userId':'me'} if name=='userSetting.getSettings' else {'id':'me'} if name=='user.getById' else latest
        with self.assertRaisesRegex(ValueError,'已在 DAPD 中被修改'):
            save_task(self.store,api,original,{'title':'我的改动'},empty_content())
        self.assertFalse(any(call.args[0]=='POST' for call in api.request.call_args_list))

    def test_update_only_sends_changed_fields_and_reads_back(self):
        task={'id':'t','createdById':'me','title':'原始','projectId':'p'};api=Mock()
        def request(method,name,data):
            if name=='userSetting.getSettings':return {'userId':'me'}
            if name=='user.getById':return {'id':'me'}
            if name=='task.updateTask':task['title']=data['title'];return dict(task)
            return dict(task)
        api.request.side_effect=request
        result=save_task(self.store,api,dict(task),{'title':'新标题'},empty_content())
        self.assertEqual(result['title'],'新标题')
        posts=[call for call in api.request.call_args_list if call.args[0]=='POST']
        self.assertEqual(posts[0].args[2],{'id':'t','title':'新标题','updateSource':'manual'})
