import tempfile
import unittest
from pathlib import Path
from PIL import Image
from dapd_tool.storage import Store
from dapd_tool.media import Assets, description_html, image_assets, description_assets
from dapd_tool.template_files import export_templates, import_templates


class TemplateFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "data")

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
