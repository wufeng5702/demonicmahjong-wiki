import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from schema import offering_entry, relic_entry


class TestRelicEntry(unittest.TestCase):
    def test_key_order_with_icon(self):
        e = relic_entry(id=1, rarity=2, stack=3, kind="诅咒", src="bundle",
                        icon_pid=99, en="A", cn="甲")
        self.assertEqual(
            list(e.keys()),
            ["id", "en", "cn", "nameKey", "descKey", "rarity", "stack",
             "kind", "icon_pid", "src"],
        )
        self.assertEqual(e["icon_pid"], 99)

    def test_icon_pid_omitted_when_none(self):
        e = relic_entry(id=2, rarity=0, stack=0, kind="", src="enum")
        self.assertNotIn("icon_pid", e)
        self.assertEqual(list(e.keys())[-2:], ["kind", "src"])

    def test_id_coerced_to_int(self):
        e = relic_entry(id="5", rarity="1", stack="2", kind="", src="shared")
        self.assertEqual((e["id"], e["rarity"], e["stack"]), (5, 1, 2))


class TestOfferingEntry(unittest.TestCase):
    def test_bundle_shape_has_no_icon_or_src(self):
        e = offering_entry(id=10, en="X", level=1, adds={"hp": 2})
        self.assertEqual(
            list(e.keys()),
            ["id", "en", "level", "nameKey", "descKey", "adds",
             "fanZhong", "useTiming", "useType"],
        )

    def test_shared_shape_appends_icon_then_src(self):
        e = offering_entry(id=11, icon_pid=7, src="shared")
        self.assertEqual(list(e.keys())[-2:], ["icon_pid", "src"])

    def test_adds_defaults_to_empty_dict(self):
        e = offering_entry(id=12)
        self.assertEqual(e["adds"], {})


if __name__ == "__main__":
    unittest.main()
