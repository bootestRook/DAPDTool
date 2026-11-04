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
BUNDLE_NAME = f"{NAME}-{VERSION}-Windows-x64"
PACKAGE = BUILD / "package"
APPLICATION = BUILD / NAME
PACKAGES = BUILD / "Releases"
RUNTIME_PACKAGES = ["PySide6-Essentials", "PySide6-Addons", "shiboken6", "httpx", "httpcore", "anyio", "certifi", "idna", "h11", "pywin32", "typing_extensions", "Pillow", "velopack", "pypinyin"]


def remove_output(path, parent):
    """Remove only a direct build/release child, never a redirected path."""
    if path.parent.resolve() != parent.resolve() or path.resolve().parent != parent.resolve() or path.is_symlink() or path.is_junction():
        raise ValueError(f"Refusing to remove an output outside {parent}: {path}")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def package_release(package, release, name):
    """Finish the new package before replacing or pruning existing releases."""
    if Path(name).name != name or name in ("", ".", ".."):
        raise ValueError("Invalid release package name")
    release.mkdir(parents=True, exist_ok=True)
    bundle = package.parent / (name + ".zip")
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(package).as_posix())
    with zipfile.ZipFile(bundle) as archive:
        if archive.testzip() is not None:
            raise ValueError("Release ZIP verification failed")
    unpacked = release / name
    if unpacked.exists():
        remove_output(unpacked, release)
    # Fresh extraction inherits release permissions instead of carrying NTFS
    # integrity labels and ACLs from the build staging directory.
    unpacked.mkdir()
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(unpacked)
    remove_output(package, package.parent)
    bundle.replace(release / bundle.name)
    for path in release.iterdir():
        if path.name not in {name, name + ".zip"}:
            remove_output(path, release)
    return unpacked, release / bundle.name


def collect_sources(root):
    """Include nested UI packages and everything needed to run source checks/tests."""
    names = ("dapd_desktop.py", "dapd_api.py", "build_desktop.py", "build_editor.py",
             "publish_release.py", "requirements-desktop.txt", "README-DAPD.md", "README.md",
             "RELEASE-NOTES.md", "AGENTS.md")
    files = [root / name for name in names]
    for folder in ("dapd_tool", "tests", "scripts"):
        files.extend((root / folder).rglob("*.py"))
    files.extend((root / ".github" / "workflows").glob("*.yml"))
    files.extend((root / "licenses").glob("*.txt"))
    files.extend(root / "editor" / name for name in ("package.json", "package-lock.json", "vite.config.js", "index.html"))
    files.extend(path for path in (root / "editor" / "src").rglob("*") if path.is_file())
    files.extend(path for path in (root / "dapd_tool" / "editor_dist").rglob("*") if path.is_file())
    return sorted(set(files))


def main():
    if sys.platform != "win32":
        raise SystemExit("Build this application on Windows x64.")
    subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "check_structure.py")], cwd=ROOT, check=True)
    RELEASE.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    if PACKAGE.exists():
        remove_output(PACKAGE, BUILD)
    PACKAGE.mkdir()
    # Use the same native Qt stock icon in the window and the executable.
    from PySide6.QtWidgets import QApplication, QStyle
    app = QApplication([])
    icon = BUILD / "dapd.ico"
    if not app.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView).pixmap(64, 64).save(str(icon), "ICO"):
        raise RuntimeError("Unable to create the Windows application icon")
    command = [sys.executable, "-X", "utf8", "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed", "--noupx",
               "--name", NAME, "--icon", str(icon), "--distpath", str(BUILD), "--workpath", str(BUILD / "work"),
               "--specpath", str(BUILD), "--exclude-module", "openai", "--exclude-module", "dapd_chat",
               "--exclude-module", "dapd_templates", "--exclude-module", "feishu_link", "--exclude-module", "PyQt6",
               "--add-data", str(ROOT / "dapd_tool" / "editor_dist") + ";dapd_tool/editor_dist",
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
    shutil.copy2(ROOT / "README-DAPD.md", PACKAGE / "使用说明.md")

    licenses = PACKAGE / "licenses"
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
certifi, idna, h11, Pillow, pywin32, pypinyin and Velopack, and is bundled with PyInstaller.
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
    (PACKAGE / "THIRD-PARTY-NOTICES.md").write_text(notices, encoding="utf-8")
    shutil.copy2(ROOT / "licenses" / "editor-third-party.txt", licenses / "editor-third-party.txt")
    with zipfile.ZipFile(PACKAGE / "source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for source in collect_sources(ROOT):
            archive.write(source, str(source.relative_to(ROOT)))
    for filename in ("使用说明.md", "THIRD-PARTY-NOTICES.md", "source.zip"):
        shutil.copy2(PACKAGE / filename, APPLICATION / filename)
    shutil.copytree(licenses, APPLICATION / "licenses", dirs_exist_ok=True)
    vpk = ROOT / ".tools" / "vpk.exe"
    if not vpk.is_file():
        raise RuntimeError("Install vpk 1.2.161 into .tools before building")
    packages = PACKAGES
    if packages.exists():
        remove_output(packages, BUILD)
    subprocess.run([str(vpk), "pack", "--packId", "DAPDTool.Desktop", "--packTitle", NAME,
                    "--packVersion", VERSION, "--packDir", str(APPLICATION), "--mainExe", NAME + ".exe",
                    "--outputDir", str(packages), "--runtime", "win-x64", "--delta", "None",
                    "--icon", str(icon), "--releaseNotes", str(ROOT / "RELEASE-NOTES.md")], cwd=ROOT, check=True, env=build_env)
    bundled_files = [path for path in APPLICATION.rglob("*") if path.is_file()]
    artifacts = sorted(path for path in packages.iterdir() if path.is_file())
    with zipfile.ZipFile(packages / "DAPDTool.Desktop-win-Portable.zip") as portable:
        portable.extractall(PACKAGE)
    required = [PACKAGE / ".portable", PACKAGE / (NAME + ".exe"), PACKAGE / "Update.exe",
                PACKAGE / "current" / (NAME + ".exe"), PACKAGE / "current" / "_internal" / "python313.dll"]
    if not all(path.is_file() for path in required):
        raise RuntimeError("Portable package is missing its launcher or runtime")
    manifest.update({"packaging": "velopack-portable", "repository": "bootestRook/DAPDTool",
                     "application_bytes": sum(path.stat().st_size for path in bundled_files),
                     "artifacts": {path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in artifacts}})
    (PACKAGE / "build-info.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    checksum_files = sorted(path for path in PACKAGE.rglob("*") if path.is_file())
    (PACKAGE / "SHA256.txt").write_text("\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(PACKAGE).as_posix()}" for path in checksum_files) + "\n", encoding="utf-8")
    unpacked, bundle = package_release(PACKAGE, RELEASE, BUNDLE_NAME)
    print(json.dumps({"executable": str(unpacked / (NAME + ".exe")), "zip": str(bundle), "unpacked": str(unpacked), "ai_modules": len(forbidden), "default_templates": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
