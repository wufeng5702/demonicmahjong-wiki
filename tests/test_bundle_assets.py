import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from bundle_assets import load_bundle_assets


class TestBundleAssets(unittest.TestCase):
    def test_nested_ui_bundles_and_shared_dependencies_are_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = ["defaultlocalgroup_assets_all_hash.bundle",
                     "shared_core_assets_bundle/shared_core_hash.bundle",
                     "ui_icons_assets_bundle/ui_icons_hash.bundle",
                     "ui_event_assets_bundle/ui_event_01_hash.bundle"]
            files = {}
            for pid, name in enumerate(names, 1):
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.touch()
                files[str(path)] = SimpleNamespace(files={
                    f"CAB-{pid}": SimpleNamespace(
                        objects={pid: f"object-{pid}"}, container={name: f"pointer-{pid}"},
                    ),
                    f"CAB-{pid}.resS": SimpleNamespace(),
                })
            manager = SimpleNamespace(load_file=lambda path: files[path])
            with patch("bundle_assets.AA_DIR", root), \
                    patch("bundle_assets.BUNDLE_PATH", root / names[0]), \
                    patch("bundle_assets.AssetsManager", return_value=manager):
                am, sf = load_bundle_assets()
            self.assertIs(am, manager)
            self.assertEqual(len(sf.objects), 4)
            self.assertEqual(len(sf.container), 4)

    def test_original_single_bundle_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "defaultlocalgroup_assets_all_hash.bundle"
            path.touch()
            sf = SimpleNamespace(objects={1: "object"}, container={"icon.png": "pointer"})
            manager = SimpleNamespace(load_file=lambda path: SimpleNamespace(files={"CAB-main": sf}))
            with patch("bundle_assets.AA_DIR", root), \
                    patch("bundle_assets.BUNDLE_PATH", path), \
                    patch("bundle_assets.AssetsManager", return_value=manager):
                _, assets = load_bundle_assets()
            self.assertEqual(assets.objects, sf.objects)
            self.assertEqual(assets.container, sf.container)


if __name__ == "__main__":
    unittest.main()
