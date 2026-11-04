"""Per-node fixed text, inline pictures and attachment editor."""
import copy

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QTextCursor, QTextDocument, QTextImageFormat
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QTextEdit, QVBoxLayout, QWidget

from .media import Assets, empty_content, validate_content


class DescriptionEdit(QTextEdit):
    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())

    def canInsertFromMimeData(self, source):
        return source.hasText()

    def loadResource(self, kind, name):
        # Only explicitly added sanitized local image resources are rendered.
        return None


class ContentEditor(QWidget):
    def __init__(self, directory, parent=None, *, readonly=False):
        super().__init__(parent)
        self.assets = Assets(directory)
        self.images = {}
        self.readonly = readonly
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(10)
        self.heading = QLabel("固定描述")
        self.heading.setObjectName("section")
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)
        self.note = QLabel("文字和图片会复用到每个新任务。选中左侧节点可分别编辑。")
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        if not readonly:
            row = QHBoxLayout()
            insert = QPushButton("插入图片")
            insert.setAutoDefault(False)
            insert.clicked.connect(self.insert_image)
            row.addWidget(insert)
            row.addStretch()
            layout.addLayout(row)
        self.description = DescriptionEdit()
        self.description.setAcceptRichText(False)
        self.description.setReadOnly(readonly)
        self.description.setPlaceholderText("输入这个任务的固定描述；可在光标位置插入图片。")
        self.description.setAccessibleName("节点固定描述")
        self.description.setMinimumHeight(140)
        layout.addWidget(self.description,1)
        row = QHBoxLayout()
        row.addWidget(QLabel("附件"),1)
        if not readonly:
            add = QPushButton("添加附件")
            add.setAutoDefault(False)
            add.clicked.connect(self.add_attachments)
            remove = QPushButton("移除所选")
            remove.setAutoDefault(False)
            remove.clicked.connect(self.remove_attachment)
            row.addWidget(add)
            row.addWidget(remove)
        layout.addLayout(row)
        self.attachments = QListWidget()
        self.attachments.setAccessibleName("节点附件")
        self.attachments.setMaximumHeight(115)
        self.attachments.setMinimumHeight(75)
        layout.addWidget(self.attachments)
        self.error = QLabel("")
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.setObjectName("muted")
        layout.addWidget(self.error)

    def image_cursor(self, cursor, asset):
        path = self.assets.path(asset)
        image = QImage(str(path))
        if image.isNull():
            raise ValueError("无法读取已保存的图片，请重新添加。")
        name = "dapd-asset:" + asset["id"]
        self.images[name] = copy.deepcopy(asset)
        self.description.document().addResource(QTextDocument.ResourceType.ImageResource,QUrl(name),image)
        fmt = QTextImageFormat()
        fmt.setName(name)
        width = min(460,image.width())
        fmt.setWidth(width)
        fmt.setHeight(width*image.height()/image.width())
        cursor.insertImage(fmt)

    def set_content(self, content):
        content = validate_content(content)
        self.description.clear()
        self.images = {}
        self.attachments.clear()
        self.error.clear()
        cursor = self.description.textCursor()
        try:
            for part in content["parts"]:
                if "text" in part:
                    cursor.insertText(part["text"])
                else:
                    self.image_cursor(cursor,part["image"])
            for asset in content["attachments"]:
                self.add_asset_item(asset)
        except ValueError as exc:
            self.error.setText(str(exc))
            # A missing asset must not silently disappear on save.
            raise
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.description.setTextCursor(cursor)

    def content(self):
        parts=[]
        block=self.description.document().begin()
        first=True
        while block.isValid():
            if not first:
                parts.append({"text":"\n"})
            first=False
            iterator=block.begin()
            while not iterator.atEnd():
                fragment=iterator.fragment()
                if fragment.isValid():
                    if fragment.charFormat().isImageFormat():
                        name=fragment.charFormat().toImageFormat().name()
                        if name not in self.images:
                            raise ValueError("描述含未登记的图片，请使用“插入图片”添加。")
                        parts.append({"image":copy.deepcopy(self.images[name])})
                    else:
                        parts.append({"text":fragment.text()})
                iterator+=1
            block=block.next()
        # Merge adjacent text fragments without touching inline image positions.
        merged=[]
        for part in parts:
            if "text" in part and merged and "text" in merged[-1]:
                merged[-1]["text"]+=part["text"]
            else:
                merged.append(part)
        return validate_content({"parts":merged,"attachments":[self.attachments.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.attachments.count())]})

    def insert_image(self):
        path,_=QFileDialog.getOpenFileName(self,"选择描述图片","","静态图片 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif *.tga)")
        if not path:
            return
        try:
            asset=self.assets.import_file(path,image_only=True)
            cursor=self.description.textCursor()
            self.image_cursor(cursor,asset)
            self.description.setTextCursor(cursor)
            self.error.setText("已保存图片副本，原图未修改。创建任务时才上传。")
        except Exception as exc:
            self.error.setText(str(exc) if isinstance(exc,ValueError) else "无法读取图片，请检查文件是否有效。")

    def add_asset_item(self,asset):
        size=f"{asset['size']} B" if asset['size']<1024 else f"{asset['size']/1024:.1f} KB"
        item=QListWidgetItem(f"{asset['name']}    {size}")
        item.setData(Qt.ItemDataRole.UserRole,copy.deepcopy(asset))
        self.attachments.addItem(item)

    def add_attachments(self):
        paths,_=QFileDialog.getOpenFileNames(self,"选择附件（单文件最大 50 MB）","","支持的文件 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif *.tga *.pdf *.doc *.docx *.xls *.xlsx *.csv *.txt *.mp4 *.webm *.mov *.avi *.mp3 *.wav *.m4a *.ogg *.flac *.aac)")
        for path in paths:
            try:
                self.add_asset_item(self.assets.import_file(path))
                self.error.setText("已保存本地副本，创建任务时才上传。图片副本会移除元数据并限制到 4096 像素。")
            except Exception as exc:
                self.error.setText(str(exc) if isinstance(exc,ValueError) else "无法复制文件，请检查文件是否可读。")
                break

    def remove_attachment(self):
        index=self.attachments.currentRow()
        if index>=0:
            self.attachments.takeItem(index)
