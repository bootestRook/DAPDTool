import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from dapd_tool.instance import acquire_instance_lock


class InstanceTests(unittest.TestCase):
    def setUp(self):
        self.scope = "test-" + uuid.uuid4().hex
        patcher = patch("dapd_tool.instance.win32security.ConvertSidToStringSid", return_value=self.scope)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_only_one_handle_can_hold_the_instance_name(self):
        first = acquire_instance_lock()
        self.assertIsNotNone(first)
        try:
            self.assertIsNone(acquire_instance_lock())
        finally:
            first.Close()
        second = acquire_instance_lock()
        self.assertIsNotNone(second)
        second.Close()

    def test_process_death_releases_instance_without_a_stale_file(self):
        script = "import sys,time,win32security; win32security.ConvertSidToStringSid=lambda sid:sys.argv[1]; from dapd_tool.instance import acquire_instance_lock; handle=acquire_instance_lock(); print('ready' if handle is not None else 'busy',flush=True); time.sleep(30)"
        process = subprocess.Popen([sys.executable, "-c", script, self.scope], cwd=Path(__file__).resolve().parents[1],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertEqual(process.stdout.readline().strip(), "ready")
            self.assertIsNone(acquire_instance_lock())
        finally:
            process.terminate()
            process.communicate(timeout=10)
        handle = acquire_instance_lock()
        self.assertIsNotNone(handle)
        handle.Close()


if __name__ == "__main__":
    unittest.main()
