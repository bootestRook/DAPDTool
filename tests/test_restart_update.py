from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QDialog, QWidget

from dapd_tool.ui.activity import ActivityState
from dapd_tool.ui.dialogs.restart_update import RestartUpdateDialog
from qt_fixture import QtCase


class RestartUpdateTests(QtCase):
    def setUp(self):
        self.owner = QWidget()
        self.addCleanup(self.owner.deleteLater)
        self.activity = ActivityState(self.owner)
        self.dialog = RestartUpdateDialog(self.activity, self.owner)
        self.addCleanup(self.dialog.reject)

    def test_button_counts_from_five_then_accepts_once(self):
        accepted = QSignalSpy(self.dialog.accepted)
        self.dialog.show()
        self.assertIn("5 秒", self.dialog.restart_button.text())
        self.assertEqual(self.dialog.timer.interval(), 1000)
        self.assertEqual(self.dialog.timer.timerType(), Qt.TimerType.PreciseTimer)
        for count in (4, 3, 2, 1):
            self.dialog.tick()
            self.assertIn(f"{count} 秒", self.dialog.restart_button.text())
            self.assertEqual(accepted.count(), 0)
        self.dialog.tick()
        self.assertEqual(accepted.count(), 1)
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(self.dialog.timer.isActive())

    def test_manual_restart_and_postpone_both_stop_timer(self):
        self.dialog.show()
        self.dialog.restart_button.click()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(self.dialog.timer.isActive())
        self.dialog.show()
        self.dialog.later_button.click()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Rejected)
        self.assertFalse(self.dialog.timer.isActive())

    def test_busy_operations_pause_and_restart_full_countdown(self):
        accepted = QSignalSpy(self.dialog.accepted)
        self.dialog.show()
        self.dialog.tick()
        self.activity.set_busy("first", True)
        self.activity.set_busy("second", True)
        self.assertFalse(self.dialog.timer.isActive())
        self.assertFalse(self.dialog.restart_button.isEnabled())
        self.dialog.restart()
        self.assertEqual(accepted.count(), 0)
        self.activity.set_busy("first", False)
        self.assertFalse(self.dialog.timer.isActive())
        self.activity.set_busy("second", False)
        self.assertTrue(self.dialog.timer.isActive())
        self.assertEqual(self.dialog.remaining, 5)
        self.dialog.reject()
        self.activity.set_busy("third", True)
        self.activity.set_busy("third", False)
        self.assertFalse(self.dialog.timer.isActive())

    def test_real_timer_triggers_automatic_restart(self):
        accepted = QSignalSpy(self.dialog.accepted)
        self.dialog.show()
        self.dialog.timer.setInterval(10)
        self.assertTrue(accepted.wait(1000))
        QTest.qWait(30)
        self.assertEqual(accepted.count(), 1)
        self.assertFalse(self.dialog.timer.isActive())
