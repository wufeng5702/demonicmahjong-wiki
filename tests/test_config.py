import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import config


def asset_file(classes):
    def obj(cls):
        script = SimpleNamespace(read=lambda: SimpleNamespace(m_ClassName=cls))
        return SimpleNamespace(
            type=SimpleNamespace(name="MonoBehaviour"),
            read=lambda **kwargs: SimpleNamespace(m_Script=script),
        )
    return SimpleNamespace(objects={pid: obj(cls) for pid, cls in enumerate(classes)})


class TestLocateSharedDataFiles(unittest.TestCase):
    def tearDown(self):
        config.locate_shared_data_files.cache_clear()

    def locate(self, files):
        config.locate_shared_data_files.cache_clear()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in files:
                (root / name).touch()
            manager = SimpleNamespace(load_file=lambda path: asset_file(files[Path(path).name]))
            with patch.object(config, "GAME_DATA_DIR", root), \
                    patch("UnityPy.AssetsManager", return_value=manager) as factory, \
                    contextlib.redirect_stdout(io.StringIO()):
                paths = config.locate_shared_data_files()
                self.assertIs(config.locate_shared_data_files(), paths)
                self.assertEqual(factory.call_count, len(files))
                return {kind: path.name for kind, path in paths.items()}

    def test_updated_layout(self):
        self.assertEqual(self.locate({
            "sharedassets0.assets": ["AchievementPayload"] * 3,
            "sharedassets1.assets": [],
            "sharedassets3.assets": ["AchievementPayload", "CharacterPayload"],
            "sharedassets4.assets": [],
        }), {"base": "sharedassets0.assets", "characters": "sharedassets3.assets"})

    def test_original_layout(self):
        self.assertEqual(self.locate({
            "sharedassets1.assets": ["AchievementPayload"] * 3,
            "sharedassets4.assets": ["AchievementPayload", "CharacterPayload"],
        }), {"base": "sharedassets1.assets", "characters": "sharedassets4.assets"})

    def test_largest_character_table_wins_over_partial_copy(self):
        self.assertEqual(self.locate({
            "resources.assets": ["CharacterPayload"],
            "sharedassets0.assets": ["AchievementPayload"] * 2,
            "sharedassets3.assets": ["CharacterPayload"] * 3,
        })["characters"], "sharedassets3.assets")

    def test_missing_data_is_not_silently_accepted(self):
        with self.assertRaisesRegex(RuntimeError, "characters"):
            self.locate({"sharedassets0.assets": ["AchievementPayload"]})


if __name__ == "__main__":
    unittest.main()
