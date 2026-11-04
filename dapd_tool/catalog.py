"""Resolve DAPD's copied group text to an explicit project and group."""
import re
from urllib.parse import parse_qs, urlsplit

UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"


def project_id_from_text(text):
    matches=set()
    for url in re.findall(r"https://dapd\.dodjoy\.com/groups/\?[^\s（）)]+",text):
        values=parse_qs(urlsplit(url).query).get("projectId",[])
        matches.update(v.lower() for v in values if re.fullmatch(UUID,v))
    if len(matches)!=1:
        raise ValueError("请粘贴一个 DAPD 项目链接，支持包含项目名称的整段文字。")
    return matches.pop()


def task_id_from_text(text):
    text = text.strip()
    if re.fullmatch(UUID, text):
        return text.lower()
    matches = {value.lower() for value in re.findall(r"https://dapd\.dodjoy\.com/task/(" + UUID + r")(?=[?/#\s）)]|$)", text)}
    if len(matches) == 1:
        return matches.pop()
    if len(matches) > 1 or "http://" in text or "https://" in text:
        raise ValueError("请粘贴一个 DAPD 任务链接，支持包含任务标题的整段文字。")
    return None


def group_id_from_text(text):
    pattern = r"https://dapd\.dodjoy\.com/groups/(" + UUID + r")(?=[?/#\s）)]|$)"
    matches = {value.lower() for value in re.findall(pattern, text)}
    if len(matches) != 1:
        raise ValueError("请粘贴一个 DAPD 任务组链接，支持包含任务组名称的整段文字。")
    return matches.pop()


def locate_group(api, identifier):
    projects = api.projects()
    for project in projects:
        groups = api.groups(project["id"])
        for group in groups:
            if group["id"] == identifier:
                if group.get("status") == "archived":
                    raise ValueError("这个任务组已经归档，请选择其他任务组。")
                return {"projects": projects, "project": project, "groups": groups, "group": group}
    raise ValueError("当前账号无法访问这个任务组，请检查链接和 API Key 的项目权限。")
