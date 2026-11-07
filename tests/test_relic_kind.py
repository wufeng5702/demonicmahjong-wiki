import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from relic_kind import CURSED_RELIC_SCRIPTS, relic_kind


class TestRelicKind(unittest.TestCase):
    def test_new_curse_classes_work_without_tags(self):
        for cls in ("ZuZhouFangChuiDisplay", "MiDaSiDiaoXiangDisplay"):
            with self.subTest(cls=cls):
                self.assertEqual(relic_kind(cls), "诅咒")

    def test_game_curse_tag_handles_future_classes(self):
        self.assertEqual(relic_kind("NewRelicDisplay", raw_tags=[56000]), "诅咒")

    def test_curse_classification_wins_over_list_fallback(self):
        self.assertEqual(relic_kind("NewRelicDisplay", "神秘", [56000]), "诅咒")

    def test_existing_curses_are_preserved(self):
        for cls in CURSED_RELIC_SCRIPTS:
            with self.subTest(cls=cls):
                self.assertEqual(relic_kind(cls), "诅咒")

    def test_mysterious_and_outsider_fallbacks_are_preserved(self):
        self.assertEqual(relic_kind("BaiBaoXiangDisplay"), "神秘")
        self.assertEqual(relic_kind("UnknownRelicDisplay", "神秘"), "神秘")
        self.assertEqual(relic_kind("UnknownRelicDisplay", "外乡人"), "外乡人")

    def test_manual_related_tag_is_not_a_curse_identity(self):
        self.assertEqual(relic_kind("HuangDiDeXinZhuangDisplay", raw_tags=["魂力", "诅咒"]), "")
        self.assertEqual(relic_kind("HuangDiDeXinZhuangDisplay", raw_tags=[]), "")


if __name__ == "__main__":
    unittest.main()
