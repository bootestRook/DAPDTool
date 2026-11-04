"""Creation journal presentation values and CSV export."""
import csv

from dapd_api import task_url


STATUS = {"pending": "等待创建", "started": "正在提交", "created": "已创建", "unverified": "已提交，待回读",
          "failed": "提交被拒绝", "unknown": "结果待核对", "paused": "已暂停", "running": "创建中",
          "completed": "已完成", "blocked": "待核对", "media_unknown":"上传结果待核对"}


def export_job(job, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as output:
        writer = csv.writer(output)
        writer.writerow(["序号", "标题", "父节点序号", "状态", "任务 ID", "链接"])
        for row, node in zip(job["nodes"], job["plan"]["nodes"]):
            title = node["title"]
            if title.startswith(("=", "+", "-", "@", "\t", "\r")):
                title = "'" + title
            writer.writerow([row["position"] + 1, title, "" if node["parent"] is None else node["parent"] + 1,
                             STATUS[row["status"]], row["task_id"] or "", task_url(row["task_id"]) if row["task_id"] else ""])
