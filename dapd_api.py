"""DAPD API client; callers supply credentials from their own secure storage."""
import json
from datetime import datetime, time, timezone, timedelta
from pathlib import Path

import httpx

BASE_URL = "https://dapd.dodjoy.com"
CHINA_TIME = timezone(timedelta(hours=8))


class DapdError(RuntimeError):
    def __init__(self, message, *, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


def task_summary(task):
    fields = ("id", "title", "projectId", "taskGroupId", "parentTaskId", "assigneeId", "status", "dueDate", "priority")
    return {key: task[key] for key in fields if key in task}


class DapdClient:
    def __init__(self, key, *, transport=None):
        if not isinstance(key, str) or not key.strip():
            raise ValueError("请先配置 DAPD API Key。")
        self.key = key
        self.http = httpx.Client(base_url=BASE_URL, headers={"Authorization": "Bearer " + self.key},
                                 timeout=25, follow_redirects=False, transport=transport)

    def close(self):
        self.http.close()

    def request(self, method, procedure, payload):
        write = method == "POST"
        try:
            response = self.http.request(method, "/trpc/" + procedure,
                **({"json": payload} if write else {"params": {"input": json.dumps(payload, ensure_ascii=False)}}))
        except httpx.TimeoutException as exc:
            raise DapdError("DAPD 请求超时，请检查网络后重试。", uncertain=write) from exc
        except httpx.RequestError as exc:
            raise DapdError("DAPD 网络请求失败。", uncertain=write) from exc
        if response.status_code >= 400:
            if response.status_code in (401, 403):
                message = "DAPD Key 无效或当前账号没有操作权限。"
            else:
                message = f"DAPD 拒绝请求（HTTP {response.status_code}）。"
            raise DapdError(message, uncertain=write and response.status_code >= 500)
        try:
            body = response.json()
            return body["result"]["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise DapdError("DAPD 返回了无法确认的结果。", uncertain=write) from exc

    def projects(self):
        return [{k: p[k] for k in ("id", "name")}
                for p in self.request("GET", "project.getProjects", {}) if not p.get("isArchived")]

    def groups(self, projectId, *, checkpoint=lambda: None):
        groups, seen = [], set()
        offset = 0
        while True:
            checkpoint()
            page = self.request("GET", "taskGroup.getTaskGroups", {"projectId": projectId, "limit": 100, "offset": offset})
            checkpoint()
            if not isinstance(page, list) or any(not isinstance(g, dict) or not g.get("id") for g in page):
                raise ValueError("DAPD 返回了无效的任务组列表，请重新读取。")
            identifiers = [g["id"] for g in page]
            if len(set(identifiers)) != len(identifiers) or seen.intersection(identifiers):
                raise ValueError("DAPD 任务组分页重复，已停止读取，请稍后重试。")
            seen.update(identifiers)
            groups.extend({k: g[k] for k in ("id", "name", "status") if k in g} for g in page)
            if len(page) < 100:
                return groups
            offset += len(page)

    def members(self, projectId):
        members = self.request("GET", "project.getProjectMembers", projectId)
        return [{"id": str(m["user"]["id"]), "name": m["user"]["name"]} for m in members]

    def task(self, id):
        task = self.request("GET", "task.getTaskById", {"id": id})
        if not isinstance(task, dict) or not task.get("id"):
            raise ValueError("没有找到该 DAPD 任务。")
        return task_summary(task)

    def search(self, projectId, query):
        if not query.strip():
            raise ValueError("请提供任务搜索词。")
        data = self.request("GET", "task.searchTasks", {"projectId": projectId, "query": query})
        tasks = data["tasks"]
        return {"tasks": [task_summary(t) for t in tasks[:50]], "truncated": len(tasks) > 50}

    def validate_task(self, payload):
        allowed = {"title", "description", "projectId", "taskGroupId", "parentTaskId", "assigneeId", "dueDate", "priority"}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise ValueError("不支持的任务字段。")
        payload = dict(payload)
        for field in ("title", "projectId", "taskGroupId"):
            if not isinstance(payload.get(field), str) or not payload[field].strip():
                raise ValueError("缺少任务标题、项目或任务组。")
        if len(payload["title"]) > 255:
            raise ValueError("任务标题不能超过 255 字。")
        if payload["projectId"] not in {p["id"] for p in self.projects()}:
            raise ValueError("项目不存在或不可访问，请重新查询项目。")
        group = next((g for g in self.groups(payload["projectId"]) if g["id"] == payload["taskGroupId"]), None)
        if not group or group.get("status") == "archived":
            raise ValueError("任务组不属于该项目或已经归档，请重新选择。")
        if payload.get("parentTaskId"):
            parent = self.task(payload["parentTaskId"])
            if (parent.get("projectId"), parent.get("taskGroupId")) != (payload["projectId"], payload["taskGroupId"]):
                raise ValueError("子任务必须使用父任务的项目和任务组。")
        if payload.get("assigneeId"):
            members = self.members(payload["projectId"])
            if payload["assigneeId"] not in {m["id"] for m in members}:
                raise ValueError("负责人不是该项目的成员，请重新查询成员。")
        if "priority" in payload and payload["priority"] not in {"low", "medium", "high", "urgent"}:
            raise ValueError("无法识别任务优先级。")
        if payload.get("dueDate"):
            try:
                due = datetime.fromisoformat(payload["dueDate"])
                if len(payload["dueDate"]) == 10:
                    due = datetime.combine(due.date(), time(23, 59, 59))
                if due.tzinfo is None:
                    due = due.replace(tzinfo=CHINA_TIME)
                payload["dueDate"] = due.isoformat()
            except (ValueError, TypeError) as exc:
                raise ValueError("截止时间需要使用 ISO 日期或时间格式。") from exc
        return payload

    def create(self, payload):
        task = self.request("POST", "task.createTask", payload)
        if not isinstance(task, dict) or not task.get("id"):
            raise DapdError("DAPD 创建请求未返回任务 ID。", uncertain=True)
        return task_summary(task)


def with_api(key, operation):
    api = DapdClient(key)
    try:
        return operation(api)
    finally:
        api.close()

def task_url(identifier):
    return BASE_URL + "/task/" + identifier
