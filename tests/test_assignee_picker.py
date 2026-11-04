import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from dapd_tool.assignee_picker import AssigneePicker, ROLE
from dapd_tool.avatars import avatar_thumbnail
from dapd_tool.people import child_departments, department_paths, load_people, scoped_users


USERS = [
    {"id": "a", "name": "崔廷龙", "departmentNames": ["组织", "研发", "音频设计"], "avatar": ""},
    {"id": "b", "name": "沈嘉俊", "departmentNames": ["组织", "研发", "战斗策划"], "avatar": ""},
    {"id": "c", "name": "杨乾", "departmentNames": ["组织", "美术", "组织", "研发", "战斗策划"], "avatar": ""},
    {"id": "d", "name": "Alex", "departmentNames": [], "avatar": ""},
]
GROUPS = [{"id": "g", "name": "核心战斗", "userIds": ["b", "c"]}]


def directory():
    return {"users": USERS, "groups": GROUPS, "scope": "演示项目", "project_selected": True, "history_key": "account:project"}


class PeopleTests(unittest.TestCase):
    def test_fuzzy_name_pinyin_initials_and_scope_labels(self):
        for query, expected in [("廷", ["a"]), ("cuiting", ["a"]), ("SJJ", ["b"]),
                                ("战斗", ["b", "c"]), ("hexin", ["b", "c"]), ("alex", ["d"]), ("不存在", [])]:
            self.assertEqual([u["id"] for u in scoped_users(USERS, GROUPS, "all", query=query)], expected)

    def test_department_paths_keep_multiple_memberships_and_ancestors(self):
        self.assertEqual(department_paths(USERS[2]), [("组织", "美术"), ("组织", "研发", "战斗策划")])
        self.assertEqual(dict(child_departments(USERS, ("组织",)))[("组织", "研发")], {"a", "b", "c"})
        self.assertEqual([u["id"] for u in scoped_users(USERS, GROUPS, "department", ("组织", "研发", "战斗策划"))], ["b", "c"])

    def test_member_groups_and_ungrouped_use_user_ids(self):
        self.assertEqual([u["id"] for u in scoped_users(USERS, GROUPS, "group", group_id="g")], ["b", "c"])
        self.assertEqual([u["id"] for u in scoped_users(USERS, GROUPS, "group")], ["a", "d"])

    def test_directory_preserves_avatars_department_and_project_scope(self):
        api = Mock()
        responses = {"userSetting.getSettings": {"userId": "account"},
                     "project.getProjectMembers": [{"user": u} for u in USERS],
                     "project.listProjectMemberGroups": GROUPS}
        api.request.side_effect = lambda _, name, __: responses[name]
        result = load_people(api, {"id": "project", "name": "演示项目"})
        self.assertEqual(result, directory())
        self.assertTrue(all(c.args[0] == "GET" for c in api.request.call_args_list))

    def test_avatar_load_is_bounded_sanitized_and_does_not_send_credentials(self):
        source = io.BytesIO(); Image.new("RGB", (100, 50), "blue").save(source, "PNG")
        response = Mock(); response.iter_bytes.return_value = [source.getvalue()]
        with patch("dapd_tool.avatars.httpx.stream") as stream:
            stream.return_value.__enter__.return_value = response
            value = avatar_thumbnail("https://example.com/avatar.png")
            self.assertNotIn("headers", stream.call_args.kwargs)
            with Image.open(io.BytesIO(value)) as image:
                self.assertEqual(image.size, (64, 64)); self.assertEqual(image.format, "PNG")
            response.iter_bytes.return_value = [b"x" * (2 * 1024 * 1024 + 1)]
            with self.assertRaises(ValueError): avatar_thumbnail("https://example.com/too-big")
        self.assertEqual(avatar_thumbnail("file:///private.png"), b"")


class PickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.picker = AssigneePicker(self.temp.name)
        self.picker.set_directory(directory()); self.picker.show()
        self.addCleanup(self.picker.close)

    def test_search_enter_selection_reopen_clear_and_account_history(self):
        self.picker.open_popup(); popup = self.picker.popup
        popup.search.setText("sjj"); self.app.processEvents()
        QTest.keyClick(popup.search, Qt.Key.Key_Return)
        self.assertEqual(self.picker.value(), {"id": "b", "name": "沈嘉俊"})
        self.assertEqual(self.picker.history(), ["b"])
        self.picker.open_popup(); popup = self.picker.popup
        self.assertEqual(popup.search.text(), "")
        labels = [popup.list.item(i).text() for i in range(popup.list.count())]
        self.assertIn("当前  1", labels)
        self.assertEqual(popup.list.currentItem().data(ROLE)["id"], "b")
        popup.choose(popup.list.item(0)); self.assertIsNone(self.picker.value())
        self.picker.set_directory({**directory(), "history_key": "another:project"})
        self.assertEqual(self.picker.history(), [])

    def test_department_and_group_switch_preserves_selection_until_choice(self):
        self.picker.set_value({"id": "a", "name": "崔廷龙"}); self.picker.open_popup()
        popup = self.picker.popup; popup.set_mode("department"); popup.navigate(("组织", "研发", "战斗策划"))
        self.assertEqual([popup.list.item(i).data(ROLE)["id"] for i in range(popup.list.count())], ["b", "c"])
        popup.set_mode("group"); popup.select_group(None)
        self.assertTrue(popup.tabs.buttons()[2].isChecked())
        self.assertEqual([popup.list.item(i).data(ROLE)["id"] for i in range(popup.list.count())], ["a", "d"])
        QTest.keyClick(popup.search, Qt.Key.Key_Escape)
        self.assertEqual(self.picker.value()["id"], "a")

    def test_empty_search_keeps_controls_compact_and_project_groups_visible(self):
        self.picker.open_popup(); popup = self.picker.popup
        popup.set_mode("group"); popup.search.setText("不存在")
        self.app.processEvents()
        self.assertEqual(popup.list.count(), 0)
        self.assertTrue(popup.empty.isVisible())
        self.assertLess(popup.tabs.buttons()[0].parentWidget().height(), 50)
        self.assertGreaterEqual(popup.scope_scroll.height(), 70)
        QTest.keyClick(popup.search, Qt.Key.Key_Return)
        self.assertIsNone(self.picker.value())
        popup.close()


if __name__ == "__main__":
    unittest.main()
