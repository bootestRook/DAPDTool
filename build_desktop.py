"""Build and audit the self-contained Windows distribution from a clean venv."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from dapd_tool import VERSION


ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / "release"
BUILD = ROOT / "build-desktop"
NAME = "DAPD任务工具"
APPLICATION = RELEASE / NAME
RUNTIME_PACKAGES = ["PySide6-Essentials", "shiboken6", "httpx", "httpcore", "anyio", "certifi", "idna", "h11", "pywin32", "typing_extensions", "Pillow", "velopack"]


def main():
    if sys.platform != "win32":
        raise SystemExit("Build this application on Windows x64.")
    RELEASE.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    # Use the same native Qt stock icon in the window and the executable.
    from PySide6.QtWidgets import QApplication, QStyle
    app = QApplication([])
    icon = BUILD / "dapd.ico"
    if not app.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView).pixmap(64, 64).save(str(icon), "ICO"):
        raise RuntimeError("Unable to create the Windows application icon")
    command = [sys.executable, "-X", "utf8", "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed", "--noupx",
               "--name", NAME, "--icon", str(icon), "--distpath", str(RELEASE), "--workpath", str(BUILD / "work"),
               "--specpath", str(BUILD), "--exclude-module", "openai", "--exclude-module", "dapd_chat",
               "--exclude-module", "dapd_templates", "--exclude-module", "feishu_link", "--exclude-module", "PyQt6",
               str(ROOT / "dapd_desktop.py")]
    # Developer tools can prepend unrelated ICU/UCRT DLLs to PATH. Keep binary
    # discovery restricted to the build interpreter, its venv, and Windows.
    build_env=os.environ.copy()
    build_env['PATH']=os.pathsep.join([str(Path(sys.prefix)/'Scripts'),sys.base_prefix,
                                     str(Path(os.environ['SystemRoot'])/'System32'),os.environ['SystemRoot']])
    subprocess.run(command, cwd=ROOT, check=True, env=build_env)
    exe = APPLICATION / (NAME + ".exe")
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(exe))
    pyz_name = next(name for name in archive.toc if name.endswith(".pyz"))
    modules = archive.open_embedded_archive(pyz_name).toc
    forbidden = [name for name in modules if name.split(".")[0] in {"openai", "feishu_link", "dapd_chat", "dapd_templates", "group_chat", "desktop_client"}]
    if forbidden:
        raise RuntimeError("Unexpected messaging or AI modules in build: " + repr(forbidden))
    bundled_files = [path for path in APPLICATION.rglob("*") if path.is_file()]
    forbidden_data = [str(path) for path in bundled_files if any(value in str(path).lower() for value in ("credential.bin", ".sqlite3", ".feishu-link", "core-batch"))]
    if forbidden_data:
        raise RuntimeError("Unexpected user data in executable")
    versions = {name: importlib.metadata.version(name) for name in RUNTIME_PACKAGES}
    if not (APPLICATION / "_internal" / "python313.dll").is_file():
        raise RuntimeError("The portable application must include its runtime alongside the executable")
    manifest = {"name": NAME, "version": VERSION, "python": sys.version.split()[0], "architecture": "Windows x64",
                "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(), "bytes": exe.stat().st_size,
                "dependencies": versions, "default_templates": 0, "credentials_bundled": False,
                "ai_modules_bundled": False, "signature": "unsigned", "packaging": "onedir",
                "startup_extraction": False, "application_bytes": sum(path.stat().st_size for path in bundled_files)}
    shutil.copy2(ROOT / "README-DAPD.md", RELEASE / "使用说明.md")

    licenses = RELEASE / "licenses"
    licenses.mkdir(exist_ok=True)
    for package in RUNTIME_PACKAGES + ["PyInstaller"]:
        distribution = importlib.metadata.distribution(package)
        for entry in distribution.files or []:
            if ".dist-info/" in str(entry) and any(s in str(entry).lower() for s in ("license", "copying", "notice")):
                source = Path(distribution.locate_file(entry))
                if source.is_file():
                    shutil.copy2(source, licenses / (package + "-" + source.name))
    for filename in ("LICENSE.txt", "LICENSE"):
        source = Path(sys.base_prefix) / filename
        if source.exists():
            shutil.copy2(source, licenses / "Python-LICENSE.txt")
            break
    for license_id in ("LGPL-3.0-only", "GPL-3.0-only", "Velopack-LICENSE"):
        shutil.copy2(ROOT / "licenses" / (license_id + ".txt"), licenses / (license_id + ".txt"))
    notices = """# Third-party notices

This application includes Python, PySide6 / Qt, Shiboken, httpx, httpcore, anyio,
certifi, idna, h11, Pillow, pywin32 and Velopack, and is bundled with PyInstaller.
Component copyright and license notices are in the licenses directory.

Qt / PySide6 / Shiboken 6.11.0 are distributed under their open-source LGPLv3 option.
The complete application build source is in source.zip. You may rebuild with a
modified compatible Qt / PySide6 distribution using the included requirements
and build script. No restriction is imposed on modification or reverse engineering
needed to debug modifications to these LGPL components.

Qt source: https://download.qt.io/official_releases/qt/6.11/6.11.0/submodules/
Qt for Python source: https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.11.0
Qt copyright and third-party component notices: https://doc.qt.io/qt-6/licenses-used-in-qt.html
Python source and license: https://www.python.org/downloads/source/
PyInstaller bootloader exception: https://pyinstaller.org/en/stable/license.html
Velopack source and MIT license: https://github.com/velopack/velopack/tree/1.2.161
Package versions are recorded in build-info.json.
"""
    (RELEASE / "THIRD-PARTY-NOTICES.md").write_text(notices, encoding="utf-8")
    source_files = [ROOT / name for name in ("dapd_desktop.py", "dapd_api.py", "build_desktop.py", "publish_release.py", "requirements-desktop.txt", "README-DAPD.md", "README.md", "RELEASE-NOTES.md")]
    source_files += list((ROOT / "dapd_tool").glob("*.py"))
    source_files += list((ROOT / "tests").glob("test_*.py"))
    source_files += list((ROOT / ".github" / "workflows").glob("*.yml"))
    source_files += list((ROOT / "licenses").glob("*.txt"))
    with zipfile.ZipFile(RELEASE / "source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for source in source_files:
            archive.write(source, str(source.relative_to(ROOT)))
    for filename in ("使用说明.md", "THIRD-PARTY-NOTICES.md", "source.zip"):
        shutil.copy2(RELEASE / filename, APPLICATION / filename)
    shutil.copytree(licenses, APPLICATION / "licenses", dirs_exist_ok=True)
    vpk = ROOT / ".tools" / "vpk.exe"
    if not vpk.is_file():
        raise RuntimeError("Install vpk 1.2.161 into .tools before building")
    packages = RELEASE / "Releases"
    if packages.exists():
        assert packages.resolve().is_relative_to(RELEASE.resolve()) and packages.name == "Releases"
        shutil.rmtree(packages)
    subprocess.run([str(vpk), "pack", "--packId", "DAPDTool.Desktop", "--packTitle", NAME,
                    "--packVersion", VERSION, "--packDir", str(APPLICATION), "--mainExe", NAME + ".exe",
                    "--outputDir", str(packages), "--runtime", "win-x64", "--delta", "None",
                    "--icon", str(icon), "--releaseNotes", str(ROOT / "RELEASE-NOTES.md")], cwd=ROOT, check=True, env=build_env)
    bundled_files = [path for path in APPLICATION.rglob("*") if path.is_file()]
    artifacts = sorted(path for path in packages.iterdir() if path.is_file())
    manifest.update({"packaging": "velopack-onedir", "repository": "bootestRook/DAPDTool",
                     "application_bytes": sum(path.stat().st_size for path in bundled_files),
                     "artifacts": {path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in artifacts}})
    (RELEASE / "build-info.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    checksum_files = sorted([*bundled_files, *artifacts, RELEASE / "source.zip", RELEASE / "build-info.json"])
    (RELEASE / "SHA256.txt").write_text("\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(RELEASE).as_posix()}" for path in checksum_files) + "\n", encoding="utf-8")
    bundle = RELEASE / f"DAPD任务工具-{VERSION}-Windows-x64.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in [*packages.glob("*"), RELEASE / "使用说明.md", RELEASE / "build-info.json", RELEASE / "SHA256.txt", RELEASE / "THIRD-PARTY-NOTICES.md", RELEASE / "source.zip", *licenses.glob("*")]:
            archive.write(path, str(path.relative_to(RELEASE)))
    print(json.dumps({"installer": str(packages / "DAPDTool.Desktop-win-Setup.exe"), "zip": str(bundle), "ai_modules": len(forbidden), "default_templates": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
