"""Validated, deterministic template expansion."""
import copy
from .media import validate_content


MAX_TASKS = 5000


def title_text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("任务标题不能为空。")
    value = value.strip()
    if len(value) > 255 or "\n" in value or "\r" in value:
        raise ValueError("任务标题必须为一行，且不超过 255 字。")
    return value


def validate_template(nodes):
    if not isinstance(nodes, list) or len(nodes) > MAX_TASKS - 1:
        raise ValueError("模板结构无效或任务过多。")
    clean = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not {"title", "parent"}.issubset(node) or set(node) - {"title", "parent", "content"}:
            raise ValueError("模板节点必须包含标题与父节点。")
        parent = node["parent"]
        if parent is not None and (type(parent) is not int or not 0 <= parent < index):
            raise ValueError("模板父节点必须位于子节点之前，且不能循环引用。")
        clean.append({"title": title_text(node["title"]), "parent": parent})
        if "content" in node:
            clean[-1]["content"] = validate_content(node["content"])
    return clean


def make_plan(titles, nodes, destination, root=None):
    nodes = validate_template(nodes)
    titles = [title_text(t) for t in titles]
    if not titles:
        raise ValueError("请至少输入一个主任务标题。")
    if len(titles) != len(set(titles)):
        raise ValueError("主任务标题有重复，请检查后再预览。")
    if len(titles) * (len(nodes) + 1) > MAX_TASKS:
        raise ValueError(f"一次最多创建 {MAX_TASKS} 个任务，请分批提交。")
    if not destination.get("projectId") or not destination.get("taskGroupId"):
        raise ValueError("请选择项目和任务组。")
    plan = []
    root_content = validate_content(root)
    for title in titles:
        root_index = len(plan)
        plan.append({"title": title, "parent": None, "content": copy.deepcopy(root_content)})
        for node in nodes:
            plan.append({"title": node["title"], "parent": root_index if node["parent"] is None else root_index + 1 + node["parent"], "content": validate_content(node.get("content"))})
    return {"destination": copy.deepcopy(destination), "nodes": plan}


def creation_order(plan):
    """Reverse siblings for DAPD's front insertion, keeping parents first."""
    children = {}
    for index, node in enumerate(plan["nodes"]):
        children.setdefault(node["parent"], []).append(index)
    pending = list(children.get(None, []))
    while pending:
        index = pending.pop()
        yield index
        pending.extend(children.get(index, []))


def node_payload(plan, index, ids):
    node = plan["nodes"][index]
    dest = plan["destination"]
    payload = {"title": node["title"], "projectId": dest["projectId"], "taskGroupId": dest["taskGroupId"]}
    parent = dest.get("parentTaskId") if node["parent"] is None else ids.get(node["parent"])
    if node["parent"] is not None and not parent:
        raise ValueError("父任务尚未创建成功，不能创建子任务。")
    if parent:
        payload["parentTaskId"] = parent
    assignee = node.get("content", {}).get("assignee")
    if assignee:
        payload["assigneeId"] = assignee["id"]
    return payload


def make_batch_plan(entries, destination):
    """Combine independently named template instances without losing parent indices."""
    nodes = []
    for title, template in entries:
        plan = make_plan([title], template["nodes"], destination, template["root"])
        offset = len(nodes)
        for node in plan["nodes"]:
            if node["parent"] is not None:
                node["parent"] += offset
            nodes.append(node)
    if not nodes or len(nodes) > MAX_TASKS:
        raise ValueError(f"请添加任务，每批最多 {MAX_TASKS} 个节点。")
    titles = [n["title"] for n in nodes if n["parent"] is None]
    if len(titles) != len(set(titles)):
        raise ValueError("主任务标题有重复，请分别命名。")
    return {"destination": copy.deepcopy(destination), "nodes": nodes}
