from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QDialog, QFormLayout, QHBoxLayout, QLineEdit, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout
from ..widgets.content_editor import ContentEditor
from ...media import empty_content
from ..controls import label, button, confirm


class TemplateDialog(QDialog):
    def __init__(self, store, template=None, parent=None, people=None):
        super().__init__(parent)
        self.store, self.template = store, template
        self.saved_id = None
        self.setWindowTitle("编辑模板" if template else "新建模板")
        self.resize(1120, 760)
        self.setMinimumSize(980, 680)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        form = QFormLayout()
        self.name = QLineEdit(template["name"] if template else "")
        self.name.setPlaceholderText("给这个模板起个名字")
        form.addRow("模板名称", self.name)
        layout.addLayout(form)
        layout.addWidget(label("主任务标题在创建时输入。双击子任务改名；选中任意节点，编辑其固定描述、图片和附件。", "muted"))
        row = QHBoxLayout()
        row.addWidget(button("添加同级", self.add_sibling))
        row.addWidget(button("添加子任务", self.add_child))
        row.addWidget(button("删除节点", self.remove))
        row.addStretch()
        layout.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("任务层级")
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.root = QTreeWidgetItem(["主任务标题（创建时填写）"])
        self.root.setData(0,Qt.ItemDataRole.UserRole,(template or {}).get("root",empty_content()))
        self.tree.addTopLevelItem(self.root)
        items = []
        for node in (template or {}).get("nodes", []):
            parent_item = self.root if node["parent"] is None else items[node["parent"]]
            items.append(self.new_item(node["title"], parent_item,node.get("content",empty_content())))
        self.tree.expandAll()
        self.tree.setCurrentItem(self.root)
        split=QSplitter()
        split.addWidget(self.tree)
        self.editor=ContentEditor(store.directory)
        if people:
            self.editor.set_people(people)
        split.addWidget(self.editor)
        split.setSizes([380,650])
        layout.addWidget(split,1)
        self.editing_item=self.root
        self.editor.set_content(self.root.data(0,Qt.ItemDataRole.UserRole))
        self.tree.currentItemChanged.connect(self.node_changed)
        row = QHBoxLayout()
        row.addWidget(button("上移", lambda: self.move(-1)))
        row.addWidget(button("下移", lambda: self.move(1)))
        row.addWidget(button("降为子级", self.indent))
        row.addWidget(button("升为上级", self.outdent))
        row.addStretch()
        layout.addLayout(row)
        self.error = label("")
        layout.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("取消", self.reject))
        row.addWidget(button("保存模板", self.save, True))
        layout.addLayout(row)
        self.initial = (self.name.text(), self.nodes(),self.root.data(0,Qt.ItemDataRole.UserRole))

    def new_item(self, title, parent, content=None):
        item = QTreeWidgetItem([title])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setData(0,Qt.ItemDataRole.UserRole,content if content is not None else empty_content())
        parent.addChild(item)
        return item

    def flush_content(self):
        if self.editing_item is not None:
            self.editing_item.setData(0,Qt.ItemDataRole.UserRole,self.editor.content())

    def node_changed(self,current,previous):
        if previous is not None and previous is self.editing_item:
            try:
                self.flush_content()
            except ValueError as exc:
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(previous)
                self.tree.blockSignals(False)
                self.error.setText(str(exc))
                return
        self.editing_item=current
        self.editor.setEnabled(current is not None)
        if current:
            self.editor.heading.setText("固定描述 · " + ("主任务" if current is self.root else current.text(0)))
            self.editor.set_content(current.data(0,Qt.ItemDataRole.UserRole) or empty_content())

    def add_sibling(self):
        current = self.tree.currentItem() or self.root
        parent = current.parent() or self.root
        item = self.new_item("新任务", parent)
        if current is not self.root:
            parent.takeChild(parent.indexOfChild(item))
            parent.insertChild(parent.indexOfChild(current) + 1, item)
        parent.setExpanded(True)
        self.tree.setCurrentItem(item)
        self.tree.editItem(item, 0)

    def add_child(self):
        parent = self.tree.currentItem() or self.root
        item = self.new_item("新任务", parent)
        parent.setExpanded(True)
        self.tree.setCurrentItem(item)
        self.tree.editItem(item, 0)

    def remove(self):
        item = self.tree.currentItem()
        if item and item is not self.root:
            if item.childCount() and not confirm(self, "删除这个节点及其所有子任务？", "删除"):
                return
            parent=item.parent()
            self.tree.setCurrentItem(parent)
            parent.removeChild(item)

    def move(self, step):
        item = self.tree.currentItem()
        if not item or item is self.root:
            return
        parent = item.parent()
        index = parent.indexOfChild(item)
        if 0 <= index + step < parent.childCount():
            parent.takeChild(index)
            parent.insertChild(index + step, item)
            self.tree.setCurrentItem(item)

    def indent(self):
        item = self.tree.currentItem()
        if not item or item is self.root:
            return
        parent = item.parent()
        index = parent.indexOfChild(item)
        if index:
            new_parent = parent.child(index - 1)
            parent.takeChild(index)
            new_parent.addChild(item)
            new_parent.setExpanded(True)
            self.tree.setCurrentItem(item)

    def outdent(self):
        item = self.tree.currentItem()
        if not item or item is self.root or item.parent() is self.root:
            return
        parent = item.parent()
        grandparent = parent.parent()
        parent.takeChild(parent.indexOfChild(item))
        grandparent.insertChild(grandparent.indexOfChild(parent) + 1, item)
        self.tree.setCurrentItem(item)

    def nodes(self):
        if hasattr(self,"editing_item"):
            self.flush_content()
        result = []
        def walk(parent, parent_index):
            for index in range(parent.childCount()):
                item = parent.child(index)
                position = len(result)
                node={"title": item.text(0), "parent": parent_index}
                content=item.data(0,Qt.ItemDataRole.UserRole) or empty_content()
                if content["parts"] or content["attachments"] or content.get("html") or content.get("assignee"):
                    node["content"]=content
                result.append(node)
                walk(item, position)
        walk(self.root, None)
        return result

    def save(self):
        self.tree.clearFocus()
        try:
            nodes=self.nodes()
            self.saved_id = self.store.save_template(self.name.text(), nodes, (self.template or {}).get("id"),self.root.data(0,Qt.ItemDataRole.UserRole))
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()

    def reject(self):
        if (self.name.text(), self.nodes(),self.root.data(0,Qt.ItemDataRole.UserRole)) != self.initial and not confirm(self, "模板尚未保存，放弃本次修改？", "放弃修改"):
            return
        super().reject()
