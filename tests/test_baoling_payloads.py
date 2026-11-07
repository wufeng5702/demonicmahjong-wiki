import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from UnityPy.enums import ClassIDType

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from baoling import baoling_category
from extract_bundle import extract_baoling_entries
import extract_icons


def payload(oid, kind=None, name="Test", **kwargs):
    return SimpleNamespace(
        id=oid, baoLingType=kind, m_Name=name,
        displayNameTerm=SimpleNamespace(mTerm=f"BaoLing/Individual/{oid}/Name"),
        descriptionTerm=SimpleNamespace(mTerm=f"BaoLing/Individual/{oid}/Description"),
        **kwargs,
    )


def mono(cls, data):
    data.m_Script = SimpleNamespace(read=lambda: SimpleNamespace(m_ClassName=cls))
    return SimpleNamespace(type=ClassIDType.MonoBehaviour, read=lambda: data)


class TestBaolingCategory(unittest.TestCase):
    def test_unified_payload_uses_type_not_id_range(self):
        self.assertEqual(baoling_category("BaoLingPayload", payload(9999, 0)), "baopai")
        self.assertEqual(baoling_category("BaoLingPayload", payload(10036, 1)), "pailing")
        self.assertEqual(baoling_category("BaoLingPayload", payload(10018, 2)), "pailing")
        self.assertEqual(baoling_category("BaoLingPayload", payload(10036, 0)), "baopai")

    def test_old_separate_classes_still_work(self):
        self.assertEqual(baoling_category("PaiLingPayload", payload(10015)), "pailing")
        self.assertEqual(baoling_category("BaoPaiPayload", payload(1)), "baopai")

    def test_unrelated_classes_and_invalid_ids_are_ignored(self):
        self.assertIsNone(baoling_category("OtherPayload", SimpleNamespace()))
        self.assertIsNone(baoling_category("BaoLingPayload", payload(0, 0)))

    def test_unknown_unified_type_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, "baoLingType"):
            baoling_category("BaoLingPayload", payload(1, 3))


class TestBaolingEntries(unittest.TestCase):
    def test_unified_records_keep_terms_and_numeric_adds(self):
        data = extract_baoling_entries({"BaoLingPayload": [
            (1, payload(1, 0, addBaseScore=50, addFan=3)),
            (2, payload(10015, 1, baseMultiIndependent=1.25)),
            (3, payload(10018, 2)),
        ]})
        self.assertEqual(data["baopai"][0]["adds"], {"addBaseScore": 50, "addFan": 3})
        self.assertEqual(data["pailing"][0]["adds"], {"baseMultiIndependent": 1.25})
        self.assertEqual(data["pailing"][0]["nameKey"], "BaoLing/Individual/10015/Name")
        self.assertEqual([e["id"] for e in data["pailing"]], [10015, 10018])
        self.assertEqual(data["baopai"][0]["descKey"], "BaoLing/Individual/1/Description")

    def test_old_records_and_duplicate_ids(self):
        data = extract_baoling_entries({
            "BaoLingPayload": [(1, payload(1, 0, name="New"))],
            "BaoPaiPayload": [(2, payload(1, name="Old")), (3, payload(2))],
            "PaiLingPayload": [(4, payload(10015))],
        })
        self.assertEqual([e["id"] for e in data["baopai"]], [1, 2])
        self.assertEqual(data["baopai"][0]["en"], "New")
        self.assertEqual([e["id"] for e in data["pailing"]], [10015])

    def test_missing_category_fails_before_json_can_be_overwritten(self):
        for buckets in ({}, {"BaoLingPayload": [(1, payload(1, 0))]}):
            with self.subTest(buckets=buckets):
                with self.assertRaisesRegex(RuntimeError, "拒绝输出空分类"):
                    extract_baoling_entries(buckets)


class TestBaolingIcons(unittest.TestCase):
    def test_pailing_renderer_recognizes_new_and_old_payloads(self):
        objects = {
            1: mono("BaoLingPayload", payload(10015, 1, lingModel=SimpleNamespace(path_id=100))),
            2: mono("PaiLingPayload", payload(10016, lingModel=SimpleNamespace(path_id=100))),
            3: mono("BaoLingPayload", payload(1, 0)),
            4: mono("BaoLingPayload", payload(10018, 2, lingModel=SimpleNamespace(path_id=100))),
            100: SimpleNamespace(type=ClassIDType.GameObject),
        }
        for oid, obj in objects.items():
            obj.path_id = oid
        manager = SimpleNamespace(load_file=lambda _: SimpleNamespace(
            files={"CAB-main": SimpleNamespace(objects=objects)},
        ))
        with tempfile.TemporaryDirectory() as tmp, \
                patch("extract_icons.AssetsManager", return_value=manager), \
                patch("extract_icons.collect_parts", return_value=[object()]), \
                patch("extract_icons.render", return_value=Image.new("RGBA", (4, 4))), \
                contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            self.assertEqual(extract_icons.render_pailing_icons(root / "main.bundle", root), 3)
            self.assertTrue((root / "pailing/10015.png").is_file())
            self.assertTrue((root / "pailing/10016.png").is_file())
            self.assertTrue((root / "pailing/10018.png").is_file())
            self.assertFalse((root / "pailing/1.png").exists())

    def test_baopai_renderer_recognizes_new_and_old_payloads(self):
        material = SimpleNamespace(m_SavedProperties=SimpleNamespace(m_TexEnvs=[
            ("_MainTex", SimpleNamespace(m_Texture=SimpleNamespace(path_id=200))),
            ("_MaskTex", SimpleNamespace(m_Texture=SimpleNamespace(path_id=201))),
        ]))
        objects = {
            1: mono("BaoLingPayload", payload(1, 0, baoMaterialMask=SimpleNamespace(path_id=100))),
            2: mono("BaoPaiPayload", payload(2, baoMaterialMask=SimpleNamespace(path_id=100))),
            3: mono("BaoLingPayload", payload(10015, 1)),
            100: SimpleNamespace(type=ClassIDType.Material, path_id=100, read=lambda: material),
            200: SimpleNamespace(type=ClassIDType.Texture2D, path_id=200,
                                 read=lambda: SimpleNamespace(image=Image.new("RGB", (512, 512), "white"))),
            201: SimpleNamespace(type=ClassIDType.Texture2D, path_id=201,
                                 read=lambda: SimpleNamespace(image=Image.new("RGBA", (512, 512), (0, 0, 255, 255)))),
        }
        for oid, obj in objects.items():
            obj.path_id = oid
        with tempfile.TemporaryDirectory() as tmp, \
                patch("extract_icons.SITE_DIR", Path(tmp)), \
                patch("extract_icons.BUNDLE_PATH", Path(tmp) / "main.bundle"), \
                patch("extract_icons.load_bundle_assets", return_value=(object(), SimpleNamespace(objects=objects))), \
                contextlib.redirect_stdout(io.StringIO()):
            extract_icons.extract_baopai_icons()
            root = Path(tmp) / "icons/baopai"
            self.assertTrue((root / "1.png").is_file())
            self.assertTrue((root / "2.png").is_file())
            self.assertFalse((root / "10015.png").exists())


DATA_JSON = ROOT / "web_src" / "data.json"


@unittest.skipUnless(DATA_JSON.exists(), "data.json 未构建")
class TestBaolingCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA_JSON.read_text(encoding="utf-8"))["data"]

    def assert_ids_preserved(self, cat, expected):
        ids = [entry["id"] for entry in self.data.get(cat, [])]
        self.assertEqual(len(ids), len(set(ids)), f"{cat} ID 重复")
        self.assertTrue(expected <= set(ids), f"{cat} 缺失 ID: {sorted(expected - set(ids))}")

    def test_pailing_and_nianling_ids_are_preserved(self):
        self.assert_ids_preserved("pailing", set(range(10015, 10029)) | {10030, 10031, 10036, 10037, 10038})

    def test_baopai_ids_are_preserved(self):
        self.assert_ids_preserved("baopai", {1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 29, 33, 34, 35, 37, 9999})


if __name__ == "__main__":
    unittest.main()
