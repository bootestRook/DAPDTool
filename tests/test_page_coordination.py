import tempfile
from unittest.mock import Mock, patch

from dapd_tool.storage import Store
from dapd_tool.ui.main_window import MainWindow
from qt_fixture import QtCase


class PageCoordinationTests(QtCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.window = MainWindow(self.store)
        self.addCleanup(self.window.close)
        self.session = self.window.session
        self.session.set_key("test")

    def test_shared_content_notification_refreshes_both_template_views(self):
        identifier = self.store.save_template("new template", [])
        self.window.updates.templatesChanged.emit()
        template_list = self.window.templates_page.template_list
        combo = self.window.create_page.template_combo
        self.assertEqual(template_list.count(), 1)
        self.assertEqual(combo.count(), 2)
        self.window.templates_page.refresh_templates(identifier)
        self.assertEqual(combo.currentData()["id"], identifier)
        self.window.create_page.manageTemplatesRequested.emit()
        self.assertIs(self.window.tabs.currentWidget(), self.window.templates_page)

    def test_update_indicator_tracks_program_and_content_versions(self):
        updates = self.window.updates
        updates.updater = Mock(ready=None, installed=True, current_version="1.0.0")
        updates.content_version = "1.0.0"
        updates.available = {"program": None, "content": {"version": "1.1.0"}}
        updates.refresh_actions()
        self.assertFalse(self.window.update_dot.isHidden())
        updates.content_version = "1.1.0"
        updates.refresh_actions()
        self.assertTrue(self.window.update_dot.isHidden())
        updates.updater.ready = True
        updates.refresh_actions()
        self.assertFalse(self.window.update_dot.isHidden())
        self.assertEqual(self.window.update_dot.toolTip(), "")
        updates.updater.ready = None
        updates.available = {"program": {"version": "1.1.0"}, "content": None}
        updates.refresh_actions()
        self.assertFalse(self.window.update_dot.isHidden())
        updates.updater.current_version = "1.1.0"
        updates.refresh_actions()
        self.assertTrue(self.window.update_dot.isHidden())

    def test_project_selection_sets_template_scope_and_clears_parent(self):
        project = {"id": "p", "name": "project"}
        self.session.set_projects([project])
        picker = self.window.create_page.destination_picker
        api = Mock()
        api.groups.return_value = [{"id": "g", "name": "group"}]
        with patch("dapd_tool.ui.destination.with_api", side_effect=lambda key, op: op(api)):
            picker.project.setCurrentIndex(1)
            self.wait_idle(self.window.activity)
        self.assertEqual(self.session.project, project)
        picker.group.setCurrentIndex(1)
        self.assertTrue(self.window.create_page.preview_button.isEnabled())
        picker.parent_task = {"id": "parent", "title": "parent"}
        picker.project.setCurrentIndex(0)
        self.assertIsNone(self.session.project)
        self.assertIsNone(picker.parent_task)
        self.assertFalse(self.window.create_page.preview_button.isEnabled())
        self.assertFalse(picker.parent_button.isEnabled())

    def test_account_change_clears_browser_cache_and_creation_scope(self):
        self.session.set_projects([{"id": "p", "name": "project"}])
        self.window.task_browser.cache["p"] = {"private": "previous account"}
        self.session.set_project({"id": "p"})
        self.session.set_key("second-account")
        self.assertEqual(self.window.task_browser.cache, {})
        self.assertIsNone(self.window.task_browser.data)
        self.assertEqual(self.window.task_browser.projects.count(), 0)
        self.assertIsNone(self.session.project)

    def test_preview_signal_starts_batch_and_navigates_to_history(self):
        project = {"id": "p", "name": "project"}
        self.session.set_projects([project])
        picker = self.window.create_page.destination_picker
        picker.project.blockSignals(True)
        picker.project.setCurrentIndex(1)
        picker.project.blockSignals(False)
        picker.set_groups([{"id": "g", "name": "group"}])
        picker.group.setCurrentIndex(1)
        self.window.create_page.single_title.setText("new task")
        api = Mock()
        api.validate_task.side_effect = lambda value: value
        api.create.side_effect = lambda value: {**value, "id": "created"}
        api.task.side_effect = lambda _: {**api.create.call_args.args[0], "id": "created"}
        with patch("dapd_tool.ui.pages.create.PreviewDialog") as preview:
            preview.return_value.exec.return_value = 1
            with patch("dapd_tool.ui.job_controller.with_api", side_effect=lambda key, op: op(api)):
                self.window.create_page.preview()
                self.wait_idle(self.window.activity)
        self.assertIs(self.window.tabs.currentWidget(), self.window.history_page)
        self.assertEqual(self.window.history_page.history.topLevelItemCount(), 1)
        self.assertEqual(self.window.progress.value(), 1)
        self.assertEqual(self.store.jobs()[0]["status"], "completed")
