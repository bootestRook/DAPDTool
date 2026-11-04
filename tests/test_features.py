import copy
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
from PIL import Image
from dapd_tool.storage import Store
from dapd_tool.media import Assets, empty_content, description_html, image_assets, description_assets
from dapd_tool.model import make_plan, make_batch_plan, node_payload
from dapd_tool.template_files import export_templates, import_templates
from dapd_tool.tasks import list_created_tasks, save_task
from dapd_tool.engine import run_job


class FeatureTests(unittest.TestCase):
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

    def test_portable_rich_template_roundtrip_and_collision(self):
        source=Path(self.temp.name)/"image.png";Image.new("RGB",(12,12),"teal").save(source)
        asset=Assets(self.store.directory).import_file(source)
        content={"parts":[{"image":asset}], "attachments":[asset], "html":'<h2>标题</h2><img src="dapd-asset:'+asset['id']+'">', "assignee":{"id":"u","name":"成员"}}
        self.store.save_template("模板",[],root=content)
        output=Path(self.temp.name)/"transfer.dapd-template"
        export_templates(self.store,self.store.templates(),output)
        other=Store(Path(self.temp.name)/"other")
        import_templates(other,output);import_templates(other,output)
        saved=other.templates()
        self.assertEqual(len(saved),2)
        self.assertNotEqual(saved[0]['name'],saved[1]['name'])
        restored=saved[0]['root'];new_asset=next(iter(image_assets(restored).values()))
        self.assertIn('dapd-asset:'+new_asset['id'],restored['html'])
        self.assertEqual(restored['assignee'],content['assignee'])
        self.assertIn('https://example.com/image.png',description_html(restored,{new_asset['id']:'https://example.com/image.png'}))
        Assets(other.directory).path(new_asset,verify_hash=True)

    def test_previous_plain_template_remains_importable(self):
        self.store.save_template("旧模板",[{"title":"旧子任务","parent":None}],root={"parts":[{"text":"旧描述"}],"attachments":[]})
        output=Path(self.temp.name)/"old.dapd-template"
        export_templates(self.store,self.store.templates(),output)
        other=Store(Path(self.temp.name)/"new")
        import_templates(other,output)
        self.assertEqual(other.templates()[0]['root']['parts'],[{'text':'旧描述'}])

    def test_description_file_survives_portable_template_export_and_import(self):
        source = Path(self.temp.name) / "spec.txt"
        source.write_text("描述中的文件", encoding="utf-8")
        asset = Assets(self.store.directory).import_file(source)
        content = {"parts": [{"file": asset}], "attachments": [],
                   "html": '<a href="dapd-asset:' + asset["id"] + '">spec.txt</a>'}
        self.store.save_template("文件描述", [], root=content)
        output = Path(self.temp.name) / "files.dapd-template"
        export_templates(self.store, self.store.templates(), output)
        other = Store(Path(self.temp.name) / "other")
        import_templates(other, output)
        restored = other.templates()[0]["root"]
        imported = next(iter(description_assets(restored).values()))
        self.assertEqual(Assets(other.directory).path(imported).read_text(encoding="utf-8"), "描述中的文件")
        self.assertEqual(imported["sha256"], asset["sha256"])
        self.assertEqual(imported["mime"], asset["mime"])
        self.assertEqual(restored["html"], '<a href="dapd-asset:' + imported["id"] + '">spec.txt</a>')
        self.assertEqual(restored["attachments"], [])

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
        result=list_created_tasks(api)
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


os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from dapd_tool.content_editor import ContentEditor
from dapd_tool.ui import configure_app


class RichEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        configure_app(cls.app)

    def test_heading_alignment_font_size_and_image_survive_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            editor=ContentEditor(folder);editor.set_content(empty_content())
            editor.show();self.app.processEvents()
            editor.description.setPlainText('说明文字')
            editor.description.evaluate("editor.updateBlock(editor.document[0],{type:'heading',props:{level:2,textAlignment:'center'}})")
            editor.description.evaluate("editor.updateBlock(editor.document[0],{content:[{type:'text',text:'说明文字',styles:{fontSize:'24px',bold:true}}]})")
            source=Path(folder)/'source.png';Image.new('RGB',(16,10),'teal').save(source)
            asset=Assets(folder).import_file(source)
            editor.description.insert_asset(asset)
            content=editor.content()
            self.assertIn('24px',content['html'])
            self.assertIn('center',content['html'])
            self.assertIn('dapd-asset:',content['html'])
            editor.set_content(content)
            actual=editor.description.evaluate("JSON.stringify(editor.document)")
            self.assertIn('inlineImage',actual)
            self.assertIn('heading',actual)
            self.assertNotIn('file://',actual)
            self.assertEqual(editor.content(),content)
            editor.close()

    def test_block_types_include_screenshot_options(self):
        with tempfile.TemporaryDirectory() as folder:
            editor=ContentEditor(folder);editor.set_content(empty_content())
            types=json.loads(editor.description.evaluate("JSON.stringify(Object.keys(editor.schema.blockSchema))"))
            for kind in ['heading','bulletListItem','numberedListItem','checkListItem','codeBlock','quote','toggleListItem']:
                self.assertIn(kind,types)
            editor.close()

    def test_pasted_image_is_copied_to_template_assets(self):
        import base64
        import time
        from PySide6.QtTest import QTest
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'clipboard.png';Image.new('RGB',(14,11),'teal').save(source)
            raw=base64.b64encode(source.read_bytes()).decode()
            editor=ContentEditor(folder);editor.set_content(empty_content())
            editor.show();self.app.processEvents()
            editor.description.evaluate("editor.focus()")
            deadline = time.monotonic() + 5
            while not editor.description.evaluate("Boolean(document.activeElement?.closest('.bn-editor'))"):
                self.assertLess(time.monotonic(), deadline, "编辑器未取得输入焦点")
                QTest.qWait(20)
            script="const dt=new DataTransfer();dt.setData('text/html','<p>粘贴图片</p><img src=\"data:image/png;base64,"+raw+"\">');document.querySelector('.bn-editor').dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));"
            editor.description.evaluate(script)
            deadline = time.monotonic() + 5
            while not editor.description.evaluate("window.getContent().pending === 0 && window.getContent().html.includes('data:image/')"):
                self.assertLess(time.monotonic(), deadline, "粘贴的图片未完成插入")
                QTest.qWait(20)
            content=editor.content()
            self.assertEqual(len(image_assets(content)),1)
            self.assertIn('dapd-asset:',content['html'])
            self.assertNotIn('data:image/',content['html'])
            editor.close()


if __name__=='__main__':unittest.main()
