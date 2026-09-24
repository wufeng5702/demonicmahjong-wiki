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

APP_JS_PNG = 'const ICON_EXT = ".png";\nconst src = `icons/x/${id}${ICON_EXT}`;\n'
APP_JS_AVIF = APP_JS_PNG.replace('".png"', '".avif"')


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

    def _mk_avif(self, rel: str):
        p = self.deploy_dir / "icons" / rel
        p = p.with_suffix(".avif")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"avif")

    def _run(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            deploy.update_references(self.deploy_dir)
        return buf.getvalue()

    def test_flips_icon_ext_when_all_avif_present(self):
        (self.deploy_dir / "app.js").write_text(APP_JS_PNG, encoding="utf-8")
        self._mk_avif("character/1.png")
        self._run()
        self.assertEqual((self.deploy_dir / "app.js").read_text(encoding="utf-8"),
                         APP_JS_AVIF)

    def test_keeps_icon_ext_when_avif_missing(self):
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
        self._mk_avif("character/1.png")
        self._run()
        self.assertIn("icons/character/1.avif",
                      (self.deploy_dir / "index.html").read_text(encoding="utf-8"))
        self.assertIn("icons/character/1.avif",
                      (self.deploy_dir / "data.json").read_text(encoding="utf-8"))

    def test_missing_avif_literal_left_alone(self):
        (self.deploy_dir / "index.html").write_text(
            '<img src="icons/character/2.png">', encoding="utf-8")
        self._run()
        self.assertIn("icons/character/2.png",
                      (self.deploy_dir / "index.html").read_text(encoding="utf-8"))

    def test_second_run_is_stable(self):
        (self.deploy_dir / "app.js").write_text(APP_JS_PNG, encoding="utf-8")
        (self.deploy_dir / "index.html").write_text(
            '<img src="icons/character/1.png">', encoding="utf-8")
        self._mk_avif("character/1.png")
        self._run()
        out2 = self._run()
        self.assertIn("0 files updated", out2)

    def test_all_icons_have_avif(self):
        empty = self.tmp / "noicons"
        self.assertFalse(deploy._all_icons_have_avif(self.site, empty))
        self.assertFalse(deploy._all_icons_have_avif(self.site, self.deploy_dir))
        self._mk_avif("character/1.png")
        self.assertTrue(deploy._all_icons_have_avif(self.site, self.deploy_dir))


if __name__ == "__main__":
    unittest.main()
