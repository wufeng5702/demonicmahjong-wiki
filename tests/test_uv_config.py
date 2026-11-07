import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestUvIndexConfig(unittest.TestCase):
    def test_default_index_matches_locked_package_registry(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
        defaults = [index for index in project["tool"]["uv"]["index"] if index.get("default")]
        self.assertEqual(len(defaults), 1)
        expected = defaults[0]["url"].rstrip("/")
        registries = {p["source"]["registry"].rstrip("/") for p in lock["package"]
                      if "registry" in p["source"]}
        self.assertEqual(registries, {expected})


if __name__ == "__main__":
    unittest.main()
