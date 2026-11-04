"""Exercise the DAPD-style editor through its rendered controls and native bridge."""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dapd_tool.content_editor import ContentEditor
from dapd_tool.media import empty_content, description_assets
from dapd_tool.ui import configure_app


class DescriptionEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        configure_app(cls.app)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.widget = ContentEditor(self.temporary.name)
        self.widget.resize(960, 650)
        self.widget.show()
        self.widget.activateWindow()
        self.view = self.widget.description
        self.view.setFocus()
        self.widget.set_content(empty_content())
        QTest.qWait(80)

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.widget = self.view = None
        self.temporary.cleanup()

    def js(self, expression):
        return self.view.evaluate(expression)

    def open_menu(self):
        self.js("document.querySelector('.empty-add').click()")
        QTest.qWait(120)

    def choose(self, title):
        self.js("[...document.querySelectorAll('[role=option]')].find(e=>e.querySelector('.bn-mt-suggestion-menu-item-title')?.textContent==="
                + json.dumps(title) + ").click()")
        QTest.qWait(120)

    def wait_until(self, expression):
        for _ in range(40):
            if self.js(expression):
                return
            QTest.qWait(50)
        self.fail("Editor state did not settle: " + expression)

    def test_plus_opens_grouped_menu_and_inserts_heading(self):
        self.assertFalse(self.js("!!document.querySelector('.bn-formatting-toolbar')"))
        self.open_menu()
        groups = json.loads(self.js("JSON.stringify([...document.querySelectorAll('.bn-suggestion-menu-label')].map(e=>e.textContent))"))
        self.assertEqual(groups, ["基础", "媒体", "折叠", "其他"])
        self.assertEqual(self.js("document.querySelectorAll('[role=option]').length"), 23)
        self.assertEqual(self.js("document.querySelector('.bn-mt-suggestion-menu-item-title').textContent"), "文本")
        self.choose("二级标题")
        self.assertEqual(self.js("editor.document[0].type"), "heading")
        self.assertEqual(self.js("editor.document[0].props.level"), 2)

    def test_selected_text_has_floating_formatting_and_no_hover_text(self):
        self.view.setPlainText("1111\n1\n11")
        self.js("editor.focus()")
        QTest.qWait(40)
        QTest.keyClick(self.view.focusProxy(), Qt.Key_Home, Qt.ControlModifier)
        QTest.keyClick(self.view.focusProxy(), Qt.Key_End, Qt.ShiftModifier)
        QTest.qWait(120)
        self.assertEqual(self.js("window.getSelection().toString()"), "1111")
        self.assertEqual(self.js("document.querySelectorAll('.bn-formatting-toolbar').length"), 1)
        self.js("document.querySelector('.bn-formatting-toolbar button[aria-label=加粗]').click()")
        self.assertTrue(self.js("editor.getActiveStyles().bold"))
        self.assertEqual(self.js("document.querySelectorAll('[title], [role=tooltip]').length"), 0)
        self.js("editor.focus();editor.setTextCursorPosition(editor.document[1])")
        self.wait_until("![...document.querySelectorAll('.bn-formatting-toolbar')].some(e=>e.checkVisibility({checkOpacity:true}))")

    def test_file_panel_copies_file_and_preserves_block_on_reopen(self):
        self.open_menu()
        self.choose("文件")
        self.js("(()=>{const transfer=new DataTransfer();transfer.items.add(new File(['description attachment'],'spec.txt',{type:'text/plain'}));"
                "const input=document.querySelector('input[type=file]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()")
        QTest.qWait(200)
        content = self.widget.content()
        self.assertEqual(len(description_assets(content)), 1)
        asset = next(iter(description_assets(content).values()))
        self.assertEqual(asset["mime"], "text/plain")
        self.assertIn("dapd-asset:" + asset["id"], content["html"])
        self.assertNotIn("file:///", content["html"])
        self.assertEqual(self.widget.assets.path(asset).read_text(), "description attachment")
        self.widget.set_content(content)
        self.assertEqual(self.js("editor.document[0].type"), "file")
        self.assertTrue(self.js("!!editor.document[0].props.url"))
        self.assertEqual(self.widget.content(), content)

    def test_media_row_layout_moves_images_and_survives_reopen(self):
        source = Path(self.temporary.name) / "source.png"
        Image.new("RGB", (120, 80), "teal").save(source)
        asset = self.widget.assets.import_file(source)
        url = self.view.register_asset(asset)
        self.js("editor.replaceBlocks(editor.document," + json.dumps([
            {"type": "image", "props": {"url": url, "previewWidth": 120}},
            {"type": "image", "props": {"url": url, "previewWidth": 120}},
        ]) + ")")
        self.js("document.querySelector('[role=switch]').click()")
        QTest.qWait(120)
        positions = json.loads(self.js("JSON.stringify([...document.querySelectorAll('.bn-editor [data-content-type=image]')].map(e=>({x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y})))"))
        self.assertEqual(positions[0]["y"], positions[1]["y"])
        self.assertGreater(positions[1]["x"], positions[0]["x"])
        content = self.widget.content()
        self.assertIn('data-media-layout="row"', content["html"])
        self.widget.set_content(content)
        QTest.qWait(40)
        self.assertTrue(self.js("document.querySelector('[role=switch]').checked"))
        self.assertEqual(self.widget.content(), content)
        self.widget.set_content(empty_content())
        QTest.qWait(40)
        self.assertFalse(self.js("document.querySelector('[role=switch]').checked"))

    def test_collapse_preserves_content_and_readonly_hides_edit_controls(self):
        self.view.setPlainText("保留这段描述")
        before = self.widget.content()
        self.js("document.querySelector('.description-toggle').click()")
        QTest.qWait(40)
        self.assertTrue(self.js("document.querySelector('#description-content').hidden"))
        self.assertEqual(self.view.maximumHeight(), 48)
        self.assertEqual(self.widget.content(), before)
        self.view.readonly = True
        self.widget.set_content(before)
        QTest.qWait(40)
        self.assertGreater(self.view.maximumHeight(), 200)
        self.assertFalse(self.js("editor.isEditable"))
        self.assertFalse(self.js("!!document.querySelector('.empty-add, [role=switch], .bn-formatting-toolbar')"))


if __name__ == "__main__":
    unittest.main()
