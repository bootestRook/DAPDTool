import tempfile
import unittest
from dapd_tool.storage import Store
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from dapd_tool.ui.main_window import MainWindow
from dapd_tool.ui.dialogs.template import TemplateDialog
from dapd_tool.ui.theme import configure_app
from creation_fixture import TREE

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
        self.assertEqual(self.window.templates_page.template_list.count(), 0)
        self.assertIsNone(self.window.create_page.template_combo.currentData())
        self.assertFalse(self.window.create_page.preview_button.isEnabled())
        self.assertEqual(self.window.history_page.history.topLevelItemCount(), 0)

    def test_destination_change_clears_parent(self):
        self.window.create_page.destination_picker.parent_task = {"id": "old", "title": "旧父任务"}
        self.window.create_page.destination_picker.group.addItem("测试任务组", {"id": "g", "name": "测试任务组"})
        self.window.create_page.destination_picker.group.setCurrentIndex(1)
        self.assertIsNone(self.window.create_page.destination_picker.parent_task)

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
        self.window.templates_page.refresh_templates(dialog.saved_id)
        self.assertEqual(self.window.create_page.template_combo.currentData()["name"], "自建模板")
        self.assertEqual(self.window.templates_page.template_tree.topLevelItem(0).child(0).child(0).text(0), "特效")

    def test_no_tooltip_events(self):
        self.assertTrue(self.app.no_tooltips.eventFilter(self.window, QEvent(QEvent.Type.ToolTip)))
        self.assertFalse(self.app.no_tooltips.eventFilter(self.window, QEvent(QEvent.Type.Enter)))
