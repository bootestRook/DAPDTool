import tempfile
import threading
from unittest.mock import Mock, patch

from PySide6.QtCore import QTimer
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QDialog, QWidget

from dapd_tool.storage import Store
from dapd_tool.ui.activity import ActivityState
from dapd_tool.ui.pages.updates import UpdatesPage
from dapd_tool.ui.runner import Runner
from qt_fixture import QtCase


class UpdatePageTests(QtCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.owner = QWidget()
        self.addCleanup(self.owner.deleteLater)
        self.activity = ActivityState(self.owner)
        self.page = UpdatesPage(Store(self.temp.name), self.activity, self.owner)
        self.page.updater = Mock(ready=True, installed=True, current_version="1.0.0")
        self.page.refresh_actions()

    def test_install_waits_for_every_runner_then_emits_restart(self):
        first, second = Runner(self.owner, self.activity), Runner(self.owner, self.activity)
        gates = [threading.Event(), threading.Event()]
        self.addCleanup(lambda: [gate.set() for gate in gates])
        for runner, gate in zip((first, second), gates):
            runner.start(lambda _, gate=gate: gate.wait(3), lambda _: None, self.fail)
        self.assertFalse(self.page.program_action.isEnabled())
        self.page.program_clicked()
        self.page.updater.launch_update.assert_not_called()
        gates[0].set()
        from PySide6.QtTest import QTest
        while first.busy:
            QTest.qWait(10)
        self.assertTrue(self.activity.busy)
        self.assertFalse(self.page.program_action.isEnabled())
        gates[1].set()
        self.wait_idle(self.activity)
        self.assertTrue(self.page.program_action.isEnabled())
        restart = Mock()
        self.page.restartRequested.connect(restart)
        with patch("dapd_tool.ui.pages.updates.RestartUpdateDialog") as dialog:
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            self.page.program_clicked()
        self.page.updater.launch_update.assert_called_once()
        restart.assert_called_once()

    def test_operation_started_while_prompt_closes_prevents_install(self):
        runner = Runner(self.owner, self.activity)
        gate = threading.Event()
        self.addCleanup(gate.set)

        def accept():
            runner.start(lambda _: gate.wait(3), lambda _: None, self.fail)
            return QDialog.DialogCode.Accepted

        with patch("dapd_tool.ui.pages.updates.RestartUpdateDialog") as dialog:
            dialog.return_value.exec.side_effect = accept
            self.page.program_clicked()
        self.page.updater.launch_update.assert_not_called()
        gate.set()
        self.wait_idle(self.activity)

    def test_program_download_opens_countdown_and_restarts_after_worker_finishes(self):
        self.page.updater.ready = None
        self.page.available["program"] = {"version": "1.1.0"}
        self.page.updater.download.side_effect = lambda *_: setattr(self.page.updater, "ready", True)
        restart = QSignalSpy(self.page.restartRequested)
        from dapd_tool.ui.dialogs.restart_update import RestartUpdateDialog

        def prompt(activity, parent):
            dialog = RestartUpdateDialog(activity, parent)
            # Keep the real queued result/finished ordering, without a five-second test wait.
            QTimer.singleShot(0, lambda: dialog.timer.setInterval(10))
            return dialog

        with patch("dapd_tool.ui.pages.updates.RestartUpdateDialog", side_effect=prompt):
            self.page.program_clicked()
            self.wait_idle(self.activity)
        self.page.updater.download.assert_called_once()
        self.page.updater.launch_update.assert_called_once()
        self.assertEqual(restart.count(), 1)

    def test_postponed_restart_does_not_launch_installer(self):
        with patch("dapd_tool.ui.pages.updates.RestartUpdateDialog") as dialog:
            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            self.page.program_downloaded(None)
        self.page.updater.launch_update.assert_not_called()
        self.assertIn("稍后", self.page.status.text())

    def test_installer_failure_is_visible_and_does_not_request_close(self):
        self.page.updater.launch_update.side_effect = ValueError("无法启动更新")
        restart = QSignalSpy(self.page.restartRequested)
        with patch("dapd_tool.ui.pages.updates.RestartUpdateDialog") as dialog:
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            self.page.program_clicked()
        self.assertEqual(restart.count(), 0)
        self.assertIn("无法启动更新", self.page.status.text())

    def test_content_sync_shows_success_clears_indicator_and_never_restarts(self):
        self.page.updater.ready = None
        self.page.available["content"] = {"version": "1.0.0"}
        indicator = QSignalSpy(self.page.availableChanged)
        changed = QSignalSpy(self.page.templatesChanged)
        with patch("dapd_tool.ui.pages.updates.ReleaseClient"):
            with patch("dapd_tool.ui.pages.updates.install_pack", return_value={"version": "1.0.0", "templates": 2, "files": 3}):
                with patch("dapd_tool.ui.pages.updates.load_shared", return_value={"version": "1.0.0"}):
                    with patch("dapd_tool.ui.pages.updates.message") as success:
                        self.page.sync_content()
                        self.wait_idle(self.activity)
        self.assertEqual(changed.count(), 1)
        success.assert_called_once()
        self.assertIn("无需重启", success.call_args.args[1])
        self.assertFalse(indicator.at(indicator.count() - 1)[0])
        self.page.updater.launch_update.assert_not_called()

    def test_failed_download_does_not_open_restart_prompt(self):
        self.page.updater.ready = None
        self.page.available["program"] = {"version": "1.1.0"}
        self.page.updater.download.side_effect = ValueError("程序校验失败")
        with patch("dapd_tool.ui.pages.updates.RestartUpdateDialog") as dialog:
            self.page.program_clicked()
            self.wait_idle(self.activity)
        dialog.assert_not_called()
        self.page.updater.launch_update.assert_not_called()
        self.assertIn("程序校验失败", self.page.status.text())

    def test_failed_content_sync_keeps_indicator_and_does_not_show_success(self):
        self.page.updater.ready = None
        self.page.available["content"] = {"version": "1.0.0"}
        indicator = QSignalSpy(self.page.availableChanged)
        with patch("dapd_tool.ui.pages.updates.ReleaseClient"):
            with patch("dapd_tool.ui.pages.updates.install_pack", side_effect=ValueError("内容校验失败")):
                with patch("dapd_tool.ui.pages.updates.message") as success:
                    self.page.sync_content()
                    self.wait_idle(self.activity)
        success.assert_not_called()
        self.assertTrue(indicator.at(indicator.count() - 1)[0])
        self.assertIn("内容校验失败", self.page.status.text())
