import json
import sys
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import extract_icons
from catalog import Catalog


class TestLingyongSpriteName(unittest.TestCase):
    def setUp(self):
        self.sprites = {"IconSkillWangSi": object(), "ID30058ShiE": object()}
        self.catalog = Catalog.__new__(Catalog)
        self.catalog._bin_guid_to_path = {
            "c14ac6fbe65a92142a264d9d6edcb8b1":
                "Assets/ART/UI/SkillIcon/IconSkillWangSi.png",
        }

    def resolve(self, sub="", guid="", catalog=None):
        return extract_icons._lingyong_sprite_name(
            self.sprites, 30058, sub, "ShiE", guid, catalog,
        )

    def test_explicit_subobject_wins(self):
        self.assertEqual(self.resolve("IconSkillWangSi"), "IconSkillWangSi")

    def test_empty_subobject_resolved_by_guid_not_payload_name(self):
        self.assertEqual(
            self.resolve(guid="c14ac6fbe65a92142a264d9d6edcb8b1", catalog=self.catalog),
            "IconSkillWangSi",
        )

    def test_id_fallback_without_catalog(self):
        self.assertEqual(self.resolve(), "ID30058ShiE")

    def test_missing_sprite_does_not_select_unrelated_skill(self):
        self.sprites.pop("ID30058ShiE")
        self.assertIsNone(self.resolve(guid="unknown", catalog=self.catalog))


class TestPailingFaceAnchor(unittest.TestCase):
    def test_manual_face_anchor_overrides_emission_mask(self):
        obj = "\n".join([
            "v 0 0 0", "v 1 0 0", "v 0 1 0",
            "v 0 0 0", "v 0 0 1", "v 0 1 0",
            "vt 0.05 0.90", "vt 0.15 0.90", "vt 0.10 0.95",
            "vt 0.80 0.15", "vt 0.90 0.15", "vt 0.85 0.25",
            "vn 0 0 1", "vn 1 0 0",
            "f 1/1/1 2/2/1 3/3/1", "f 4/4/2 5/5/2 6/6/2",
        ])
        mesh = SimpleNamespace(read=lambda: SimpleNamespace(export=lambda _: obj))
        mask = Image.new("L", (8, 8))
        mask.putpixel((7, 7), 255)
        parts = [(mesh, Image.new("RGBA", (8, 8)), mask, np.eye(4))]
        basis = extract_icons.face_basis(parts, (0.10, 0.92))
        self.assertIsNotNone(basis)
        np.testing.assert_allclose(basis[2], [0, 0, 1])


DATA_JSON = ROOT / "web_src" / "data.json"


@unittest.skipUnless(DATA_JSON.exists(), "data.json 未构建")
class TestDlcRelicCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.relics = json.loads(DATA_JSON.read_text(encoding="utf-8"))["data"]["relics"]

    def test_previous_dlc_relics_are_not_duplicated_by_source(self):
        counts = Counter(e["id"] for e in self.relics)
        for rid in [*range(163, 184), 10028, 10029]:
            with self.subTest(id=rid):
                self.assertEqual(counts[rid], 1)

    def test_full_moon_relics_have_data_and_existing_rarity_categories(self):
        for rid in [*range(184, 199), 10030]:
            with self.subTest(id=rid):
                entries = [e for e in self.relics if e["id"] == rid]
                self.assertEqual(len(entries), 1)
                entry = entries[0]
                self.assertNotEqual(entry.get("src"), "enum")
                self.assertTrue(entry.get("name"))
                self.assertTrue(entry.get("desc"))
                self.assertEqual(entry["kind"], "神秘" if rid == 10030 else "")


if __name__ == "__main__":
    unittest.main()
