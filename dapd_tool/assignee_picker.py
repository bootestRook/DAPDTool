"""DAPD-style searchable single-person popup, shared by both editors."""
import hashlib
import json
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QStyle,
    QStyledItemDelegate, QVBoxLayout, QWidget)

from .avatars import AvatarCache
from .people import child_departments, department_paths, scoped_users

ROLE = Qt.ItemDataRole.UserRole


def marker_pixmap(kind, size=24):
    """Small geometric UI marks, painted at the same weight as the popup text."""
    result = QPixmap(size * 2, size * 2); result.setDevicePixelRatio(2)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24, size / 24)
    painter.setPen(QPen(QColor("#168bd2"), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == "person":
        painter.drawEllipse(QRectF(8.5, 4, 7, 7))
        path = QPainterPath(); path.moveTo(5, 20); path.cubicTo(5, 10, 19, 10, 19, 20)
    else:
        path = QPainterPath(); path.moveTo(5, 12); path.lineTo(10, 17); path.lineTo(20, 7)
    painter.drawPath(path); painter.end()
    return result


def avatar_pixmap(user, cache, size=24):
    result = QPixmap(size * 2, size * 2)
    result.setDevicePixelRatio(2)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    circle = QPainterPath()
    circle.addEllipse(QRectF(0, 0, size, size))
    painter.setClipPath(circle)
    photo = cache.get(user.get("avatar", ""))
    if photo and not photo.isNull():
        painter.drawPixmap(0, 0, size, size, photo)
    else:
        painter.fillRect(0, 0, size, size, QColor("#e7f1f4"))
        painter.setPen(QColor("#226274"))
        font = painter.font(); font.setPixelSize(12); font.setBold(True); painter.setFont(font)
        painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, user.get("name", "")[:1])
    painter.end()
    return result


class PersonDelegate(QStyledItemDelegate):
    def __init__(self, popup):
        super().__init__(popup)
        self.popup = popup

    def paint(self, painter, option, index):
        data = index.data(ROLE)
        painter.save()
        rect = option.rect.adjusted(3, 1, -3, -1)
        if data["kind"] == "heading":
            painter.setPen(QColor("#566875"))
            font = option.font; font.setPointSize(9); font.setBold(True); painter.setFont(font)
            painter.drawText(rect.adjusted(10, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, index.data())
        else:
            selected = data.get("id") == (self.popup.owner.value() or {}).get("id")
            active = bool(option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver))
            if active or selected:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#edf3f5" if active else "#f4f6f8"))
                painter.drawRoundedRect(rect, 6, 6)
            x, y = rect.x() + 10, rect.center().y() - 12
            if data["kind"] == "person":
                painter.drawPixmap(x, y, avatar_pixmap(data, self.popup.owner.avatars))
            else:
                painter.drawPixmap(x, y, marker_pixmap("person"))
            painter.setPen(QColor("#253440")); painter.setFont(option.font)
            info = (department_paths(data) or [()])[0]
            department = info[-1] if info else ""
            width = min(130, rect.width() // 3) if department else 0
            name_rect = rect.adjusted(44, 0, -width - 28, 0)
            painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter,
                             option.fontMetrics.elidedText(data["name"], Qt.TextElideMode.ElideRight, name_rect.width()))
            if department:
                painter.setPen(QColor("#566875"))
                painter.drawText(rect.adjusted(rect.width() - width - 26, 0, -26, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                    option.fontMetrics.elidedText(department, Qt.TextElideMode.ElideRight, width))
            if selected:
                painter.drawPixmap(rect.right() - 19, rect.center().y() - 8, marker_pixmap("check", 16))
            if active and option.state & QStyle.StateFlag.State_HasFocus:
                painter.setPen(QPen(QColor("#147788"), 1)); painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 5, 5)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(300, 30 if index.data(ROLE)["kind"] == "heading" else 40)


class AssigneePopup(QFrame):
    def __init__(self, owner):
        super().__init__(owner, Qt.WindowType.Popup)
        self.owner = owner
        self.mode, self.path, self.group_id = "all", (), None
        self.setObjectName("assigneePopup")
        self.setAccessibleName("选择负责人")
        self.setStyleSheet("""
            QFrame#assigneePopup { background: white; border: 1px solid #bdcad1; border-radius: 8px; }
            QLineEdit { padding: 6px 9px; border-radius: 7px; }
            QPushButton { padding: 4px 8px; min-height: 20px; }
            QPushButton:focus { border: 2px solid #147788; padding: 3px 7px; }
            QPushButton[scopeTab="true"] { border: none; border-radius: 13px; background: transparent; color: #566875; }
            QPushButton[scopeTab="true"]:checked { background: #252525; color: white; }
            QPushButton[scopeTab="true"]:focus { border: 2px solid #147788; }
            QPushButton[scopeChoice="true"]:checked { background: #e7f1f4; border-color: #147788; color: #183c4a; }
            QFrame#scopeTabs { border: 1px solid #d8dfe3; border-radius: 16px; background: white; }
            QListWidget { border: none; outline: none; background: white; }
            QListWidget::item { padding: 0; border: none; }
            QScrollArea { border: none; background: white; }
            QScrollArea > QWidget > QWidget { background: white; }
        """)
        layout = QVBoxLayout(self); layout.setContentsMargins(12, 12, 12, 10); layout.setSpacing(9)
        self.search = QLineEdit(); self.search.setPlaceholderText("搜索用户…"); self.search.setAccessibleName("搜索负责人")
        self.search.setClearButtonEnabled(True)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)
        tabs = QFrame(); tabs.setObjectName("scopeTabs")
        tabs.setFixedHeight(36)
        tabs_layout = QHBoxLayout(tabs); tabs_layout.setContentsMargins(3, 3, 3, 3); tabs_layout.setSpacing(2)
        self.tabs = QButtonGroup(self)
        for mode, title in [("all", "全部"), ("department", "按部门"), ("group", "按分组")]:
            button = QPushButton(title); button.setAutoDefault(False); button.setCheckable(True)
            button.setProperty("scopeTab", True)
            button.clicked.connect(lambda _, value=mode: self.set_mode(value))
            self.tabs.addButton(button); tabs_layout.addWidget(button)
        self.tabs.buttons()[0].setChecked(True)
        layout.addWidget(tabs)
        self.scope_scroll = QScrollArea(); self.scope_scroll.setWidgetResizable(True)
        self.scope_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scope_scroll.setMaximumHeight(150)
        self.scope_widget = QWidget(); self.scope_layout = QVBoxLayout(self.scope_widget)
        self.scope_layout.setContentsMargins(2, 0, 2, 0); self.scope_layout.setSpacing(4)
        self.scope_scroll.setWidget(self.scope_widget); layout.addWidget(self.scope_scroll)
        self.list = QListWidget(); self.list.setAccessibleName("可选负责人")
        self.list.setMouseTracking(True); self.list.setItemDelegate(PersonDelegate(self))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(self.choose); self.list.itemActivated.connect(self.choose)
        self.list.installEventFilter(self)
        self.empty = QLabel(); self.empty.setWordWrap(True); self.empty.setObjectName("muted")
        self.empty.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.empty)
        layout.addWidget(self.list, 1)
        self.scope_label = QLabel(owner.directory["scope"]); self.scope_label.setObjectName("muted")
        self.scope_label.setTextFormat(Qt.TextFormat.PlainText); self.scope_label.setWordWrap(True)
        layout.addWidget(self.scope_label)
        self.search.textChanged.connect(self.refresh)
        self.owner.avatars.changed.connect(self.list.viewport().update)
        self.refresh_scope(); self.refresh()

    def set_mode(self, mode):
        self.mode, self.path = mode, ()
        self.tabs.buttons()[["all", "department", "group"].index(mode)].setChecked(True)
        self.group_id = self.owner.directory["groups"][0]["id"] if self.owner.directory["groups"] else None
        self.refresh_scope(); self.refresh()

    def navigate(self, path):
        self.path = path; self.refresh_scope(); self.refresh()

    def select_group(self, identifier):
        self.group_id = identifier; self.refresh_scope(); self.refresh()

    def scope_button(self, title, callback, checked=False):
        button = QPushButton(title); button.setAutoDefault(False)
        button.setProperty("scopeChoice", True)
        button.setMinimumWidth(0); button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        button.setAccessibleName(title)
        button.setCheckable(True); button.setChecked(checked); button.clicked.connect(callback)
        self.scope_layout.addWidget(button)
        button.setFixedHeight(32)

    def refresh_scope(self):
        while self.scope_layout.count():
            self.scope_layout.takeAt(0).widget().deleteLater()
        self.scope_scroll.setVisible(self.mode != "all")
        if self.mode == "department":
            if self.path:
                crumb = QLabel(" / ".join(self.path)); crumb.setWordWrap(True); crumb.setTextFormat(Qt.TextFormat.PlainText)
                self.scope_layout.addWidget(crumb)
                self.scope_button("返回上一级部门", lambda: self.navigate(self.path[:-1]))
            for path, ids in child_departments(self.owner.directory["users"], self.path):
                self.scope_button(f"{path[-1]}    {len(ids)} 人", lambda _, p=path: self.navigate(p))
            if not self.scope_layout.count():
                self.scope_layout.addWidget(QLabel("暂无部门数据"))
        elif self.mode == "group":
            if not self.owner.directory["project_selected"]:
                label = QLabel("请先在创建任务页选择项目，以查看成员分组。"); label.setWordWrap(True)
                self.scope_layout.addWidget(label)
            else:
                for group in self.owner.directory["groups"]:
                    self.scope_button(group["name"], lambda _, i=group["id"]: self.select_group(i), self.group_id == group["id"])
                self.scope_button("未分组", lambda: self.select_group(None), self.group_id is None)
        height = 0
        for i in range(self.scope_layout.count()):
            widget = self.scope_layout.itemAt(i).widget()
            widget.ensurePolished()
            height += max(28, widget.heightForWidth(310) if widget.hasHeightForWidth() else widget.sizeHint().height()) + 4
        self.scope_widget.setMinimumHeight(height)
        self.scope_scroll.setFixedHeight(min(150, max(38, height + 4)))

    def heading(self, title, count):
        item = QListWidgetItem(f"{title}  {count}"); item.setData(ROLE, {"kind": "heading"})
        item.setFlags(Qt.ItemFlag.NoItemFlags); self.list.addItem(item)

    def person(self, user):
        data = {**user, "kind": "person"} if user else {"kind": "none", "id": None, "name": "无负责人"}
        item = QListWidgetItem(data["name"] + ("，" + " / ".join(data.get("departmentNames", [])) if data.get("departmentNames") else ""))
        item.setData(ROLE, data); self.list.addItem(item)

    def refresh(self):
        self.list.clear()
        directory, query = self.owner.directory, self.search.text()
        users = scoped_users(directory["users"], directory["groups"], self.mode, self.path, self.group_id, query)
        if self.mode == "group" and not directory["project_selected"]:
            users = []
        if self.mode == "all":
            if not query.strip(): self.person(None)
            current = [u for u in users if u["id"] == (self.owner.value() or {}).get("id")]
            recent = [u for identifier in self.owner.history() for u in users if u["id"] == identifier and u not in current]
            for title, rows in [("当前", current), ("常用", recent), ("全部", users)]:
                if rows:
                    self.heading(title, len(rows))
                    for user in rows: self.person(user)
        else:
            for user in users: self.person(user)
        self.empty.setText("未找到匹配的用户" if query.strip() else "此范围暂无可选成员")
        self.empty.setVisible(not users)
        self.move_selection(1, first=True)
        selected_id = (self.owner.value() or {}).get("id")
        for index in range(self.list.count()):
            data = self.list.item(index).data(ROLE)
            if data["kind"] != "heading" and data.get("id") == selected_id:
                self.list.setCurrentRow(index)
                break

    def move_selection(self, direction, first=False):
        rows = [i for i in range(self.list.count()) if self.list.item(i).data(ROLE)["kind"] != "heading"]
        if rows:
            position = rows.index(self.list.currentRow()) if self.list.currentRow() in rows else -1
            self.list.setCurrentRow(rows[0] if first else rows[(position + direction) % len(rows)])

    def choose(self, item):
        if not item or item.data(ROLE)["kind"] == "heading": return
        data = item.data(ROLE)
        self.owner.set_value({"id": data["id"], "name": data["name"]} if data["id"] else None)
        self.owner.remember(data["id"])
        self.owner.changed.emit()
        self.close()
        self.owner.setFocus()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self.move_selection(1 if event.key() == Qt.Key.Key_Down else -1); return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.choose(self.list.currentItem()); return True
            if event.key() == Qt.Key.Key_Escape:
                self.close(); self.owner.setFocus(); return True
        return super().eventFilter(obj, event)


class AssigneePicker(QPushButton):
    changed = Signal()

    def __init__(self, directory, parent=None):
        super().__init__("无负责人", parent)
        self.data_directory = Path(directory)
        self.directory = {"users": [], "groups": [], "scope": "尚未连接 DAPD", "history_key": "", "project_selected": False}
        self.selected, self.popup = None, None
        self.setAutoDefault(False); self.setIconSize(QSize(24, 24))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("QPushButton { text-align: left; }")
        self.avatars = AvatarCache(self)
        self.avatars.changed.connect(self.refresh_label)
        self.clicked.connect(self.open_popup)

    def set_directory(self, directory):
        self.directory = directory
        self.refresh_label()

    def value(self):
        return dict(self.selected) if self.selected else None

    def set_value(self, value):
        self.selected = {"id": str(value["id"]), "name": value["name"]} if value else None
        self.refresh_label()

    def refresh_label(self):
        user = next((u for u in self.directory["users"] if u["id"] == (self.selected or {}).get("id")), self.selected)
        self.setText(user["name"] if user else "无负责人")
        if user:
            self.setIcon(QIcon(avatar_pixmap(user, self.avatars)))
        else:
            self.setIcon(QIcon(marker_pixmap("person")))

    def history_path(self):
        key = self.directory["history_key"]
        return self.data_directory / "assignee-history" / (hashlib.sha256(key.encode()).hexdigest() + ".json") if key else None

    def history(self):
        path = self.history_path()
        if path and path.exists():
            try:
                values = json.loads(path.read_text(encoding="utf-8"))
                return [v for v in values if isinstance(v, str)][:10] if isinstance(values, list) else []
            except (OSError, ValueError):
                pass
        return []

    def remember(self, identifier):
        path = self.history_path()
        if path and identifier:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                values = [identifier, *(v for v in self.history() if v != identifier)][:10]
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(values), encoding="utf-8"); temporary.replace(path)
            except OSError:
                pass  # Selection remains usable when the local history cannot be saved.

    def open_popup(self):
        if self.popup:
            self.popup.close(); self.popup.deleteLater()
        self.popup = AssigneePopup(self)
        screen = self.screen().availableGeometry()
        width, height = min(360, screen.width() - 16), min(520, screen.height() - 24)
        self.popup.resize(width, height)
        point = self.mapToGlobal(QPoint(0, self.height() + 4))
        if point.y() + height > screen.bottom(): point.setY(self.mapToGlobal(QPoint(0, 0)).y() - height - 4)
        point.setX(max(screen.left() + 8, min(point.x(), screen.right() - width - 8)))
        point.setY(max(screen.top() + 8, point.y()))
        self.popup.move(point); self.popup.show(); self.popup.search.setFocus()
