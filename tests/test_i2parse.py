import contextlib
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import config
from config import I2_OBJECT_PATH_ID, locate_i2_object
from i2parse import load_i2_terms, tr


def unity_string(text):
    raw = text.encode("utf-8")
    return struct.pack("<i", len(raw)) + raw + b"\0" * (-len(raw) % 4)


def language_source(name="新名称", padding=0):
    raw = b"\0" * (44 + padding)
    for key, zh, en in (("Relic/1/Name", name, "Name"),
                        ("Relic/1/Description", "说明", "Description")):
        raw += unity_string(key) + unity_string("") + struct.pack("<i", 3)
        raw += unity_string(zh) + unity_string(en) + unity_string("")
        raw += struct.pack("<ii", 0, 0)
    return raw


def asset_file(objects):
    return SimpleNamespace(objects={
        pid: SimpleNamespace(type=SimpleNamespace(name=kind),
                             get_raw_data=lambda raw=raw: raw)
        for pid, (kind, raw) in objects.items()
    })


class TestLocateI2Object(unittest.TestCase):
    def test_small_source_and_late_keys_are_not_excluded(self):
        for padding in (0, 200004):
            with self.subTest(padding=padding):
                bf = asset_file({48163: ("MonoBehaviour", language_source(padding=padding))})
                self.assertEqual(locate_i2_object(bf), 48163)

    def test_largest_source_wins_over_historical_id(self):
        bf = asset_file({
            I2_OBJECT_PATH_ID: ("MonoBehaviour", language_source("旧名称")),
            48163: ("MonoBehaviour", language_source(padding=100)),
            99: ("TextAsset", language_source(padding=200)),
        })
        self.assertEqual(locate_i2_object(bf), 48163)

    def test_non_localization_objects_are_ignored(self):
        bf = asset_file({I2_OBJECT_PATH_ID: ("MonoBehaviour", b"not localization")})
        self.assertIsNone(locate_i2_object(bf))


class TestLoadI2Terms(unittest.TestCase):
    def load_from(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in files:
                (root / name).touch()
            manager = SimpleNamespace(load_file=lambda path: files[Path(path).name])
            with patch.object(config, "GAME_DATA_DIR", root), \
                    patch("i2parse.SHARED0", root / "sharedassets0.assets"), \
                    patch("i2parse.AssetsManager", return_value=manager), \
                    contextlib.redirect_stdout(io.StringIO()):
                return load_i2_terms()

    def test_source_moved_to_sharedassets0_with_smaller_scene_copy(self):
        terms = self.load_from({
            "sharedassets0.assets": asset_file({
                48163: ("MonoBehaviour", language_source(padding=100)),
            }),
            "sharedassets1.assets": asset_file({}),
            "sharedassets3.assets": asset_file({
                107288: ("MonoBehaviour", language_source("旧名称")),
            }),
        })
        self.assertEqual(tr("Relic/1/Name", terms), "新名称")
        self.assertEqual(tr("Relic/1/Description", terms), "说明")

    def test_original_sharedassets1_layout_still_works(self):
        terms = self.load_from({"sharedassets1.assets": asset_file({
            I2_OBJECT_PATH_ID: ("MonoBehaviour", language_source()),
        })})
        self.assertEqual(tr("Relic/1/Name", terms), "新名称")

    def test_source_in_resources_without_sharedassets1(self):
        terms = self.load_from({"resources.assets": asset_file({
            42: ("MonoBehaviour", language_source()),
        })})
        self.assertEqual(tr("Relic/1/Name", terms), "新名称")

    def test_unparseable_candidate_does_not_replace_valid_source(self):
        terms = self.load_from({
            "sharedassets0.assets": asset_file({
                1: ("MonoBehaviour", language_source()),
            }),
            "sharedassets3.assets": asset_file({
                2: ("MonoBehaviour", b"/Name /Description" + b"\0" * 1000),
            }),
        })
        self.assertEqual(tr("Relic/1/Name", terms), "新名称")

    def test_no_source_error_reports_scan_scope(self):
        with self.assertRaisesRegex(RuntimeError, r"已扫描 .* 下 1 个 \.assets 文件"):
            self.load_from({"sharedassets1.assets": asset_file({})})

    def test_no_assets_error_reports_empty_scan(self):
        with self.assertRaisesRegex(RuntimeError, r"下 0 个 \.assets 文件"):
            self.load_from({})


if __name__ == "__main__":
    unittest.main()
