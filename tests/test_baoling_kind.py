import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from extract_events import _baoling_kind


class TestBaolingKind(unittest.TestCase):
    def test_ids_all_ge_10000_is_pailing(self):
        self.assertEqual(_baoling_kind({"baoLingGetList": [10001, 10002]}), "牌灵")

    def test_ids_all_lt_10000_is_baopai(self):
        self.assertEqual(_baoling_kind({"baoLingGetList": [1, 2]}), "宝牌")

    def test_flag_pailing_only(self):
        self.assertEqual(_baoling_kind({"paiLing": True}), "牌灵")

    def test_flag_baopai_only(self):
        self.assertEqual(_baoling_kind({"baoPai": True}), "宝牌")

    def test_both_flags_true_defaults_pailing(self):
        self.assertEqual(_baoling_kind({"paiLing": True, "baoPai": True}), "牌灵")

    def test_no_flags_no_ids_defaults_baopai(self):
        self.assertEqual(_baoling_kind({}), "宝牌")

    def test_mixed_ids_fall_through_to_flags(self):
        n = {"baoLingGetList": [1, 10001], "baoPai": True}
        self.assertEqual(_baoling_kind(n), "宝牌")


if __name__ == "__main__":
    unittest.main()
