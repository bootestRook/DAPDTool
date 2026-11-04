"""Documented DAPD file APIs; uploads only to the existing authenticated client."""
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from dapd_api import DapdError


def upload(api, path, asset, project, task, kind, filename):
    data = {"projectId":project, "source":kind}
    if task:
        data["taskId"] = task
    try:
        with Path(path).open("rb") as stream:
            response = api.http.post("/api/files/upload", data=data, files={"file":(filename, stream, asset["mime"])}, timeout=120)
    except httpx.RequestError as exc:
        raise DapdError("文件上传请求中断，结果需要核对。", uncertain=True) from exc
    if response.status_code >= 400:
        raise DapdError(f"DAPD 拒绝文件上传（HTTP {response.status_code}）。", uncertain=response.status_code >= 500)
    try:
        result = response.json()
        url = result.get("url") or result.get("downloadUrl")
        if not isinstance(url, str) or urlsplit(url).scheme != "https":
            raise ValueError()
        return {k: result[k] for k in ("id", "url", "downloadUrl", "pathname", "contentType") if k in result} | {"url":url}
    except (ValueError, TypeError, AttributeError) as exc:
        raise DapdError("文件上传未返回可确认的链接，请先核对。", uncertain=True) from exc


def raw_task(api, identifier):
    return api.request("GET", "task.getTaskById", {"id":identifier})


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def attachment_present(task, result):
    values = set(strings(task.get("attachments", [])))
    return bool(values.intersection(str(result[k]) for k in ("id", "url", "downloadUrl", "pathname") if result.get(k)))


def reconcile(api, project, task, kind, filename):
    if kind == "attachment":
        candidates = raw_task(api, task).get("attachments", [])
    else:
        candidates = api.request("GET", "file.getProjectFiles", {"projectId":project, "includeAllFolders":True})
    found = []
    for candidate in candidates:
        values = list(strings(candidate))
        if not any(v == filename or Path(unquote(urlsplit(v).path)).name == filename for v in values):
            continue
        urls = [v for v in values if v.startswith("https://") and Path(unquote(urlsplit(v).path)).name == filename]
        if urls:
            found.append({"url":urls[0], "id":candidate.get("id")})
    if len(found) == 1:
        return found[0]
    return None
