import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import deploy

IMG_EXT = deploy.IMG_EXT
APP_JS_PNG = 'const ICON_EXT = ".png";\nconst src = `icons/x/${id}${ICON_EXT}`;\n'
APP_JS_OPT = APP_JS_PNG.replace('".png"', f'"{IMG_EXT}"')


class TestUpdateReferences(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.site = self.tmp / "site"
        self.deploy_dir = self.tmp / "deploy"
        self.site_icons = self.site / "icons" / "character"
        self.site_icons.mkdir(parents=True)
        self.deploy_dir.mkdir()
        (self.site_icons / "1.png").write_bytes(b"png")
        # ICON_EXT 切换依赖 deploy.SITE 全局
        self._orig_site = deploy.SITE
        deploy.SITE = self.site

    def tearDown(self):
        deploy.SITE = self._orig_site
        self._td.cleanup()

    def _mk_opt(self, rel: str):
        p = self.deploy_dir / "icons" / rel
        p = p.with_suffix(IMG_EXT)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(IMG_EXT.encode())

    def _run(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            deploy.update_references(self.deploy_dir)
        return buf.getvalue()

    def test_flips_icon_ext_when_all_icons_present(self):
        (self.deploy_dir / "app.js").write_text(APP_JS_PNG, encoding="utf-8")
        self._mk_opt("character/1.png")
        self._run()
        self.assertEqual((self.deploy_dir / "app.js").read_text(encoding="utf-8"),
                         APP_JS_OPT)

    def test_keeps_icon_ext_when_icons_missing(self):
        (self.deploy_dir / "app.js").write_text(APP_JS_PNG, encoding="utf-8")
        out = self._run()
        self.assertIn("warning", out)
        self.assertEqual((self.deploy_dir / "app.js").read_text(encoding="utf-8"),
                         APP_JS_PNG)

    def test_literal_refs_in_html_json_rewritten(self):
        (self.deploy_dir / "index.html").write_text(
            '<img src="icons/character/1.png">', encoding="utf-8")
        (self.deploy_dir / "data.json").write_text(
            json.dumps({"icon": "icons/character/1.png"}), encoding="utf-8")
        self._mk_opt("character/1.png")
        self._run()
        self.assertIn(f"icons/character/1{IMG_EXT}",
                      (self.deploy_dir / "index.html").read_text(encoding="utf-8"))
        self.assertIn(f"icons/character/1{IMG_EXT}",
                      (self.deploy_dir / "data.json").read_text(encoding="utf-8"))

    def test_missing_icon_literal_left_alone(self):
        (self.deploy_dir / "index.html").write_text(
            '<img src="icons/character/2.png">', encoding="utf-8")
        self._run()
        self.assertIn("icons/character/2.png",
                      (self.deploy_dir / "index.html").read_text(encoding="utf-8"))

    def test_second_run_is_stable(self):
        (self.deploy_dir / "app.js").write_text(APP_JS_PNG, encoding="utf-8")
        (self.deploy_dir / "index.html").write_text(
            '<img src="icons/character/1.png">', encoding="utf-8")
        self._mk_opt("character/1.png")
        self._run()
        out2 = self._run()
        self.assertIn("0 files updated", out2)

    def test_all_icons_have_opt(self):
        empty = self.tmp / "noicons"
        self.assertFalse(deploy._all_icons_have_opt(self.site, empty))
        self.assertFalse(deploy._all_icons_have_opt(self.site, self.deploy_dir))
        self._mk_opt("character/1.png")
        self.assertTrue(deploy._all_icons_have_opt(self.site, self.deploy_dir))

    def test_switches_from_other_format(self):
        old_ext = next(e for e in deploy.IMG_FORMATS if e != IMG_EXT)
        (self.deploy_dir / "app.js").write_text(
            APP_JS_PNG.replace('".png"', f'"{old_ext}"'), encoding="utf-8")
        (self.deploy_dir / "index.html").write_text(
            f'<img src="icons/character/1{old_ext}">', encoding="utf-8")
        self._mk_opt("character/1.png")
        self._run()
        self.assertEqual((self.deploy_dir / "app.js").read_text(encoding="utf-8"),
                         APP_JS_OPT)
        self.assertIn(f"icons/character/1{IMG_EXT}",
                      (self.deploy_dir / "index.html").read_text(encoding="utf-8"))

    def test_stale_format_ref_falls_back_to_png(self):
        old_ext = next(e for e in deploy.IMG_FORMATS if e != IMG_EXT)
        (self.deploy_dir / "index.html").write_text(
            f'<img src="icons/character/9{old_ext}">', encoding="utf-8")
        self._run()
        self.assertIn("icons/character/9.png",
                      (self.deploy_dir / "index.html").read_text(encoding="utf-8"))


class TestSyncAndOptimize(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.src = self.tmp / "src"
        self.dst = self.tmp / "dst"
        p = self.src / "character" / "1.png"
        p.parent.mkdir(parents=True)
        Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(p)

    def tearDown(self):
        self._td.cleanup()

    def _run(self):
        with contextlib.redirect_stdout(io.StringIO()):
            deploy.sync_and_optimize(self.src, self.dst)

    def test_generates_current_format(self):
        self._run()
        self.assertTrue((self.dst / "character" / "1.png").exists())
        self.assertTrue((self.dst / "character" / f"1{IMG_EXT}").exists())

    def test_legacy_format_removed(self):
        self._run()
        for ext in deploy.LEGACY_EXTS:
            legacy = self.dst / "character" / f"1{ext}"
            legacy.write_bytes(b"stale")
        self._run()
        for ext in deploy.LEGACY_EXTS:
            self.assertFalse((self.dst / "character" / f"1{ext}").exists())
        self.assertTrue((self.dst / "character" / f"1{IMG_EXT}").exists())


if __name__ == "__main__":
    unittest.main()
