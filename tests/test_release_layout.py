import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import build_desktop
import publish_release


class ReleaseLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.release = self.root / "release"
        self.release.mkdir()
        self.package = self.root / "build-desktop" / "package"
        self.package.mkdir(parents=True)
        self.name = "DAPD任务工具-2.3.4-Windows-x64"

    def test_package_keeps_only_matching_latest_zip_and_unpacked_folder(self):
        (self.release / "old.zip").write_bytes(b"old")
        (self.release / "Releases").mkdir()
        (self.release / "Releases" / "old.exe").write_bytes(b"old")
        (self.release / self.name).mkdir()
        (self.release / self.name / "stale.txt").write_text("old", encoding="utf-8")
        (self.package / "current" / "_internal").mkdir(parents=True)
        (self.package / "DAPD任务工具.exe").write_bytes(b"portable launcher")
        (self.package / ".portable").write_bytes(b"")
        (self.package / "current" / "DAPD任务工具.exe").write_bytes(b"application")
        (self.package / "current" / "_internal" / "python313.dll").write_bytes(b"runtime")
        (self.package / "使用说明.md").write_text("新版说明", encoding="utf-8")
        staging_directory_id = self.package.stat().st_ino
        staging_executable_id = (self.package / "DAPD任务工具.exe").stat().st_ino

        unpacked, bundle = build_desktop.package_release(self.package, self.release, self.name)

        self.assertEqual({p.name for p in self.release.iterdir()}, {self.name, self.name + ".zip"})
        files = {p.relative_to(unpacked).as_posix(): p.read_bytes() for p in unpacked.rglob("*") if p.is_file()}
        with zipfile.ZipFile(bundle) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual({name: archive.read(name) for name in archive.namelist()}, files)
        self.assertNotIn("stale.txt", files)
        self.assertIn("DAPD任务工具.exe", files)
        self.assertFalse(any("Setup.exe" in name for name in files))
        self.assertFalse(self.package.exists())
        self.assertNotEqual(unpacked.stat().st_ino, staging_directory_id)
        self.assertNotEqual((unpacked / "DAPD任务工具.exe").stat().st_ino, staging_executable_id)

    def test_failed_zip_does_not_remove_previous_release(self):
        old = self.release / "previous.zip"
        old.write_bytes(b"keep previous package")
        with patch.object(build_desktop.zipfile, "ZipFile", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                build_desktop.package_release(self.package, self.release, self.name)
        self.assertEqual(old.read_bytes(), b"keep previous package")
        self.assertEqual(list(self.release.iterdir()), [old])

    def test_cleanup_rejects_path_outside_output(self):
        outside = self.root / "keep.txt"
        outside.write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError):
            build_desktop.remove_output(outside, self.release)
        self.assertTrue(outside.is_file())

    def test_publisher_reads_update_artifacts_from_build_and_publishes_portable_zip(self):
        package = self.release / self.name
        package.mkdir()
        artifacts = self.root / "build-desktop" / "Releases"
        artifacts.mkdir(parents=True)
        installer = artifacts / "DAPDTool.Desktop-win-Setup.exe"
        installer.write_bytes(b"installer")
        update = artifacts / "DAPDTool.Desktop-2.3.4-full.nupkg"
        update.write_bytes(b"update")
        feed = {"Assets": [{"Version": "2.3.4", "FileName": update.name, "Size": update.stat().st_size,
                            "SHA256": hashlib.sha256(update.read_bytes()).hexdigest()}]}
        (artifacts / "releases.win.json").write_text(json.dumps(feed), encoding="utf-8")
        (package / "build-info.json").write_text("{}", encoding="utf-8")
        (package / "SHA256.txt").write_text("checksums", encoding="utf-8")
        bundle = package.parent / (package.name + ".zip")
        bundle.write_bytes(b"portable zip")
        (self.root / "RELEASE-NOTES.md").write_text("notes", encoding="utf-8")
        with patch.object(publish_release, "ROOT", self.root), patch.object(publish_release, "VERSION", "2.3.4"), \
                patch.object(publish_release, "publish") as publish, patch("sys.argv", ["publish_release.py", "app"]):
            publish_release.main()
        paths = publish.call_args.args[3]
        self.assertIn(installer, paths)
        self.assertIn(update, paths)
        self.assertIn(package / "build-info.json", paths)
        self.assertIn(package / "SHA256.txt", paths)
        self.assertIn(bundle, paths)


if __name__ == "__main__":
    unittest.main()
