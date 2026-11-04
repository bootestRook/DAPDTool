from dapd_tool.catalog import group_id_from_text, locate_group, task_id_from_text
from creation_fixture import CreationCase

class CatalogTests(CreationCase):
    def test_copied_group_link_with_chinese_name_and_query(self):
        text = "示例版本（测试）（ https://dapd.dodjoy.com/groups/11111111-2222-4333-8444-555555555555?only=true ）"
        self.assertEqual(group_id_from_text(text), "11111111-2222-4333-8444-555555555555")
        for invalid in ["https://example.com/groups/11111111-2222-4333-8444-555555555555", "示例版本", text + " https://dapd.dodjoy.com/groups/11111111-2222-4333-8444-555555555556"]:
            with self.assertRaises(ValueError):
                group_id_from_text(invalid)

    def test_group_link_resolves_project_by_id_not_name(self):
        self.api.projects.return_value = [{"id":"p1","name":"同名项目"}, {"id":"p2","name":"同名项目"}]
        self.api.groups.side_effect = lambda p: [{"id":"g1" if p=="p1" else "g2", "name":"同名任务组"}]
        result = locate_group(self.api, "g2")
        self.assertEqual(result["project"]["id"], "p2")
        self.assertEqual(result["group"]["id"], "g2")
        with self.assertRaises(ValueError):
            locate_group(self.api, "missing")

    def test_copied_parent_link_or_id_or_search_term(self):
        identifier = "22222222-3333-4444-8555-666666666666"
        text = f"DAPD任务：【示例】主任务（ https://dapd.dodjoy.com/task/{identifier} ）"
        self.assertEqual(task_id_from_text(text), identifier)
        self.assertEqual(task_id_from_text(identifier), identifier)
        self.assertIsNone(task_id_from_text("【示例】主任务"))
        with self.assertRaises(ValueError):
            task_id_from_text("https://other.example/task/" + identifier)
