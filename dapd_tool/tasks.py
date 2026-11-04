"""Read the authenticated user's tasks and apply explicit, conflict-checked edits."""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from dapd_api import DapdError
from . import media_api
from .media import Assets, description_html, description_assets
from .people import load_people

EDIT_FIELDS = {"title", "description", "status", "priority", "assigneeId", "taskGroupId", "parentTaskId", "dueDate", "tags", "copiedUserIds", "relatedTaskIds", "fieldValues"}


def current_user(api):
    identifier = api.request("GET", "userSetting.getSettings", {})["userId"]
    return api.request("GET", "user.getById", {"id": identifier})


def list_created_tasks(api, progress=lambda _: None):
    user = current_user(api)
    tasks, seen, offset = [], set(), 0
    while True:
        page = api.request("GET", "task.getTasks", {"createdById": user["id"], "onlyRootTasks": False, "limit": 100, "offset": offset})
        if not isinstance(page, list) or any(t.get("createdById") != user["id"] for t in page):
            raise ValueError("DAPD 返回了不符合创建者筛选的任务，已停止加载。")
        fresh = [t for t in page if t["id"] not in seen]
        if page and not fresh:
            raise ValueError("DAPD 分页未前进，请稍后重新加载。")
        tasks.extend(fresh)
        seen.update(t["id"] for t in fresh)
        progress(len(tasks))
        if len(page) < 100:
            break
        offset += len(page)
    own_ids = set(seen)
    pending = [t.get("parentTaskId") for t in tasks if t.get("parentTaskId") not in seen]
    while pending:
        identifier = pending.pop()
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        task = media_api.raw_task(api, identifier)
        task["contextOnly"] = True
        tasks.append(task)
        pending.append(task.get("parentTaskId"))
    groups, statuses = {}, {}
    for project in {t["projectId"] for t in tasks}:
        groups.update({g["id"]: g["name"] for g in api.groups(project)})
        statuses[project] = {s["key"]: s["name"] for s in api.request("GET", "taskStatusConfig.listByProject", {"projectId": project})}
    return {"user": user, "tasks": tasks, "own_ids": own_ids, "groups": groups, "statuses": statuses}


def edit_context(api, identifier):
    task = media_api.raw_task(api, identifier)
    user = current_user(api)
    if task["createdById"] != user["id"]:
        raise ValueError("只能修改当前 API Key 用户创建的任务。")
    project = task["projectId"]
    people = load_people(api, {"id": project, "name": (task.get("project") or {}).get("name") or project})
    return {"task": task, "members": people["users"], "people": people, "groups": api.groups(project),
            "statuses": api.request("GET", "taskStatusConfig.listByProject", {"projectId": project}),
            "tags": api.request("GET", "tag.getTags", {"projectId": project}),
            "fields": api.request("GET", "taskFieldConfig.listByProject", {"projectId": project})}


def task_values(task):
    values = {k: copy.deepcopy(task.get(k)) for k in EDIT_FIELDS}
    values["tags"] = [t["id"] if isinstance(t, dict) else t for t in task.get("tags", [])]
    values["copiedUserIds"] = [u["id"] for u in task.get("copiedUsers", [])]
    values["relatedTaskIds"] = [t["id"] for t in task.get("relatedTasks", [])]
    return values


def equivalent(key, left, right):
    if key == "dueDate" and left and right:
        return datetime.fromisoformat(left.replace("Z", "+00:00")).astimezone(timezone.utc) == datetime.fromisoformat(right.replace("Z", "+00:00")).astimezone(timezone.utc)
    if key in ("tags", "copiedUserIds", "relatedTaskIds"):
        return set(left or []) == set(right or [])
    if key == "fieldValues":
        return {v["fieldId"]: v["value"] for v in left or []} == {v["fieldId"]: v["value"] for v in right or []}
    return left == right


def save_task(store, api, original, changes, content):
    if set(changes) - EDIT_FIELDS:
        raise ValueError("包含不支持的任务字段。")
    identifier = original["id"]
    latest = media_api.raw_task(api, identifier)
    if latest["createdById"] != current_user(api)["id"]:
        raise ValueError("只能修改自己创建的任务。")
    before, now = task_values(original), task_values(latest)
    if any(not equivalent(k, before[k], now[k]) for k in changes):
        raise ValueError("任务已在 DAPD 中被修改，请重新加载后再编辑，避免覆盖他人的更新。")
    if "title" in changes and not changes["title"].strip():
        raise ValueError("任务标题不能为空。")
    if changes.get("assigneeId") and changes["assigneeId"] not in {m["id"] for m in api.members(original["projectId"])}:
        raise ValueError("负责人不在当前项目中，请重新选择。")
    if changes.get("dueDate"):
        datetime.fromisoformat(changes["dueDate"])
    if "taskGroupId" in changes or "parentTaskId" in changes:
        group = changes.get("taskGroupId", latest["taskGroupId"])
        if group not in {g["id"] for g in api.groups(latest["projectId"]) if g.get("status") != "archived"}:
            raise ValueError("请选择当前项目内可用的任务组。")
        parent = changes.get("parentTaskId", latest.get("parentTaskId"))
        ancestors = {identifier}
        while parent:
            if parent in ancestors:
                raise ValueError("父任务设置会产生循环，请重新选择。")
            ancestors.add(parent)
            node = media_api.raw_task(api, parent)
            if node["projectId"] != latest["projectId"] or node["taskGroupId"] != group:
                raise ValueError("父任务必须属于相同项目与任务组。")
            parent = node.get("parentTaskId")
    uploaded_attachments = []
    if "description" in changes or content["attachments"]:
        directory = Path(store.directory) / "task-edit-uploads"
        directory.mkdir(exist_ok=True)
        # Names are stable per task + asset. Receipts survive closing the dialog.
        receipt = directory / (identifier + ".json")
        uploads = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
        def persist():
            temporary = receipt.with_suffix(".tmp")
            temporary.write_text(json.dumps(uploads), encoding="utf-8")
            temporary.replace(receipt)
        urls = {}
        files = [("description", a) for a in description_assets(content).values()] if "description" in changes else []
        files += [("attachment", a) for a in content["attachments"]]
        for kind, asset in files:
            name = "edit-" + identifier + "-" + kind + "-" + asset["sha256"][:16] + Path(asset["file"]).suffix
            key = kind + ":" + asset["id"]
            record = uploads.get(key)
            if record and record.get("url"):
                if kind == "description":
                    urls[asset["id"]] = record["url"]
                else:
                    uploaded_attachments.append(record)
                continue
            if record:
                found = media_api.reconcile(api, latest["projectId"], identifier, kind, name)
                if not found:
                    raise ValueError("描述文件上传结果待核对，请先在 DAPD 项目文件中核对；确认不存在后使用“重置待核对上传”。")
                uploads[key] = found
            else:
                path = Assets(store.directory).path(asset, verify_hash=True)
                uploads[key] = {"name": name, "unknown": True}
                persist()
                try:
                    uploads[key] = media_api.upload(api, path, asset, latest["projectId"], identifier, kind, name)
                except DapdError as exc:
                    if not exc.uncertain:
                        uploads.pop(key)
                        persist()
                    raise
            persist()
            if kind == "description":
                urls[asset["id"]] = uploads[key]["url"]
            else:
                uploaded_attachments.append(uploads[key])
        if "description" in changes:
            changes = {**changes, "description": description_html(content, urls)}
    if uploaded_attachments:
        latest = media_api.raw_task(api, identifier)
        if any(not media_api.attachment_present(latest, result) for result in uploaded_attachments):
            raise ValueError("附件已上传但尚未在任务中回读确认，请稍后核对。")
    if not changes:
        return latest
    try:
        api.request("POST", "task.updateTask", {"id": identifier, **changes, "updateSource": "manual"})
    except DapdError as exc:
        if not exc.uncertain:
            raise
        raise ValueError("更新请求结果待核对。请重新加载此任务，确认 DAPD 中的实际内容后再修改。") from exc
    result = media_api.raw_task(api, identifier)
    actual = task_values(result)
    if any(not equivalent(k, actual[k], v) for k, v in changes.items()):
        raise ValueError("DAPD 回读与提交内容不一致，请重新加载任务并核对。")
    return result


def reset_unknown_uploads(store, identifier):
    path = Path(store.directory) / "task-edit-uploads" / (identifier + ".json")
    if path.exists():
        records = json.loads(path.read_text(encoding="utf-8"))
        records = {k: v for k, v in records.items() if not v.get("unknown")}
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(records), encoding="utf-8")
        temporary.replace(path)
