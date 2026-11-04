"""Explicit, separately named template instances."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QComboBox, QSpinBox, QPushButton, QHeaderView, QLabel


class BatchEditor(QWidget):
    changed = Signal()

    def __init__(self, default_template, parent=None):
        super().__init__(parent)
        self.default_template = default_template
        self.templates = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        add = QPushButton("+ 添加任务")
        add.clicked.connect(lambda: self.add_rows(1))
        row.addWidget(add)
        row.addStretch()
        row.addWidget(QLabel("数量"))
        self.quantity = QSpinBox()
        self.quantity.setRange(1, 5000)
        self.quantity.setValue(1)
        row.addWidget(self.quantity)
        generate = QPushButton("按数量添加")
        generate.clicked.connect(lambda: self.add_rows(self.quantity.value()))
        row.addWidget(generate)
        remove = QPushButton("删除所选行")
        remove.clicked.connect(self.remove_selected)
        row.addWidget(remove)
        layout.addLayout(row)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["主任务名称（每行单独填写）", "使用模板"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(lambda _: self.changed.emit())
        layout.addWidget(self.table)

    def set_templates(self, templates):
        self.templates = templates
        for row in range(self.table.rowCount()):
            self.fill_combo(self.table.cellWidget(row, 1))

    def fill_combo(self, combo, selected=None):
        previous = selected or combo.currentData()
        combo.clear()
        combo.addItem("请选择模板", None)
        for template in self.templates:
            combo.addItem(template["name"], template)
            if previous and template["id"] == previous["id"]:
                combo.setCurrentIndex(combo.count() - 1)

    def add_rows(self, count):
        first = self.table.rowCount()
        count = min(count, 5000 - first)
        for row in range(first, first + count):
            self.table.insertRow(row)
            combo = QComboBox()
            combo.setAccessibleName(f"第 {row + 1} 项模板")
            self.fill_combo(combo, self.default_template())
            combo.currentIndexChanged.connect(lambda _: self.changed.emit())
            self.table.setCellWidget(row, 1, combo)
            self.table.setItem(row, 0, QTableWidgetItem(""))
        if count:
            self.table.setCurrentCell(first, 0)
            self.table.editItem(self.table.item(first, 0))
        self.changed.emit()

    def remove_selected(self):
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)
        self.changed.emit()

    def entries(self):
        values = []
        for row in range(self.table.rowCount()):
            title = self.table.item(row, 0).text().strip()
            template = self.table.cellWidget(row, 1).currentData()
            if not title or not template:
                raise ValueError(f"第 {row + 1} 行需要填写名称并选择模板。")
            values.append((title, template))
        return values
