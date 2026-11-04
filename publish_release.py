"""Publisher-only CLI. Credentials stay on the publisher's machine or in GitHub Actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

import httpx

from dapd_tool import VERSION
from dapd_tool.content_packs import install_pack, validate_catalog
from dapd_tool.updates import API_URL, MAX_CONTENT_BYTES, REPOSITORY

ROOT = Path(__file__).resolve().parent


def credential():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    result = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                            text=True, capture_output=True, timeout=30,
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if not fields.get("password"):
        raise ValueError("请先登录本机 GitHub 凭据管理器，或在发布环境中设置 GH_TOKEN。不要把凭据放进程序包。")
    return fields["password"]


def publish(tag, title, notes, paths, *, latest):
    with httpx.Client(headers={"Authorization": "Bearer " + credential(), "Accept": "application/vnd.github+json",
                               "User-Agent": "DAPDTool-Publisher"}, timeout=180) as client:
        existing = client.get(API_URL + "/releases/tags/" + tag)
        if existing.status_code != 404:
            if existing.status_code == 200:
                raise ValueError("此版本已经存在，请递增版本号。不会覆盖已发布的文件。")
            raise ValueError(f"无法检查仓库访问权限（HTTP {existing.status_code}）。")
        response = client.post(API_URL + "/releases", json={"tag_name": tag, "name": title, "body": notes,
                                                             "draft": True, "make_latest": "false"})
        if response.status_code != 201:
            raise ValueError(f"创建发布草稿失败（HTTP {response.status_code}），请检查仓库写入权限。")
        release = response.json()
        try:
            for path in paths:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                with path.open("rb") as source:
                    uploaded = client.post(f"https://uploads.github.com/repos/{REPOSITORY}/releases/{release['id']}/assets",
                                           params={"name": path.name}, content=source,
                                           headers={"Content-Type": "application/octet-stream", "Content-Length": str(path.stat().st_size)})
                if uploaded.status_code != 201 or uploaded.json().get("digest") != "sha256:" + digest:
                    raise ValueError(f"上传或校验 {path.name} 失败，草稿保留，未向用户发布。")
                print("已上传并校验：" + path.name, flush=True)
            response = client.patch(API_URL + f"/releases/{release['id']}", json={"draft": False, "make_latest": "true" if latest else "false"})
            if response.status_code != 200:
                raise ValueError("文件已上传，发布草稿未成功转为正式版本，请在 GitHub 核对。")
            print(response.json()["html_url"])
        except Exception:
            print("发布未完成；请检查 GitHub Releases 中的草稿，再以新版本号重试。")
            raise


def main():
    parser = argparse.ArgumentParser(description="向 bootestRook/DAPDTool 发布程序或共享内容")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("app", help="发布 build_desktop.py 生成的当前程序版本")
    content = commands.add_parser("content", help="发布软件导出的共享内容 ZIP")
    content.add_argument("package", type=Path)
    args = parser.parse_args()
    if args.command == "app":
        folder = ROOT / "release" / "Releases"
        paths = sorted(p for p in folder.iterdir() if p.is_file() and (p.suffix in {".exe", ".nupkg", ".zip"} or p.name == "releases.win.json"))
        if not any(p.name.endswith("-Setup.exe") for p in paths) or not any(p.name.endswith("-full.nupkg") for p in paths):
            raise ValueError("缺少安装包或更新包，请先运行 build_desktop.py。")
        feed = json.loads((folder / "releases.win.json").read_text(encoding="utf-8-sig"))
        if any(asset["Version"] != VERSION for asset in feed["Assets"]):
            raise ValueError("发布目录中混有其他版本，请重新构建到空发布目录。")
        for asset in feed["Assets"]:
            filename = asset["FileName"]
            if Path(filename).name != filename:
                raise ValueError("程序更新清单文件名无效。")
            package = folder / filename
            if package.stat().st_size != asset["Size"] or hashlib.sha256(package.read_bytes()).hexdigest().lower() != asset["SHA256"].lower():
                raise ValueError("更新包与清单校验值不一致，请重新构建。")
        paths.extend(ROOT / "release" / name for name in ("build-info.json", "SHA256.txt"))
        publish("v" + VERSION, "DAPD 任务工具 " + VERSION, (ROOT / "RELEASE-NOTES.md").read_text(encoding="utf-8"), paths, latest=True)
    else:
        package = args.package.resolve()
        if not 0 < package.stat().st_size <= MAX_CONTENT_BYTES:
            raise ValueError("内容包大小无效。")
        with zipfile.ZipFile(package) as archive:
            if archive.getinfo("content.json").file_size > 4 * 1024 * 1024:
                raise ValueError("内容目录过大。")
            catalog = validate_catalog(json.loads(archive.read("content.json")))
        version = catalog["version"]
        if package.name != f"dapd-content-{version}.zip":
            raise ValueError(f"内容包必须命名为 dapd-content-{version}.zip。")
        cache = ROOT / "work" / "publish-validation"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as directory:
            install_pack(directory, package, version)
        publish("content-v" + version, "共享模板与素材 " + version, catalog["notes"], [package], latest=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(str(exc) if isinstance(exc, ValueError) else "发布失败，请检查网络和文件。凭据未写入日志。") from None
