"""A lightweight task tree: cached text, linear filtering, no per-cell widgets."""
from datetime import datetime

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QFont

from ...tasks import task_hierarchy


def date_label(value):
    if not value:
        return "未设置"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


class TaskTreeModel(QAbstractItemModel):
    headers = ["任务 / 层级", "任务组", "负责人", "状态", "优先级", "创建时间", "截止时间", "更新时间", "创建者", "任务 ID"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tasks = {}
        self.values = {}
        self.children = {None: []}
        self.parents = {}
        self.rows = {}
        self.order = []
        self.query = ""
        self.matches = 0
        self.search_text = {}
        self.all_children = {None: []}
        self.own_ids = set()
        self.highlight_own = False
        self.own_background = QBrush(QColor("#e9f2f3"))
        self.own_foreground = QBrush(QColor("#244e58"))
        self.own_font = QFont()
        self.own_font.setBold(True)

    def replace(self, data):
        tasks = sorted(data["tasks"], key=lambda t: (t.get("sortOrder") or 0, t.get("createdAt") or ""))
        order = task_hierarchy(tasks)
        by_id = {t["id"]: t for t in tasks}
        values, parents, children, search_text = {}, {}, {None: []}, {}
        priorities = {"low": "低", "medium": "中", "high": "高", "urgent": "紧急"}
        for task in tasks:
            identifier = task["id"]
            group = task.get("taskGroupId", "")
            state = task.get("status", "")
            priority = task.get("priority", "")
            values[identifier] = [task["title"] + ("（父任务，仅展示）" if task.get("contextOnly") else ""),
                data["groups"].get(group, group), (task.get("assignee") or {}).get("name") or "未指派",
                data["statuses"].get(task["projectId"], {}).get(state, state), priorities.get(priority, priority),
                date_label(task.get("createdAt")), date_label(task.get("dueDate")), date_label(task.get("updatedAt")),
                (task.get("createdBy") or {}).get("name", ""), identifier]
            search_text[identifier] = " ".join(values[identifier]).casefold()
            parent = task.get("parentTaskId")
            parents[identifier] = parent if parent in by_id else None
            children.setdefault(parents[identifier], []).append(identifier)
        self.beginResetModel()
        self.tasks, self.order, self.values = by_id, order, values
        self.own_ids = set(data.get("own_ids", ()))
        self.parents, self.all_children, self.search_text = parents, children, search_text
        self._filter()
        self.endResetModel()

    def set_highlight_own(self, enabled):
        if self.highlight_own == enabled:
            return
        self.highlight_own = enabled
        roles = [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole,
                 Qt.ItemDataRole.ForegroundRole, Qt.ItemDataRole.FontRole]
        for identifiers in self.children.values():
            if identifiers:
                self.dataChanged.emit(self.createIndex(0, 0, identifiers[0]),
                    self.createIndex(len(identifiers) - 1, len(self.headers) - 1, identifiers[-1]), roles)

    def set_query(self, text):
        query = text.strip().casefold()
        if query == self.query:
            return
        self.beginResetModel()
        self.query = query
        self._filter()
        self.endResetModel()

    def _filter(self):
        visible = {identifier for identifier, text in self.search_text.items() if self.query in text}
        self.matches = sum(not self.tasks[i].get("contextOnly") for i in visible)
        # Parent-first order reversed visits each descendant before its ancestors.
        for identifier in reversed(self.order):
            if identifier in visible and self.parents[identifier] is not None:
                visible.add(self.parents[identifier])
        self.children = {parent: [i for i in items if i in visible] for parent, items in self.all_children.items()}
        self.rows = {identifier: row for items in self.children.values() for row, identifier in enumerate(items)}

    def index(self, row, column, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()
        identifier = parent.internalPointer() if parent.isValid() else None
        children = self.children.get(identifier, [])
        if 0 <= row < len(children) and 0 <= column < len(self.headers):
            return self.createIndex(row, column, children[row])
        return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        parent = self.parents[index.internalPointer()]
        if parent is None:
            return QModelIndex()
        return self.createIndex(self.rows[parent], 0, parent)

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return 0
        return len(self.children.get(parent.internalPointer() if parent.isValid() else None, []))

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        identifier = index.internalPointer()
        own = self.highlight_own and identifier in self.own_ids
        if role == Qt.ItemDataRole.DisplayRole:
            value = self.values[identifier][index.column()]
            return "我创建的 · " + value if own and index.column() == 0 else value
        if own:
            if role == Qt.ItemDataRole.BackgroundRole:
                return self.own_background
            if role == Qt.ItemDataRole.ForegroundRole:
                return self.own_foreground
            if role == Qt.ItemDataRole.FontRole and index.column() == 0:
                return self.own_font
        if role == Qt.ItemDataRole.UserRole:
            return self.tasks[identifier]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None
