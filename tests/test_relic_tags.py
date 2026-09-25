import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from enums import TAG_CN, TAG_ID_CN, _resolve_tag
from relic_tags import EXTRA_RELIC_TAGS, FIX_RELIC_TAGS, apply_relic_tags

TAG_ENUM = {
    63: "BaseScore", 64: "Fan", 65: "Independent", 76: "HuSlot", 77: "LingYongSlot",
    78: "OfferingSlot", 2000: "Relic", 42000: "Weapon", 43101: "Lotus",
    47000: "Runestone", 47001: "Token", 47010: "TreasureMirror",
    50500: "MapNode", 56000: "Curse",
}
ENUM_VALUES = {"Tag": TAG_ENUM}


class TestResolveTag(unittest.TestCase):
    def test_relic_tags_resolve_to_chinese(self):
        self.assertEqual(
            _resolve_tag([43101, 76, 77], ENUM_VALUES),
            ["莲花", "和牌槽", "灵佣槽"],
        )

    def test_runestone_and_token_are_distinct(self):
        self.assertEqual(_resolve_tag([47000], ENUM_VALUES), ["符石"])
        self.assertEqual(_resolve_tag([47001], ENUM_VALUES), ["令牌"])

    def test_id_fallback_without_enum_values(self):
        self.assertEqual(_resolve_tag([43101, 42000]), ["莲花", "武器"])

    def test_empty_and_none(self):
        self.assertEqual(_resolve_tag([]), [])
        self.assertEqual(_resolve_tag(None), [])

    def test_no_english_leak(self):
        for tid, name in TAG_ENUM.items():
            got = _resolve_tag([tid], ENUM_VALUES)[0]
            self.assertTrue(any("一" <= c <= "鿿" for c in got),
                            f"Tag.{name}({tid}) 未中文化: {got}")

    def test_name_and_id_maps_agree(self):
        for tid, name in TAG_ENUM.items():
            if name in TAG_CN:
                self.assertEqual(TAG_CN[name], TAG_ID_CN.get(tid, TAG_CN[name]),
                                 f"Tag.{name}({tid}) 中英映射不一致")


VOCAB = set(TAG_CN.values()) | set(TAG_ID_CN.values())
DATA_JSON = ROOT / "web_src" / "data.json"


class TestRelicTagPatch(unittest.TestCase):
    def test_update_tag_renamed_to_bianxing(self):
        self.assertEqual(TAG_CN["Update"], "变形")
        self.assertEqual(TAG_ID_CN[50100], "变形")

    def test_patch_tags_use_known_vocabulary(self):
        for table in (EXTRA_RELIC_TAGS, FIX_RELIC_TAGS):
            for rid, tags in table.items():
                self.assertGreater(rid, 0)
                self.assertTrue(tags, f"relic {rid} 空标签")
                for t in tags:
                    self.assertIn(t, VOCAB, f"relic {rid} 标签 {t} 未中文化/未定义")

    def test_fix_and_extra_tables_are_disjoint(self):
        overlap = set(EXTRA_RELIC_TAGS) & set(FIX_RELIC_TAGS)
        self.assertEqual(overlap, set(), f"同一遗物同时出现在两表: {overlap}")

    def test_extra_only_fills_empty_and_fix_overrides(self):
        relics = [
            {"id": 1, "tags": ["莲花"]},
            {"id": 163, "tags": []},
            {"id": 137, "tags": ["金币"]},
            {"id": 999999, "tags": []},
        ]
        self.assertEqual(apply_relic_tags(relics), (1, 1))
        self.assertEqual(relics[0]["tags"], ["莲花"])
        self.assertEqual(relics[1]["tags"], ["宝牌"])
        self.assertEqual(relics[2]["tags"], ["牌灵"])
        self.assertEqual(relics[3]["tags"], [])

    def test_reported_fixes(self):
        self.assertEqual(FIX_RELIC_TAGS[137], ["牌灵"])
        self.assertEqual(FIX_RELIC_TAGS[145], ["番数", "念灵", "武器"])
        self.assertEqual(FIX_RELIC_TAGS[10017], ["供台", "灵佣槽", "宝牌"])


@unittest.skipUnless(DATA_JSON.exists(), "data.json 未构建")
class TestRelicTagCoverage(unittest.TestCase):
    """验收标准: 绝大多数(要求全部)已实装遗物都要有标签。"""

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA_JSON.read_text(encoding="utf-8"))["data"]

    def test_implemented_relics_all_tagged(self):
        missing = [
            f'{e["id"]}{e.get("name") or e.get("en")}'
            for e in self.data["relics"]
            if e.get("src") != "enum" and not e.get("tags")
        ]
        self.assertEqual(missing, [], f"未打标签的已实装遗物: {missing}")

    def test_all_tags_chinese_vocabulary(self):
        leaks = set()
        for cat in ("relics", "lingyong"):
            for e in self.data.get(cat, []):
                for t in e.get("tags") or []:
                    if t not in VOCAB:
                        leaks.add(f"{cat}:{e.get('id')}:{t}")
        self.assertEqual(sorted(leaks), [], f"标签不在词表内: {sorted(leaks)}")

    def test_fix_table_applied(self):
        by_id = {e["id"]: e for e in self.data["relics"]}
        stale = [
            f'{rid}:{by_id[rid].get("tags")} != {want}'
            for rid, want in FIX_RELIC_TAGS.items()
            if rid in by_id and by_id[rid].get("src") != "enum"
            and by_id[rid].get("tags") != want
        ]
        self.assertEqual(stale, [], f"FIX 未生效(需重建 data.json): {stale}")


if __name__ == "__main__":
    unittest.main()
