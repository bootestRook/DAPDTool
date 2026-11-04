from PySide6.QtWidgets import QTreeWidgetItem


def fill_plan(tree, plan):
    tree.clear()
    items = []
    for node in plan["nodes"]:
        item = QTreeWidgetItem([node["title"]])
        if node["parent"] is None:
            tree.addTopLevelItem(item)
        else:
            items[node["parent"]].addChild(item)
        items.append(item)
    tree.expandAll()
