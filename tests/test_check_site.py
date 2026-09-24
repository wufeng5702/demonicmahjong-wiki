import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import check_site


class TestEntriesRouting(unittest.TestCase):
    def test_lingyong_id_ranges(self):
        data = {"lingyong": [
            {"id": 9999}, {"id": 10000}, {"id": 19999}, {"id": 20000},
            {"id": 35000, "tags": ["BOSS主动"]}, {"id": 35001, "tags": []},
        ]}
        r = check_site._entries(data)
        self.assertEqual([e["id"] for e in r["lingyong"]], [9999])
        self.assertEqual([e["id"] for e in r["bosslingyong"]],
                         [10000, 19999, 35000])

    def test_offerings_id_filter(self):
        data = {"offerings": [{"id": 0}, {"id": 1}, {"id": 19999}, {"id": 20000}]}
        r = check_site._entries(data)
        self.assertEqual([e["id"] for e in r["offerings"]], [1, 19999])

    def test_fanzhong_not_checked(self):
        r = check_site._entries({"fanzhong": [{"id": 1}]})
        self.assertNotIn("fanzhong", r)


class TestIconRel(unittest.TestCase):
    def test_enum_placeholder_allowed_without_icon(self):
        self.assertIsNone(check_site._icon_rel("relics", {"id": 1, "src": "enum"}))

    def test_explicit_icon_field_wins(self):
        e = {"id": 1, "icon": "icons/events/9.png"}
        self.assertEqual(check_site._icon_rel("events", e), "icons/events/9")

    def test_category_routing(self):
        cases = {
            "characters": "icons/character/1",
            "lingyong": "icons/lingyong/1",
            "bosslingyong": "icons/lingyong_BOSS/1",
            "offerings": "icons/offerings/1",
            "relics": "icons/relics/1",
            "achievements": "icons/achievements/1",
            "pailing": "icons/pailing/1",
            "baopai": "icons/baopai/1",
            "events": "icons/events/1",
            "yejingbuff": "icons/buff/1",
        }
        for cat, want in cases.items():
            self.assertEqual(check_site._icon_rel(cat, {"id": 1}), want, cat)


class TestCollectErrors(unittest.TestCase):
    def _write(self, root: Path, data: dict, icon_paths: list[str]):
        (root / "data.json").write_text(
            json.dumps({"data": data}, ensure_ascii=False), encoding="utf-8")
        for rel in icon_paths:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"")

    def test_missing_data_json(self):
        with tempfile.TemporaryDirectory() as td:
            errs = check_site.collect_errors(Path(td), ".png")
            self.assertEqual(len(errs), 1)
            self.assertIn("不存在", errs[0])

    def test_missing_icon_reported_then_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = {"characters": [{"id": 7, "en": "Zhu"}]}
            self._write(root, data, [])
            errs = check_site.collect_errors(root, ".png")
            self.assertEqual(errs, ["characters id=7 Zhu 缺图标 icons/character/7.png"])
            self._write(root, data, ["icons/character/7.png"])
            self.assertEqual(check_site.collect_errors(root, ".png"), [])

    def test_enum_placeholder_needs_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write(root, {"relics": [{"id": 3, "src": "enum"}]}, [])
            self.assertEqual(check_site.collect_errors(root, ".png"), [])


if __name__ == "__main__":
    unittest.main()
