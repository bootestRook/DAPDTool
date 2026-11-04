"""Ensure architectural rules reject real violations, including delayed imports."""
import tempfile
import unittest
from pathlib import Path

from scripts.check_structure import check


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put("dapd_tool/__init__.py", "")
        self.put("dapd_tool/ui/__init__.py", "")
        self.put("dapd_tool/ui/pages/__init__.py", "")
        self.put("dapd_tool/ui/widgets/__init__.py", "")

    def put(self, path, source):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")

    def test_file_limit_includes_untracked_sources_but_excludes_generated_assets(self):
        self.put("dapd_tool/large.py", "# source\n" * 501)
        self.put("editor/src/large.jsx", "// source\n" * 501)
        self.put("dapd_tool/editor_dist/generated.js", "// generated\n" * 800)
        errors, _ = check(self.root)
        self.assertEqual(len(errors), 2)
        self.assertTrue(all("500-line" in error for error in errors))

    def test_delayed_relative_import_cycle_is_rejected(self):
        self.put("dapd_tool/first.py", "def work():\n    from . import second\n")
        self.put("dapd_tool/second.py", "from .first import work\n")
        errors, _ = check(self.root)
        self.assertTrue(any("import cycle" in error for error in errors))

    def test_core_cannot_import_widgets_or_qt(self):
        self.put("dapd_tool/ui/widgets/example.py", "class Widget: pass\n")
        self.put("dapd_tool/service.py", "from .ui.widgets.example import Widget\nfrom PySide6 import QtCore\n")
        errors, _ = check(self.root)
        self.assertTrue(any("business modules" in error and "widgets" in error for error in errors))
        self.assertTrue(any("business modules" in error and "PySide6" in error for error in errors))

    def test_shared_ui_and_pages_cannot_import_composed_pages(self):
        self.put("dapd_tool/ui/pages/tasks.py", "class Tasks: pass\n")
        self.put("dapd_tool/ui/controls.py", "from .pages.tasks import Tasks\n")
        self.put("dapd_tool/ui/pages/templates.py", "from .tasks import Tasks\n")
        errors, _ = check(self.root)
        self.assertTrue(any("shared UI" in error for error in errors))
        self.assertTrue(any("signals" in error for error in errors))

    def test_obsolete_module_path_is_rejected(self):
        self.put("entry.py", "from dapd_tool.task_browser import TaskBrowser\n")
        errors, _ = check(self.root)
        self.assertTrue(any("missing local module" in error for error in errors))

    def test_valid_composition_and_business_imports_pass(self):
        self.put("dapd_tool/service.py", "def run(): pass\n")
        self.put("dapd_tool/ui/pages/tasks.py", "from ...service import run\n")
        self.put("dapd_tool/ui/main_window.py", "from .pages import tasks\n")
        errors, _ = check(self.root)
        self.assertEqual(errors, [])

    def test_responsibility_thresholds_are_review_not_exemptions(self):
        self.put("dapd_tool/service.py", "def work():\n" + "    pass\n" * 61 + "\n" * 240)
        errors, reviews = check(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(len(reviews), 2)
