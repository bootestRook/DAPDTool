import hashlib
import json
import os
import tempfile
import threading
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path

import httpx
from PIL import Image, PngImagePlugin

from dapd_api import DapdClient
from dapd_tool.catalog import project_id_from_text
from dapd_tool.engine import run_job, reset_absent_uploads
from dapd_tool.media import Assets, description_html
from dapd_tool.model import make_plan
from dapd_tool.storage import Store

DEST={"projectId":"p","taskGroupId":"g","projectName":"验收项目","groupName":"验收任务组"}


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.store=Store(self.root/'data')
        self.assets=Assets(self.store.directory)
        source=self.root/'image.png'
        info=PngImagePlugin.PngInfo();info.add_text('private','never upload metadata')
        Image.new('RGB',(24,12),'teal').save(source,pnginfo=info)
        self.source=source
        self.picture=self.assets.import_file(source,image_only=True)
        text=self.root/'spec.txt';text.write_text('测试附件',encoding='utf-8')
        self.file=self.assets.import_file(text)
        self.tasks={}
        self.files=[]
        self.upload_calls=0
        self.create_calls=0
        self.timeout_kind=None
        self.hide_attachment=False
        self.api=DapdClient('test-key',transport=httpx.MockTransport(self.handle))
        self.addCleanup(self.api.close)

    def handle(self,request):
        if request.url.path=='/api/files/upload':
            self.upload_calls+=1
            multipart=BytesParser(policy=policy.default).parsebytes(b'Content-Type: '+request.headers['content-type'].encode()+b'\r\nMIME-Version: 1.0\r\n\r\n'+request.content)
            fields={}
            for part in multipart.iter_parts():
                name=part.get_param('name',header='content-disposition')
                if name=='file':fields['name']=part.get_filename()
                else:fields[name]=part.get_payload(decode=True).decode()
            record={**fields,'id':f'file-{self.upload_calls}','url':'https://storage.example/'+fields['name']}
            self.files.append(record)
            if fields['source']=='attachment' and not self.hide_attachment:
                self.tasks[fields['taskId']]['attachments'].append(record)
            if self.timeout_kind==fields['source']:
                raise httpx.ReadTimeout('simulated lost response')
            return httpx.Response(200,json=record)
        name=request.url.path.split('/')[-1]
        data=json.loads(request.content) if request.method=='POST' else json.loads(request.url.params['input'])
        if name=='project.getProjects':value=[{'id':'p','name':'验收项目'}]
        elif name=='taskGroup.getTaskGroups':value=[{'id':'g','name':'验收任务组'}]
        elif name=='task.createTask':
            self.create_calls+=1
            value=dict(data,id=f'task-{self.create_calls}',attachments=[])
            self.tasks[value['id']]=value
        elif name=='task.getTaskById':value=self.tasks[data['id']]
        elif name=='file.getProjectFiles':value=self.files
        else:raise AssertionError(name)
        return httpx.Response(200,json={'result':{'data':value}})

    def content(self):
        return {'parts':[{'text':'固定描述 <测试>\n'}, {'image':self.picture}, {'text':'\n图片之后'}], 'attachments':[self.file]}

    def job(self,root=None,nodes=None):
        return self.store.add_job(make_plan(['批量甲','批量乙'],nodes or [],DEST,root if root is not None else self.content()))

    def run_job(self,identifier):
        return run_job(self.store,self.api,identifier,threading.Event())

    def test_image_copy_removes_metadata_preserves_source(self):
        before=hashlib.sha256(self.source.read_bytes()).hexdigest()
        with Image.open(self.assets.path(self.picture)) as image:
            self.assertNotIn('private',image.info)
            self.assertEqual(image.size,(24,12))
        self.assertEqual(before,hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertNotEqual(self.assets.path(self.picture),self.source)

    def test_wrong_extension_rejected_and_no_source_mutation(self):
        bad=self.root/'wrong.jpg';bad.write_bytes(self.source.read_bytes())
        with self.assertRaises(ValueError):self.assets.import_file(bad)
        self.assertEqual(bad.read_bytes(),self.source.read_bytes())

    def test_asset_checksum_blocks_changed_local_copy(self):
        path=self.assets.path(self.file)
        data=path.read_bytes();path.write_bytes(b'a'*len(data))
        with self.assertRaises(ValueError):self.assets.path(self.file,verify_hash=True)

    def test_description_html_escapes_text_and_uses_remote_images(self):
        html=description_html(self.content(),{self.picture['id']:'https://storage.example/p.png'})
        self.assertIn('&lt;测试&gt;',html)
        self.assertIn('<img src="https://storage.example/p.png"',html)
        self.assertNotIn(str(self.root),html)

    def test_description_file_uploads_before_creation_and_replaces_local_reference(self):
        content = {"parts": [{"file": self.file}], "attachments": [],
                   "html": '<a href="dapd-asset:' + self.file["id"] + '">spec.txt</a>'}
        job = self.run_job(self.job(root=content))
        self.assertEqual(job["status"], "completed")
        self.assertEqual(self.upload_calls, 2)
        for task in self.tasks.values():
            self.assertIn('href="https://storage.example/', task["description"])
            self.assertNotIn("dapd-asset:", task["description"])
            self.assertEqual(task["attachments"], [])

    def test_root_and_descendant_fixed_content_expand_independently(self):
        nodes=[{'title':'子任务','parent':None,'content':{'parts':[{'text':'子任务描述'}],'attachments':[]}}]
        job=self.run_job(self.job(nodes=nodes))
        self.assertEqual(job['status'],'completed')
        self.assertEqual((self.create_calls,self.upload_calls),(4,4))
        self.assertIn('<img',self.tasks['task-1']['description'])
        self.assertEqual(self.tasks['task-2']['description'],'<p>子任务描述</p>')
        self.assertEqual(self.tasks['task-2']['parentTaskId'],'task-1')
        self.assertEqual(len(self.tasks['task-1']['attachments']),1)
        self.assertEqual(len(self.tasks['task-2']['attachments']),0)
        self.run_job(job['id'])
        self.assertEqual((self.create_calls,self.upload_calls),(4,4))

    def test_image_timeout_blocks_create_then_reconciles_without_reupload(self):
        identifier=self.job()
        self.timeout_kind='description'
        job=self.run_job(identifier)
        self.assertEqual(job['status'],'blocked')
        self.assertEqual(self.create_calls,0)
        self.timeout_kind=None
        job=self.run_job(identifier)
        self.assertEqual(job['status'],'completed')
        self.assertEqual((self.create_calls,self.upload_calls),(2,4))

    def test_attachment_timeout_reconciles_without_recreating_task(self):
        identifier=self.job()
        self.timeout_kind='attachment'
        job=self.run_job(identifier)
        self.assertEqual(job['status'],'blocked')
        self.assertEqual(self.create_calls,1)
        self.timeout_kind=None
        job=self.run_job(identifier)
        self.assertEqual(job['status'],'completed')
        self.assertEqual((self.create_calls,self.upload_calls),(2,4))

    def test_unconfirmed_attachment_is_only_read_back_on_resume(self):
        identifier=self.job()
        self.hide_attachment=True
        job=self.run_job(identifier)
        self.assertEqual(job['status'],'paused')
        self.assertEqual(self.upload_calls,2)
        self.hide_attachment=False
        self.tasks['task-1']['attachments']=[self.files[1]]
        job=self.run_job(identifier)
        self.assertEqual(job['status'],'completed')
        self.assertEqual(self.upload_calls,4)

    def test_upload_unknown_cannot_silently_retry(self):
        identifier=self.job()
        self.timeout_kind='description'
        self.run_job(identifier)
        self.files=[]
        self.timeout_kind=None
        job=self.run_job(identifier)
        self.assertEqual(job['status'],'blocked')
        self.assertEqual(self.upload_calls,1)
        row = next(row for row in job['nodes'] if row['status'] == 'media_unknown')
        reset_absent_uploads(self.store,identifier,row['position'])
        self.assertEqual(self.run_job(identifier)['status'],'completed')

    def test_copied_project_link(self):
        text='DAPD项目：示例  project（ https://dapd.dodjoy.com/groups/?projectId=33333333-4444-4555-8666-777777777777 ）'
        self.assertEqual(project_id_from_text(text),'33333333-4444-4555-8666-777777777777')
        with self.assertRaises(ValueError):project_id_from_text('https://other.example/?projectId=xxx')


os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from dapd_tool.ui.dialogs.template import TemplateDialog
from dapd_tool.ui.theme import configure_app
from dapd_tool.ui.widgets.content_editor import ContentEditor


class ContentEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        configure_app(cls.app)

    def test_text_images_attachments_roundtrip_and_switch_nodes(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'data')
            source=Path(folder)/'image.png';Image.new('RGB',(30,20),'teal').save(source)
            asset=Assets(store.directory).import_file(source)
            content={'parts':[{'text':'\n第一段\n'},{'image':asset},{'text':'后文\n\n'}],'attachments':[asset]}
            editor=ContentEditor(store.directory)
            editor.set_content(content)
            self.assertEqual(editor.content(),content)
            template=store.save_template('固定内容',[{'title':'child','parent':None}],root=content)
            dialog=TemplateDialog(store,store.templates()[0])
            dialog.tree.setCurrentItem(dialog.root.child(0))
            dialog.editor.description.setPlainText('子任务固定描述')
            dialog.tree.setCurrentItem(dialog.root)
            self.assertEqual(dialog.editor.content(),content)
            dialog.save()
            saved=store.templates()[0]
            self.assertEqual(saved['root'],content)
            self.assertEqual(saved['nodes'][0]['content']['parts'],[{'text':'子任务固定描述'}])
            editor.close()

    def test_long_node_title_does_not_force_oversized_window(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder)
            store.save_template('长标题测试',[{'title':'很长的任务标题'*30,'parent':None}])
            dialog=TemplateDialog(store,store.templates()[0])
            dialog.tree.setCurrentItem(dialog.root.child(0))
            dialog.ensurePolished()
            self.assertLessEqual(dialog.minimumSizeHint().width(),1120)
            dialog.accept()


if __name__=='__main__':unittest.main()
