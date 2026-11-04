from pathlib import Path
from dapd_tool.storage import Store
from creation_fixture import CreationCase, TREE

class StorageTests(CreationCase):
    def test_empty_library_and_user_templates_survive_restart(self):
        self.assertEqual(self.store.templates(), [])
        tid = self.store.save_template("测试模板", TREE)
        self.assertEqual(Store(self.temp.name).templates()[0]["nodes"], TREE)
        self.store.save_template("新名称", TREE[:1], tid)
        self.assertEqual(len(self.store.templates()), 1)
        self.store.delete_template(tid)
        self.assertEqual(self.store.templates(), [])

    def test_encrypted_key_roundtrip_does_not_store_plaintext(self):
        key = "dapd_" + "b" * 64
        self.store.save_key(key)
        self.assertEqual(self.store.load_key(), key)
        self.assertNotIn(key.encode(), (Path(self.temp.name) / "credential.bin").read_bytes())
