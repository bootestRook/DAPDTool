"""Versioned shared templates; immutable media and an atomic catalog activation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import zipfile

from PIL import Image

from . import VERSION
from .media import Assets, MIMES, validate_content, MAX_FILE
from .model import title_text, validate_template
from .updates import MAX_CONTENT_BYTES, version_tuple

CATALOG = "shared-content.json"
MAX_MANIFEST = 4 * 1024 * 1024


def all_assets(template):
    for content in [template["root"], *[n.get("content", {"parts": [], "attachments": []}) for n in template["nodes"]]]:
        for part in content["parts"]:
            if "image" in part:
                yield part["image"]
        yield from content["attachments"]


def validate_catalog(value, app_version=VERSION):
    if not isinstance(value, dict) or set(value) != {"schema", "version", "min_app_version", "notes", "templates"} or value["schema"] != 1:
        raise ValueError("内容包格式不受支持，请更新程序后重试。")
    version_tuple(value["version"])
    if version_tuple(value["min_app_version"]) > version_tuple(app_version):
        raise ValueError(f"此内容需要程序 {value['min_app_version']} 或更高版本，请先更新程序。")
    if not isinstance(value["notes"], str) or len(value["notes"]) > 20000:
        raise ValueError("内容更新说明无效。")
    if not isinstance(value["templates"], list) or len(value["templates"]) > 500:
        raise ValueError("一个内容包最多包含 500 个模板。")
    clean = {**value, "templates": []}
    ids, names = set(), set()
    for item in value["templates"]:
        if not isinstance(item, dict) or set(item) != {"id", "name", "nodes", "root"}:
            raise ValueError("共享模板字段不完整。")
        if not isinstance(item["id"], str) or not re.fullmatch(r"[a-f0-9-]{36}", item["id"]):
            raise ValueError("共享模板标识无效。")
        name = title_text(item["name"])
        if item["id"] in ids or name in names:
            raise ValueError("内容包中存在重复的模板。")
        ids.add(item["id"])
        names.add(name)
        template = {"id": item["id"], "name": name, "nodes": validate_template(item["nodes"]), "root": validate_content(item["root"])}
        for asset in all_assets(template):
            ext = Path(asset["file"]).suffix
            if not isinstance(asset["name"], str) or not 0 < len(asset["name"]) <= 255 or any(c in asset["name"] for c in "/\\\r\n\0"):
                raise ValueError("内容包文件名无效。")
            if (ext == ".png" and asset["mime"] == "image/png") or MIMES.get(ext) == asset["mime"]:
                continue
            raise ValueError("内容包包含不支持的文件类型。图片必须为已处理的 PNG。")
        clean["templates"].append(template)
    if sum(len(t["nodes"]) + 1 for t in clean["templates"]) > 10000:
        raise ValueError("内容包任务节点过多，请减少模板数量。")
    return clean


def load_shared(directory):
    path = Path(directory) / CATALOG
    if not path.exists():
        return {"version": None, "templates": [], "notes": "尚未同步共享内容。"}
    if path.stat().st_size > MAX_MANIFEST:
        raise ValueError("本地共享内容目录异常，请重新同步。")
    catalog = validate_catalog(json.loads(path.read_text(encoding="utf-8")))
    return {**catalog, "templates": [{**t, "id": "shared:" + t["id"], "shared": True, "content_version": catalog["version"]} for t in catalog["templates"]]}


def export_pack(directory, templates, version, notes, output):
    catalog = validate_catalog({"schema": 1, "version": version, "min_app_version": VERSION,
                                "notes": notes, "templates": copy.deepcopy(templates)})
    raw = json.dumps(catalog, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_MANIFEST:
        raise ValueError("内容目录过大，请减少模板内容。")
    assets = Assets(directory)
    files = {}
    for template in catalog["templates"]:
        for asset in all_assets(template):
            if asset["file"] in files and files[asset["file"]][0] != asset["sha256"]:
                raise ValueError("文件标识冲突，请重新添加该文件。")
            files[asset["file"]] = (asset["sha256"], assets.path(asset, verify_hash=True))
    if sum(path.stat().st_size for _, path in files.values()) > MAX_CONTENT_BYTES:
        raise ValueError("内容包总大小不能超过 1 GB。")
    output = Path(output)
    temporary = output.with_suffix(".partial")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("content.json", raw)
            for name, (_, path) in files.items():
                archive.write(path, "assets/" + name)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"file": str(output), "version": version, "templates": len(templates), "files": len(files),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def install_pack(directory, archive_path, expected_version, app_version=VERSION):
    directory = Path(directory)
    cache = directory / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="content-", dir=cache) as temporary:
        staging = Path(temporary)
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            names = [e.filename for e in entries]
            if len(entries) > 10001 or len(names) != len(set(names)) or "content.json" not in names:
                raise ValueError("内容包目录重复、过大或缺少说明文件。")
            if sum(e.file_size for e in entries) > MAX_CONTENT_BYTES + MAX_MANIFEST:
                raise ValueError("内容包解压大小超过限制。")
            for e in entries:
                if stat.S_ISLNK(e.external_attr >> 16) or e.flag_bits & 1 or e.file_size > (MAX_MANIFEST if e.filename == "content.json" else MAX_FILE):
                    raise ValueError("内容包包含不支持的文件。")
            catalog = validate_catalog(json.loads(archive.read("content.json")), app_version)
            if catalog["version"] != expected_version:
                raise ValueError("内容包内外版本号不一致。")
            try:
                previous = load_shared(directory)["version"]
            except (ValueError, KeyError, TypeError):
                # A verified download can repair a damaged local catalog.
                previous = None
            if previous and version_tuple(expected_version) <= version_tuple(previous):
                raise ValueError("内容版本没有增加，不会覆盖当前共享库。")
            assets = {}
            for template in catalog["templates"]:
                for asset in all_assets(template):
                    if asset["file"] in assets and asset != assets[asset["file"]]:
                        raise ValueError("内容包包含冲突的文件标识。")
                    assets[asset["file"]] = asset
            if set(names) != {"content.json", *["assets/" + name for name in assets]}:
                raise ValueError("内容包包含未声明文件或缺少模板素材。")
            remapped = {}
            for name, asset in assets.items():
                data = archive.read("assets/" + name)
                if len(data) != asset["size"] or hashlib.sha256(data).hexdigest() != asset["sha256"]:
                    raise ValueError("模板素材校验失败，当前共享库保持原版本。")
                identifier = asset["sha256"][:32]
                new_name = identifier + Path(name).suffix
                path = staging / new_name
                path.write_bytes(data)
                if asset["mime"] == "image/png":
                    with Image.open(path) as picture:
                        if picture.format != "PNG" or max(picture.size) > 4096 or getattr(picture, "n_frames", 1) != 1 or picture.info:
                            raise ValueError("内容包图片未按要求处理，请由发布者重新导出。")
                        picture.verify()
                remapped[name] = {**asset, "id": identifier, "file": new_name}
        library = Assets(directory)
        for asset in remapped.values():
            destination = library.directory / asset["file"]
            if destination.exists():
                if hashlib.sha256(destination.read_bytes()).hexdigest() != asset["sha256"]:
                    raise ValueError("本地素材文件发生变化，已停止同步。")
            else:
                shutil.copyfile(staging / asset["file"], destination)
        for template in catalog["templates"]:
            for asset in all_assets(template):
                replacement = remapped[asset["file"]]
                asset.clear()
                asset.update(replacement)
        replacement = staging / CATALOG
        replacement.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(replacement, directory / CATALOG)
    return {"version": expected_version, "templates": len(catalog["templates"]), "files": len(remapped)}
