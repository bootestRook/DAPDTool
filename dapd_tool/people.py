"""DAPD member directory, department scopes and name/pinyin search."""
from functools import lru_cache
from pypinyin import Style, lazy_pinyin


def load_people(api, project=None):
    account = api.request("GET", "userSetting.getSettings", {})["userId"]
    if project:
        users = [m["user"] for m in api.request("GET", "project.getProjectMembers", project["id"])]
        groups = api.request("GET", "project.listProjectMemberGroups", {"projectId": project["id"]})
    else:
        users = api.request("GET", "user.getAll", {})
        groups = []
    return {"users": [u for u in users if u.get("status") != "removed"], "groups": groups,
            "history_key": str(account) + ":" + (project["id"] if project else "global"),
            "scope": project["name"] if project else "全部用户",
            "project_selected": bool(project)}


def department_paths(user):
    # DAPD flattens multiple department paths, repeating the organization root.
    names = [n.strip() for n in user.get("departmentNames", []) if isinstance(n, str) and n.strip()]
    if not names:
        return []
    starts = [i for i, n in enumerate(names) if n == names[0]] + [len(names)]
    return list(dict.fromkeys(tuple(names[a:b]) for a, b in zip(starts, starts[1:])))


@lru_cache(maxsize=8192)
def search_forms(text):
    return (text.casefold(), "".join(lazy_pinyin(text)).casefold(),
            "".join(lazy_pinyin(text, style=Style.FIRST_LETTER)).casefold())


def matches(user, query, groups):
    terms = query.casefold().strip().replace("ü", "v").split()
    fields = [user["name"], *user.get("departmentNames", []),
              *(g["name"] for g in groups if user["id"] in g["userIds"])]
    forms = [f for value in fields for f in search_forms(value)]
    return all(any(term in form for form in forms) for term in terms)


def scoped_users(users, groups, mode, path=(), group_id=None, query=""):
    grouped = {i for g in groups for i in g["userIds"]}
    selected = next((set(g["userIds"]) for g in groups if g["id"] == group_id), set())
    def in_scope(user):
        if mode == "department":
            return any(p[:len(path)] == tuple(path) for p in department_paths(user))
        if mode == "group":
            return user["id"] not in grouped if group_id is None else user["id"] in selected
        return True
    return [u for u in users if in_scope(u) and matches(u, query, groups)]


def child_departments(users, path):
    children = {}
    for user in users:
        for parts in department_paths(user):
            if parts[:len(path)] == tuple(path) and len(parts) > len(path):
                children.setdefault(parts[:len(path) + 1], set()).add(user["id"])
    return sorted(children.items(), key=lambda item: search_forms(item[0][-1])[1])
