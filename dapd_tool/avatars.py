"""Bounded, credential-free avatar loading. Only sanitized thumbnails reach Qt."""
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QPixmap


def avatar_thumbnail(url):
    if urlsplit(url).scheme != "https":
        return b""
    url += ("&" if "?" in url else "?") + "image_size=64x64&cut_type=&quality=&format=image&sticker_format=.webp"
    with tempfile.TemporaryDirectory(prefix="dapd-avatar-") as folder:
        source = Path(folder) / "source"
        size = 0
        started = time.monotonic()
        with httpx.stream("GET", url, timeout=6, follow_redirects=False) as response:
            response.raise_for_status()
            with source.open("wb") as target:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 2 * 1024 * 1024 or time.monotonic() - started > 10:
                        raise ValueError("头像文件过大或下载超时")
                    target.write(chunk)
        with Image.open(source) as original:
            if original.format not in {"PNG", "JPEG", "WEBP", "GIF", "BMP"} or original.width * original.height > 16_000_000:
                raise ValueError("不支持的头像格式或尺寸")
            original.seek(0)
            thumbnail = ImageOps.fit(ImageOps.exif_transpose(original).convert("RGB"), (64, 64))
            clean = Image.new("RGB", thumbnail.size)
            clean.paste(thumbnail)
            safe = Path(folder) / "thumbnail.png"
            clean.save(safe, format="PNG")
        with Image.open(safe) as check:
            check.verify()
        return safe.read_bytes()


class AvatarResult(QObject):
    ready = Signal(str, bytes)


class AvatarJob(QRunnable):
    def __init__(self, url, result):
        super().__init__()
        self.url, self.result = url, result

    def run(self):
        try:
            content = avatar_thumbnail(self.url)
        except Exception:
            content = b""
        self.result.ready.emit(self.url, content)


class AvatarCache(QObject):
    changed = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.images, self.pending = {}, set()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.result = AvatarResult(self)
        self.result.ready.connect(self.loaded)

    def get(self, url):
        if url and url not in self.images and url not in self.pending and len(self.pending) < 8:
            self.pending.add(url)
            self.pool.start(AvatarJob(url, self.result))
        return self.images.get(url)

    @Slot(str, bytes)
    def loaded(self, url, content):
        self.pending.discard(url)
        pixmap = QPixmap()
        if content:
            pixmap.loadFromData(content, "PNG")
        self.images[url] = pixmap
        self.changed.emit()
