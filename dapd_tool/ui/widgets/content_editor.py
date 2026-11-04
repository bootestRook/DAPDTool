"""Per-node fixed text, inline pictures and attachment editor."""
import copy

from PySide6.QtCore import Qt
from .rich_editor import RichEditor
from .assignee_picker import AssigneePicker
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from ...media import Assets, empty_content, validate_content, description_assets, description_html


class ContentEditor(QWidget):
    def __init__(self, directory, parent=None, *, readonly=False):
        super().__init__(parent)
        self.assets = Assets(directory)
        self.original = empty_content()
        self.readonly = readonly
        self.upload_action = "创建任务时上传。"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(10)
        self.heading = QLabel("固定描述")
        self.heading.setObjectName("section")
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)
        self.note = QLabel("每个节点独立保存负责人和描述。")
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.assignee = AssigneePicker(directory, self)
        self.assignee.setAccessibleName("默认负责人")
        self.assignee.setEnabled(not readonly)
        owner_row = QHBoxLayout()
        self.assignee_label = QLabel("默认负责人")
        owner_row.addWidget(self.assignee_label)
        owner_row.addWidget(self.assignee, 1)
        layout.addLayout(owner_row)
        self.description = RichEditor(self.assets, self, readonly=readonly)
        self.description.setAccessibleName("节点富文本描述")
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
        self.attachments.setMaximumHeight(90)
        self.attachments.setMinimumHeight(45)
        self.attachments.hide()
        layout.addWidget(self.attachments)
        self.error = QLabel("")
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.setObjectName("muted")
        layout.addWidget(self.error)

    def set_people(self, directory):
        self.assignee.set_directory(directory)

    def select_assignee(self, selected):
        self.assignee.set_value(selected)

    def set_content(self, content):
        self.original = validate_content(content)
        self.attachments.clear()
        self.attachments.hide()
        self.error.clear()
        self.select_assignee(content.get("assignee"))
        media = description_assets(content)
        html = description_html(content, {i: "dapd-asset:" + i for i in media}) if "html" not in content else content["html"]
        self.description.set_html(html, media.values())
        for asset in content["attachments"]:
            self.add_asset_item(asset)

    def content(self):
        state = self.description.snapshot()
        if state["changed"]:
            value = {"html": state["html"], "parts": [{"text": state["text"]}] + [
                {"image" if a["mime"].startswith("image/") else "file": a} for a in state["media"]], "attachments": []}
        else:
            value = copy.deepcopy(self.original)
        value["attachments"] = [self.attachments.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.attachments.count())]
        value.pop("assignee", None)
        if self.assignee.value():
            value["assignee"] = self.assignee.value()
        return validate_content(value)

    def add_asset_item(self,asset):
        size=f"{asset['size']} B" if asset['size']<1024 else f"{asset['size']/1024:.1f} KB"
        item=QListWidgetItem(f"{asset['name']}    {size}")
        item.setData(Qt.ItemDataRole.UserRole,copy.deepcopy(asset))
        self.attachments.addItem(item)
        self.attachments.show()

    def add_attachments(self):
        paths,_=QFileDialog.getOpenFileNames(self,"选择附件（单文件最大 50 MB）","","支持的文件 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif *.tga *.pdf *.doc *.docx *.xls *.xlsx *.csv *.txt *.mp4 *.webm *.mov *.avi *.mp3 *.wav *.m4a *.ogg *.flac *.aac)")
        for path in paths:
            try:
                self.add_asset_item(self.assets.import_file(path))
                self.error.setText("已保存本地副本。" + self.upload_action)
            except Exception as exc:
                self.error.setText(str(exc) if isinstance(exc,ValueError) else "无法复制文件，请检查文件是否可读。")
                break

    def remove_attachment(self):
        index=self.attachments.currentRow()
        if index>=0:
            self.attachments.takeItem(index)
        self.attachments.setVisible(self.attachments.count() > 0)
