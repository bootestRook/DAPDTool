"""Offline BlockNote host. The web editor receives no API credentials."""
import base64
import json
import tempfile
import threading
from urllib.parse import urlsplit
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QEventLoop, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView


class EditorPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, kind, main):
        if kind == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            if url.scheme() in ("https", "http"):
                QDesktopServices.openUrl(url)
            return False
        return url.scheme() in ("file", "qrc", "about")


class Bridge(QObject):
    readySignal = Signal()
    remoteReady = Signal(str, str)

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    @Slot()
    def ready(self):
        self.owner.ready = True
        self.readySignal.emit()

    @Slot(bool)
    def setCollapsed(self, collapsed):
        self.owner.setMinimumHeight(48 if collapsed else 200)
        self.owner.setMaximumHeight(48 if collapsed else 16777215)

    @Slot(str, str, result=str)
    def importFile(self, data, name):
        try:
            if len(data) > 70_000_000:
                raise ValueError("文件超过 50 MB。")
            from .media import IMAGE_EXTENSIONS
            raw = base64.b64decode(data, validate=True)
            suffix = Path(name).suffix.lower()
            if suffix in IMAGE_EXTENSIONS:
                from PIL import Image
                import io
                with Image.open(io.BytesIO(raw)) as picture:
                    extensions = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp", "GIF": ".gif", "BMP": ".bmp", "TIFF": ".tif", "TGA": ".tga"}
                    suffix = extensions.get(picture.format)
                    if not suffix or picture.width * picture.height > 40_000_000:
                        raise ValueError("图片格式或尺寸不受支持。")
            with tempfile.TemporaryDirectory(prefix="dapd-paste-") as folder:
                source = Path(folder) / (Path(name).stem[:100] + suffix)
                source.write_bytes(raw)
                asset = self.owner.assets.import_file(source)
            return json.dumps({"url": self.owner.register_asset(asset)})
        except Exception as exc:
            return json.dumps({"error": str(exc) if isinstance(exc, ValueError) else "无法读取文件，请重新选择。"})

    @Slot(str, str)
    def importRemoteImage(self, request_id, url):
        def download():
            try:
                import httpx
                parsed = urlsplit(url)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("复制的图片需要有效的 HTTPS 链接。")
                data = bytearray()
                with httpx.stream("GET", url, timeout=25, follow_redirects=False) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 50 * 1024 * 1024:
                            raise ValueError("复制的图片超过 50 MB。")
                result = self.importFile(base64.b64encode(data).decode("ascii"), "粘贴图片.png")
            except Exception:
                result = json.dumps({"error": "无法下载复制的图片，请复制图片本身，或保存到本机后插入。"})
            self.remoteReady.emit(request_id, result)
        threading.Thread(target=download, daemon=True).start()


class RichEditor(QWebEngineView):
    def __init__(self, assets, parent=None, readonly=False):
        super().__init__(parent)
        self.assets, self.media = assets, {}
        self.ready, self.readonly = False, readonly
        self.setPage(EditorPage(self))
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste, True)
        self.channel = QWebChannel(self.page())
        self.bridge = Bridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.page().setWebChannel(self.channel)
        self.setUrl(QUrl.fromLocalFile(str(Path(__file__).parent / "editor_dist" / "index.html")))
        self.setMinimumHeight(200)

    def wait_ready(self):
        if not self.ready:
            loop = QEventLoop()
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            self.bridge.readySignal.connect(loop.quit)
            timer.start(15000)
            loop.exec()
            self.bridge.readySignal.disconnect(loop.quit)
            if not self.ready:
                raise ValueError("富文本编辑器加载失败，请重新打开窗口。")

    def evaluate(self, expression):
        self.wait_ready()
        result = []
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        def received(value):
            result.append(value)
            loop.quit()
        self.page().runJavaScript(expression, received)
        timer.start(10000)
        loop.exec()
        if not result:
            raise ValueError("编辑器未响应，请稍后再试。")
        return result[0]

    def register_asset(self, asset):
        path = self.assets.path(asset, verify_hash=True)
        url = ("data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
               if asset["mime"].startswith("image/") else QUrl.fromLocalFile(str(path.resolve())).toString())
        self.media[url] = asset
        return url

    def set_html(self, html, assets):
        self.bridge.setCollapsed(False)
        self.media = {}
        for asset in assets:
            html = html.replace("dapd-asset:" + asset["id"], self.register_asset(asset))
        if not self.evaluate("window.setContent(" + json.dumps(html) + "," + json.dumps(self.readonly) + ")"):
            raise ValueError("描述包含无法读取的格式，已停止编辑以防内容丢失。")

    def snapshot(self):
        result = json.loads(self.evaluate("JSON.stringify(window.getContent())"))
        if not isinstance(result, dict):
            raise ValueError("无法读取编辑器内容。")
        if result.get("pending"):
            raise ValueError("正在保存描述中的文件，请稍后再保存或切换任务。")
        media = []
        for url, asset in self.media.items():
            if url in result["html"]:
                result["html"] = result["html"].replace(url, "dapd-asset:" + asset["id"])
                media.append(asset)
        result["media"] = media
        return result

    def setPlainText(self, text):
        self.evaluate("window.setPlainText(" + json.dumps(text) + ")")

    def toPlainText(self):
        return self.snapshot()["text"]

    def insert_asset(self, asset):
        self.evaluate("window.insertImage(" + json.dumps(self.register_asset(asset)) + ")")
