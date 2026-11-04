"""Per-user encrypted credentials and durable templates / creation journal."""
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import win32crypt

from .model import title_text, validate_template
from .media import validate_content


def data_directory():
    return Path(os.environ["LOCALAPPDATA"]) / "DAPDTaskTool"


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else data_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "tasks.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS templates (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, nodes TEXT NOT NULL, root TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, created TEXT NOT NULL, plan TEXT NOT NULL,
                    status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS nodes (
                    job TEXT NOT NULL REFERENCES jobs(id), position INTEGER NOT NULL,
                    status TEXT NOT NULL, task_id TEXT, payload TEXT, error TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(job, position));
                CREATE TABLE IF NOT EXISTS uploads (
                    job TEXT NOT NULL, node INTEGER NOT NULL, kind TEXT NOT NULL, asset TEXT NOT NULL,
                    name TEXT NOT NULL, status TEXT NOT NULL, result TEXT, error TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(job,node,kind,asset), FOREIGN KEY(job,node) REFERENCES nodes(job,position));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_key(self, key):
        if not re.fullmatch(r"dapd_[0-9a-f]{64}", key):
            raise ValueError("API Key 格式不正确，请复制 DAPD 设置中生成的完整 Key。")
        blob = win32crypt.CryptProtectData(key.encode(), "DAPD Task Tool", None, None, None, 0)
        target = self.directory / "credential.bin"
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(blob)
        temporary.replace(target)

    def load_key(self):
        path = self.directory / "credential.bin"
        if not path.exists():
            return ""
        try:
            return win32crypt.CryptUnprotectData(path.read_bytes(), None, None, None, 0)[1].decode()
        except Exception as exc:
            raise ValueError("无法读取本机保存的 API Key，请在连接设置中重新输入。") from exc

    def templates(self):
        with self.connect() as db:
            return [{**dict(row), "nodes": json.loads(row["nodes"]), "root": json.loads(row["root"])} for row in db.execute("SELECT * FROM templates ORDER BY name")]

    def save_template(self, name, nodes, identifier=None, root=None):
        name = title_text(name)
        nodes = validate_template(nodes)
        root = validate_content(root)
        identifier = identifier or str(uuid.uuid4())
        try:
            with self.connect() as db:
                db.execute("INSERT INTO templates VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,nodes=excluded.nodes,root=excluded.root",
                           (identifier, name, json.dumps(nodes, ensure_ascii=False), json.dumps(root, ensure_ascii=False)))
        except sqlite3.IntegrityError as exc:
            raise ValueError("已有同名模板，请使用其他名称。") from exc
        return identifier

    def delete_template(self, identifier):
        with self.connect() as db:
            db.execute("DELETE FROM templates WHERE id=?", (identifier,))

    def add_job(self, plan):
        identifier = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO jobs(id,created,plan,status) VALUES(?,?,?,'paused')",
                       (identifier, datetime.now().astimezone().isoformat(timespec="seconds"), json.dumps(plan, ensure_ascii=False)))
            db.executemany("INSERT INTO nodes(job,position,status) VALUES(?,?,'pending')",
                           [(identifier, i) for i in range(len(plan["nodes"]))])
        return identifier

    def job(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise ValueError("创建记录不存在。")
            result = dict(row)
            result["plan"] = json.loads(result["plan"])
            result["nodes"] = [dict(n) for n in db.execute("SELECT * FROM nodes WHERE job=? ORDER BY position", (identifier,))]
            result["uploads"] = [dict(n) for n in db.execute("SELECT * FROM uploads WHERE job=? ORDER BY node,kind", (identifier,))]
            return result

    def jobs(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT j.id,j.created,j.status,j.error,j.plan,
                COUNT(n.position) AS total, SUM(n.status='created') AS done FROM jobs j
                JOIN nodes n ON n.job=j.id GROUP BY j.id ORDER BY j.created DESC,j.rowid DESC""")]

    def set_job(self, identifier, status, error=""):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?,error=? WHERE id=?", (status, error, identifier))

    def set_node(self, identifier, index, status, *, task_id=None, payload=None, error=""):
        with self.connect() as db:
            db.execute("UPDATE nodes SET status=?,task_id=COALESCE(?,task_id),payload=COALESCE(?,payload),error=? WHERE job=? AND position=?",
                       (status, task_id, json.dumps(payload, ensure_ascii=False) if payload is not None else None, error, identifier, index))

    def recover_interrupted(self):
        # Called only after the application has acquired its single-instance lock.
        with self.connect() as db:
            db.execute("UPDATE nodes SET status='unknown',error='上次运行在提交时中断，请先核对 DAPD。' WHERE status='started'")
            db.execute("UPDATE uploads SET status='unknown',error='文件上传时中断，请先核对。' WHERE status='started'")
            db.execute("UPDATE jobs SET status='paused' WHERE status='running'")

    def upload_record(self, job, node, kind, asset):
        with self.connect() as db:
            row = db.execute("SELECT * FROM uploads WHERE job=? AND node=? AND kind=? AND asset=?", (job,node,kind,asset)).fetchone()
            return dict(row) if row else None

    def set_upload(self, job, node, kind, asset, name, status, result=None, error=""):
        with self.connect() as db:
            db.execute("""INSERT INTO uploads VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(job,node,kind,asset)
                DO UPDATE SET status=excluded.status,result=COALESCE(excluded.result,uploads.result),error=excluded.error""",
                       (job,node,kind,asset,name,status,json.dumps(result,ensure_ascii=False) if result is not None else None,error))
