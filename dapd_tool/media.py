"""Immutable local media, safe image copies and upload journaling helpers."""
import copy
import hashlib
import html
import mimetypes
import re
import shutil
import uuid
from pathlib import Path

from PIL import Image, ImageOps

MAX_FILE = 50 * 1024 * 1024
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".tga"}
MIMES = {".pdf":"application/pdf", ".doc":"application/msword", ".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         ".xlsx":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xls":"application/vnd.ms-excel",
         ".csv":"text/csv", ".txt":"text/plain", ".mp4":"video/mp4", ".webm":"video/webm", ".mov":"video/quicktime",
         ".avi":"video/x-msvideo", ".mp3":"audio/mpeg", ".wav":"audio/wav", ".m4a":"audio/m4a", ".ogg":"audio/ogg",
         ".flac":"audio/flac", ".aac":"audio/aac"}


def empty_content():
    return {"parts": [], "attachments": []}


def validate_asset(asset):
    if not isinstance(asset, dict) or set(asset) != {"id", "name", "file", "mime", "size", "sha256"}:
        raise ValueError("模板文件信息不完整，请重新添加文件。")
    if not re.fullmatch(r"[0-9a-f]{32}", asset["id"]) or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]):
        raise ValueError("模板文件标识无效。")
    if not re.fullmatch(r"[0-9a-f]{32}\.[a-z0-9]+", asset["file"]) or not asset["file"].startswith(asset["id"] + "."):
        raise ValueError("模板文件路径无效。")
    if not isinstance(asset["size"], int) or not 0 < asset["size"] <= MAX_FILE:
        raise ValueError("文件为空或超过 50 MB。")
    return copy.deepcopy(asset)


def validate_content(content=None):
    content = content if content is not None else empty_content()
    if not isinstance(content, dict) or not {"parts", "attachments"}.issubset(content) or set(content) - {"parts", "attachments", "html", "assignee"}:
        raise ValueError("任务描述结构无效。")
    result = empty_content()
    for part in content["parts"]:
        if isinstance(part, dict) and set(part) == {"text"} and isinstance(part["text"], str):
            result["parts"].append({"text": part["text"]})
        elif isinstance(part, dict) and set(part) == {"image"}:
            asset = validate_asset(part["image"])
            if not asset["mime"].startswith("image/"):
                raise ValueError("描述中的图片文件类型不正确。")
            result["parts"].append({"image": asset})
        elif isinstance(part, dict) and set(part) == {"file"}:
            asset = validate_asset(part["file"])
            if asset["mime"].startswith("image/"):
                raise ValueError("描述中的图片请使用图片块。")
            result["parts"].append({"file": asset})
        else:
            raise ValueError("任务描述包含不支持的内容。")
    if sum(len(p.get("text", "")) for p in result["parts"]) > 200000:
        raise ValueError("单个任务的描述不能超过 20 万字。")
    result["attachments"] = [validate_asset(asset) for asset in content["attachments"]]
    if "html" in content:
        if not isinstance(content["html"], str) or len(content["html"]) > 2_000_000:
            raise ValueError("富文本描述无效或过长。")
        result["html"] = content["html"]
        references = set(re.findall(r"dapd-asset:([a-f0-9]{32})", content["html"]))
        if references - set(description_assets(result)):
            raise ValueError("富文本引用了未包含的文件，请重新添加。")
    if content.get("assignee"):
        assignee = content["assignee"]
        if not isinstance(assignee, dict) or set(assignee) != {"id", "name"} or not all(isinstance(v, str) and v.strip() for v in assignee.values()):
            raise ValueError("默认负责人信息无效，请重新选择。")
        result["assignee"] = copy.deepcopy(assignee)
    if len(result["attachments"]) > 100:
        raise ValueError("单个任务最多添加 100 个附件。")
    return result


class Assets:
    def __init__(self, directory):
        self.directory = Path(directory) / "assets"
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, asset, verify_hash=False):
        asset = validate_asset(asset)
        path = self.directory / asset["file"]
        if not path.is_file() or path.stat().st_size != asset["size"]:
            raise ValueError(f"本地文件缺失或已变更：{asset['name']}。请重新添加。")
        if verify_hash and hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise ValueError(f"本地文件校验失败：{asset['name']}。请重新添加。")
        return path

    def import_file(self, source, *, image_only=False):
        source = Path(source)
        if not source.is_file() or not 0 < source.stat().st_size <= MAX_FILE:
            raise ValueError("请选择有效文件，单文件不能超过 50 MB。")
        before = (source.stat().st_size, source.stat().st_mtime_ns, hashlib.sha256(source.read_bytes()).hexdigest())
        identifier = uuid.uuid4().hex
        extension = source.suffix.lower()
        is_image = extension in IMAGE_EXTENSIONS
        if image_only and not is_image:
            raise ValueError("请使用 PNG、JPEG、WebP、BMP、TIFF、TGA 或静态 GIF 图片。")
        if not is_image and extension not in MIMES:
            raise ValueError("DAPD 暂不支持这种文件。可使用常见图片、PDF、Word、Excel、CSV、TXT、音频或视频。")
        output = None
        try:
            if is_image:
                # Metadata and decode cost first. Original files are never edited or previewed.
                with Image.open(source) as image:
                    actual = Image.registered_extensions().get(extension)
                    if image.format != actual or image.width * image.height > 40_000_000:
                        raise ValueError("图片格式与扩展名不符，或像素超过 4000 万，请先另存为常见尺寸图片。")
                    if getattr(image, "n_frames", 1) > 1:
                        raise ValueError("暂不处理动态/多页图片，请导出需要的静态图片后添加。")
                    clean = ImageOps.exif_transpose(image).convert("RGBA" if "A" in image.getbands() else "RGB")
                    clean.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
                    output = self.directory / (identifier + ".png")
                    # Export pixels only: no EXIF, GPS, source comments, or source paths.
                    pixels = Image.new(clean.mode, clean.size)
                    pixels.paste(clean)
                    pixels.save(output, "PNG")
                with Image.open(output) as check:
                    check.verify()
                name, mime = source.stem + ".png", "image/png"
            else:
                output = self.directory / (identifier + extension)
                shutil.copyfile(source, output)
                name, mime = source.name, MIMES[extension]
            if output.stat().st_size > MAX_FILE:
                raise ValueError("处理后的图片超过 50 MB，请使用更小的图片。")
            after = (source.stat().st_size, source.stat().st_mtime_ns, hashlib.sha256(source.read_bytes()).hexdigest())
            if before != after:
                raise ValueError("原文件在复制期间发生变化，请检查后重新添加。")
            return {"id":identifier, "name":name, "file":output.name, "mime":mime, "size":output.stat().st_size,
                    "sha256":hashlib.sha256(output.read_bytes()).hexdigest()}
        except Exception:
            if output is not None and output.exists():
                output.unlink()
            raise


def image_assets(content):
    return {p["image"]["id"]:p["image"] for p in content["parts"] if "image" in p}


def description_assets(content):
    return {asset["id"]: asset for part in content["parts"] for kind, asset in part.items() if kind in ("image", "file")}


def description_html(content, urls):
    if "html" in content:
        value = content["html"]
        for identifier, url in urls.items():
            value = value.replace("dapd-asset:" + identifier, html.escape(url, quote=True))
        if "dapd-asset:" in value:
            raise ValueError("描述中有未上传的文件。")
        return value
    if not content["parts"]:
        return ""
    chunks = []
    for part in content["parts"]:
        if "text" in part:
            chunks.append(html.escape(part["text"]).replace("\n", "</p><p>"))
        elif "image" in part:
            asset = part["image"]
            chunks.append('<img src="' + html.escape(urls[asset["id"]], quote=True) + '" alt="' + html.escape(asset["name"], quote=True) + '" />')
        else:
            asset = part["file"]
            chunks.append('<a href="' + html.escape(urls[asset["id"]], quote=True) + '">' + html.escape(asset["name"]) + '</a>')
    return "<p>" + "".join(chunks) + "</p>"


def upload_name(job, node, kind, asset):
    # A stable marker makes ambiguous uploads reconcilable without resending.
    marker = hashlib.sha256(f"{job}/{node}/{kind}/{asset['id']}".encode()).hexdigest()[:16]
    name = Path(asset["name"])
    return name.stem[:100] + "__" + marker + name.suffix
