from dapd_tool.model import creation_order, make_plan, validate_template
from creation_fixture import CreationCase, TREE, DEST

class PlanningTests(CreationCase):
    def test_template_cycles_invalid_parent_and_blank_titles_rejected(self):
        for nodes in [[{"title": "a", "parent": 0}], [{"title": "a", "parent": -1}], [{"title": "a", "parent": True}], [{"title": " ", "parent": None}]]:
            with self.assertRaises(ValueError):
                validate_template(nodes)

    def test_duplicate_roots_and_missing_destination_rejected(self):
        for titles, dest in [(["a", "a"], DEST), (["a"], {}), ([], DEST)]:
            with self.assertRaises(ValueError):
                make_plan(titles, TREE, dest)

    def test_deep_template_does_not_depend_on_python_recursion(self):
        tree = [{"title": str(index), "parent": index - 1 if index else None} for index in range(1100)]
        plan = make_plan(["主任务"], tree, DEST)
        self.assertEqual(list(creation_order(plan)), list(range(1101)))

    def test_plan_is_snapshot_not_live_template(self):
        template_id = self.store.save_template("t", TREE)
        identifier = self.add()
        self.store.save_template("t", [], template_id)
        self.assertEqual(len(self.store.job(identifier)["plan"]["nodes"]), 10)
