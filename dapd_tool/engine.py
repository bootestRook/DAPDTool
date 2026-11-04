"""Sequential API writes, durable receipts and explicit uncertain-result recovery."""
from dapd_api import DapdError
from .model import node_payload
from .media import Assets, description_html, empty_content, image_assets, upload_name
from . import media_api
import json


class Paused(Exception):
    pass


class UploadUnknown(ValueError):
    pass


def ensure_upload(store, api, job, index, kind, asset, project, task, stop):
    name = upload_name(job, index, kind, asset)
    row = store.upload_record(job,index,kind,asset["id"])
    if row and row["status"] == "uploaded":
        return json.loads(row["result"])
    if row and row["status"] in ("started", "unknown"):
        result = media_api.reconcile(api, project, task, kind, name)
        if result:
            store.set_upload(job,index,kind,asset["id"],name,"uploaded",result)
            return result
        raise UploadUnknown(f"文件上传结果待核对：{name}。请到 DAPD 核对后处理该记录。")
    if stop.is_set():
        raise Paused()
    path = Assets(store.directory).path(asset, verify_hash=True)
    store.set_upload(job,index,kind,asset["id"],name,"started")
    try:
        result = media_api.upload(api,path,asset,project,task,kind,name)
    except Exception as exc:
        unknown = not isinstance(exc,DapdError) or exc.uncertain
        store.set_upload(job,index,kind,asset["id"],name,"unknown" if unknown else "failed",error=safe_error(exc))
        if unknown:
            raise UploadUnknown(f"文件上传结果待核对：{name}。请先核对，不要重复上传。") from exc
        raise
    store.set_upload(job,index,kind,asset["id"],name,"uploaded",result)
    return result


def verify(task, payload):
    for key in ("title", "projectId", "taskGroupId", "parentTaskId"):
        if (task.get(key) or None) != (payload.get(key) or None):
            raise ValueError("DAPD 任务回读与预览不一致，请核对标题、项目、任务组和父任务。")
    if payload.get("description") and task.get("description") != payload["description"]:
        raise ValueError("DAPD 描述回读与模板内容不一致，请先核对任务。")


def task_for_verification(api, identifier, payload):
    return media_api.raw_task(api,identifier) if payload.get("description") else api.task(identifier)


def safe_error(exc):
    if isinstance(exc, (DapdError, ValueError)):
        return str(exc)
    return "操作未完成，请检查本地存储或网络后重试。"


def run_job(store, api, identifier, stop, progress=lambda _: None):
    job = store.job(identifier)
    if job["status"] == "completed":
        return job
    plan = job["plan"]
    ids = {n["position"]: n["task_id"] for n in job["nodes"] if n["status"] == "created"}
    store.set_job(identifier, "running")
    try:
        for row in job["nodes"]:
            index = row["position"]
            if row["status"] == "created":
                continue
            if stop.is_set():
                store.set_job(identifier, "paused")
                return store.job(identifier)
            if row["status"] in ("unknown", "started"):
                store.set_job(identifier, "blocked", "存在结果待核对的任务，请先处理后继续。")
                return store.job(identifier)
            payload = node_payload(plan, index, ids)
            content = plan["nodes"][index].get("content",empty_content())
            task_id = row["task_id"]
            if task_id:
                payload = json.loads(row["payload"]) if row["payload"] else payload
            else:
                # Validate the destination before uploading files into the project.
                api.validate_task(payload)
                urls = {}
                for asset in image_assets(content).values():
                    result = ensure_upload(store,api,identifier,index,"description",asset,payload["projectId"],None,stop)
                    urls[asset["id"]] = result["url"]
                description = description_html(content,urls)
                if description:
                    payload["description"] = description
                if stop.is_set():
                    raise Paused()
                store.set_node(identifier, index, "started", payload=payload)
                try:
                    result = api.create(payload)
                    task_id = result["id"]
                    store.set_node(identifier, index, "unverified", task_id=task_id)
                except Exception as exc:
                    unknown = not isinstance(exc, DapdError) or exc.uncertain
                    store.set_node(identifier, index, "unknown" if unknown else "failed", error=safe_error(exc))
                    store.set_job(identifier, "blocked" if unknown else "paused", safe_error(exc))
                    return store.job(identifier)
            # A known successful POST is never sent again, even if its media step failed.
            verify(task_for_verification(api,task_id,payload), payload)
            for asset in content["attachments"]:
                result = ensure_upload(store,api,identifier,index,"attachment",asset,payload["projectId"],task_id,stop)
                if not media_api.attachment_present(media_api.raw_task(api,task_id),result):
                    raise ValueError(f"附件已上传但尚未在任务中确认：{asset['name']}。继续时仅回读，不会重复上传。")
            store.set_node(identifier, index, "created")
            ids[index] = task_id
            progress(store.job(identifier))
        store.set_job(identifier, "completed")
    except Paused:
        store.set_job(identifier,"paused")
    except UploadUnknown as exc:
        store.set_node(identifier,index,"media_unknown",error=str(exc))
        store.set_job(identifier,"blocked",str(exc))
    except Exception as exc:
        store.set_job(identifier, "paused", safe_error(exc))
    return store.job(identifier)


def resolve_unknown(store, api, identifier, index, task_id):
    job = store.job(identifier)
    row = job["nodes"][index]
    if row["status"] != "unknown" or not row["payload"]:
        raise ValueError("所选任务不需要关联。")
    payload = json.loads(row["payload"])
    task = task_for_verification(api,task_id,payload)
    verify(task, payload)
    if any(n["task_id"] == task_id for n in job["nodes"]):
        raise ValueError("该任务已经关联到本批次中的其他记录。")
    store.set_node(identifier, index, "unverified", task_id=task_id)
    store.set_job(identifier, "paused")


def reset_absent(store, identifier, index):
    # The GUI requires explicit confirmation after the user has inspected DAPD.
    row = store.job(identifier)["nodes"][index]
    if row["status"] != "unknown" or row["task_id"]:
        raise ValueError("只有结果不明且尚未关联的任务可以重新提交。")
    store.set_node(identifier, index, "pending")
    store.set_job(identifier, "paused")


def reset_absent_uploads(store, identifier, index):
    job = store.job(identifier)
    rows = [r for r in job["uploads"] if r["node"]==index and r["status"] in ("unknown","started")]
    if not rows:
        raise ValueError("没有待核对的文件上传。")
    for row in rows:
        store.set_upload(identifier,index,row["kind"],row["asset"],row["name"],"pending")
    store.set_node(identifier,index,"unverified" if job["nodes"][index]["task_id"] else "pending")
    store.set_job(identifier,"paused")
