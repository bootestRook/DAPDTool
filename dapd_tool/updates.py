"""Public release discovery and the Velopack installer boundary. No DAPD credentials."""
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import httpx

from . import VERSION

REPOSITORY = "bootestRook/DAPDTool"
REPO_URL = "https://github.com/" + REPOSITORY
API_URL = "https://api.github.com/repos/" + REPOSITORY
INDEX_URL = "https://raw.githubusercontent.com/" + REPOSITORY + "/main/updates.json"
MAX_CONTENT_BYTES = 1024 * 1024 * 1024


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})", value):
        raise ValueError("版本号请填写三段数字，例如 1.0.0。")
    return tuple(map(int, value.split(".")))


def choose_releases(releases):
    found = {"program": None, "content": None}
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name", "")
        kind, value = ("content", tag[9:]) if tag.startswith("content-v") else ("program", tag[1:]) if tag.startswith("v") else (None, "")
        if kind is None:
            continue
        try:
            version_tuple(value)
        except ValueError:
            continue
        expected = "releases.win.json" if kind == "program" else f"dapd-content-{value}.zip"
        matches = [a for a in release.get("assets", []) if a.get("name") == expected]
        if len(matches) != 1:
            continue
        asset = matches[0]
        base = REPO_URL + "/releases/download/" + tag
        if asset.get("browser_download_url") != base + "/" + expected:
            raise ValueError("更新文件地址与发布仓库不一致，请联系发布者。")
        record = {"version": value, "tag": tag, "notes": str(release.get("body") or "暂无更新说明。")[:20000],
                  "base_url": base, "asset": asset}
        if found[kind] is None or version_tuple(value) > version_tuple(found[kind]["version"]):
            found[kind] = record
    return found


def validate_index(value):
    if not isinstance(value, dict) or set(value) != {"schema", "releases"} or value["schema"] != 1:
        raise ValueError("更新索引格式不受支持，请联系发布者。")
    rows = value["releases"]
    if not isinstance(rows, list) or len(rows) > 2 or any(not isinstance(row, dict) for row in rows):
        raise ValueError("更新索引必须仅包含当前程序与共享内容版本。")
    found = choose_releases(rows)
    if sum(item is not None for item in found.values()) != len(rows):
        raise ValueError("更新索引包含重复或不完整的版本信息。")
    return found


class ReleaseClient:
    def __init__(self, transport=None):
        self.client = httpx.Client(timeout=30, transport=transport, follow_redirects=False,
                                   headers={"Accept": "application/json", "User-Agent": "DAPDTool/" + VERSION})

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.client.close()

    def releases(self):
        # Static public file: checking does not consume GitHub REST API quotas.
        response = self.client.get(INDEX_URL)
        if response.status_code == 404:
            raise ValueError("发布者尚未提供更新索引，请稍后重试。")
        response.raise_for_status()
        if len(response.content) > 1024 * 1024:
            raise ValueError("更新索引过大，已停止读取。")
        return validate_index(response.json())

    def download_content(self, release, destination, progress=lambda _: None):
        asset = release["asset"]
        size, digest = asset.get("size"), asset.get("digest", "")
        if type(size) is not int or not 0 < size <= MAX_CONTENT_BYTES or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest or ""):
            raise ValueError("内容包缺少有效的大小或 SHA256 校验信息，请重新发布。")
        url = REPO_URL + f"/releases/download/{release['tag']}/dapd-content-{release['version']}.zip"
        if asset.get("browser_download_url") != url:
            raise ValueError("内容包地址无效。")
        destination = Path(destination)
        hasher, received = hashlib.sha256(), 0
        try:
            # GitHub redirects assets to its authenticated release-assets CDN.
            for _ in range(5):
                with self.client.stream("GET", url) as response:
                    if response.is_redirect:
                        next_url = httpx.URL(response.headers["location"])
                        if next_url.scheme != "https" or next_url.host not in {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}:
                            raise ValueError("内容下载跳转到了不受支持的地址。")
                        url = str(next_url)
                        continue
                    response.raise_for_status()
                    with destination.open("wb") as output:
                        for chunk in response.iter_bytes(256 * 1024):
                            received += len(chunk)
                            if received > size:
                                raise ValueError("内容包大小与发布信息不一致。")
                            output.write(chunk)
                            hasher.update(chunk)
                            progress(int(received * 100 / size))
                    break
            else:
                raise ValueError("内容下载跳转次数过多。")
            if received != size or hasher.hexdigest() != digest[7:]:
                raise ValueError("内容包校验失败，请重新同步。")
        except Exception:
            destination.unlink(missing_ok=True)
            raise


class ProgramUpdater:
    def __init__(self):
        self.manager = None
        self.info = None
        self.ready = None
        self.current_version = VERSION
        self.installed = bool(getattr(sys, "frozen", False) and (Path(sys.executable).parent / "sq.version").is_file())
        if self.installed:
            self.manager = self._manager(REPO_URL + "/releases/latest/download")
            self.current_version = self.manager.get_current_version()
            self.ready = self.manager.get_update_pending_restart()

    @staticmethod
    def _manager(url):
        import velopack
        source = velopack.HttpSource(url, velopack.HttpOptions([], 300000))
        return velopack.UpdateManager(source)

    def prepare(self, release):
        if not self.installed:
            raise ValueError("请使用首次安装包安装软件后，再使用软件内更新。")
        self.manager = self._manager(release["base_url"])
        self.info = self.manager.check_for_updates()
        if self.info and self.info.TargetFullRelease.Version != release["version"]:
            raise ValueError("程序更新清单与版本号不一致，请联系发布者。")
        return self.info

    def download(self, release, progress):
        if not self.prepare(release):
            raise ValueError("没有可下载的更新，请重新检查版本。")
        self.manager.download_updates(self.info, progress)
        self.ready = self.info

    def launch_update(self):
        if not self.ready or not self.manager:
            raise ValueError("请先下载程序更新。")
        # The UI first verifies workers are idle; Qt shuts down cleanly and releases its lock.
        self.manager.wait_exit_then_apply_updates(self.ready, silent=False, restart=True)


def update_error(exc):
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return "连接 GitHub 失败，请检查网络后重试。现有版本仍可使用。"
    return "更新未完成，请检查网络和磁盘空间后重试。现有数据已保留。"


def auto_check_due(directory):
    path = Path(directory) / "last-update-check.json"
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
        return time.time() - float(previous["time"]) >= 86400
    except (OSError, ValueError, KeyError, TypeError):
        return True


def record_check(directory):
    (Path(directory) / "last-update-check.json").write_text(json.dumps({"time": time.time()}), encoding="utf-8")
