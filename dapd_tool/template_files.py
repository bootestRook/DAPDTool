"""Portable template files reuse the versioned, checked content-pack format.

The schema version is independent of application releases. Schema 1 exports
remain importable by later releases; credentials and creation receipts are excluded.
"""
import json
import tempfile
import uuid
import shutil
from pathlib import Path
from .content_packs import export_pack, install_pack, load_shared, all_assets
from .media import Assets


def export_templates(store, templates, output):
    clean = [{k: t[k] for k in ("id", "name", "nodes", "root")} for t in templates]
    for item in clean:
        item["id"] = str(uuid.uuid4())
    return export_pack(store.directory, clean, "1.0.0", "个人模板导入导出", output)


def import_templates(store, path):
    # Validate the entire archive before changing any personal template.
    with tempfile.TemporaryDirectory(prefix="dapd-import-") as temporary:
        install_pack(temporary, path, "1.0.0")
        templates = load_shared(temporary)["templates"]
        source, target = Assets(temporary), Assets(store.directory)
        for template in templates:
            for asset in all_assets(template):
                existing = target.directory / asset["file"]
                if existing.exists():
                    target.path(asset, verify_hash=True)
                else:
                    shutil.copyfile(source.path(asset, verify_hash=True), existing)
        ids = []
        with store.connect() as db:
            names = {r[0] for r in db.execute("SELECT name FROM templates")}
            for template in templates:
                name, counter = template["name"], 1
                while name in names:
                    counter += 1
                    name = f"{template['name'][:235]}（导入 {counter}）"
                names.add(name)
                identifier = str(uuid.uuid4())
                db.execute("INSERT INTO templates VALUES(?,?,?,?)", (identifier, name,
                           json.dumps(template["nodes"], ensure_ascii=False), json.dumps(template["root"], ensure_ascii=False)))
                ids.append(identifier)
        return ids
