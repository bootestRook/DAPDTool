from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QSplitter, QTreeWidget, QVBoxLayout
from ..widgets.content_editor import ContentEditor
from ...media import empty_content, image_assets
from ..controls import label, button
from ..widgets.plan_tree import fill_plan


class PreviewDialog(QDialog):
    def __init__(self, plan, parent=None, directory=None):
        super().__init__(parent)
        self.setWindowTitle("核对创建清单")
        self.resize(1050, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        dest = plan["destination"]
        roots = sum(node["parent"] is None for node in plan["nodes"])
        total = len(plan["nodes"])
        layout.addWidget(label(f"将创建 {total} 个任务", "heading"))
        layout.addWidget(label(f"{roots} 个主任务 · {total - roots} 个模板子任务", "muted"))
        layout.addWidget(label(f"项目：{dest['projectName']}\n任务组：{dest['groupName']}\n父任务：{dest.get('parentTitle') or '无（任务组顶层）'}", "notice"))
        tree = QTreeWidget()
        tree.setHeaderLabel("创建后的层级")
        fill_plan(tree, plan)
        if directory is not None:
            split=QSplitter()
            split.addWidget(tree)
            content=ContentEditor(directory,readonly=True)
            content.note.setText("将按模板写入以下固定内容。附件会关联到这个任务。")
            split.addWidget(content)
            split.setSizes([380,600])
            items=[]
            def collect(item):
                items.append(item)
                for i in range(item.childCount()):collect(item.child(i))
            for i in range(tree.topLevelItemCount()):collect(tree.topLevelItem(i))
            for i,item in enumerate(items):item.setData(0,Qt.ItemDataRole.UserRole,i)
            def selected():
                item=tree.currentItem()
                if item:
                    content.set_content(plan["nodes"][item.data(0,Qt.ItemDataRole.UserRole)].get("content",empty_content()))
            tree.itemSelectionChanged.connect(selected)
            tree.setCurrentItem(tree.topLevelItem(0))
            layout.addWidget(split,1)
        else:
            layout.addWidget(tree,1)
        images=sum(len(image_assets(n.get("content",empty_content()))) for n in plan["nodes"])
        attachments=sum(len(n.get("content",empty_content())["attachments"]) for n in plan["nodes"])
        layout.addWidget(label(f"描述图片 {images} 张 · 附件 {attachments} 个。负责人和日期留空，停止时保留已完成进度。", "muted"))
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("返回修改", self.reject))
        row.addWidget(button(f"创建 {total} 个任务", self.accept, True))
        layout.addLayout(row)
