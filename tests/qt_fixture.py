"""A Qt event-loop fixture for background-operation tests."""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dapd_tool.ui.theme import configure_app


class QtCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        configure_app(cls.app)

    def wait_idle(self, activity):
        deadline = time.monotonic() + 5
        while activity.busy:
            self.assertLess(time.monotonic(), deadline, "Background operation did not finish")
            QTest.qWait(10)
