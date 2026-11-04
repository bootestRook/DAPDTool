"""Build the bundled editor and collect the installed dependencies' license texts."""
import json
from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parent


def main():
    editor = ROOT / "editor"
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("Install Node.js 22 or newer before building the editor.")
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=editor, check=True)
    subprocess.run([npm, "run", "build"], cwd=editor, check=True)
    packages = json.loads((editor / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    notices = []
    for relative, metadata in packages.items():
        if not relative:
            continue
        directory = editor / relative
        if not directory.is_dir():
            continue  # npm omits optional dependencies for other operating systems.
        for path in directory.iterdir():
            if path.is_file() and path.name.lower().split(".")[0] in {"license", "licence", "copying", "notice"}:
                notices.append(f"\n{relative} {metadata.get('version', '')}\n" + path.read_text(encoding="utf-8", errors="replace"))
    (ROOT / "licenses" / "editor-third-party.txt").write_text("\n".join(notices), encoding="utf-8")


if __name__ == "__main__":
    main()
