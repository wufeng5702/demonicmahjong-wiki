import contextlib
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import logwarn


class TestLogwarn(unittest.TestCase):
    def setUp(self):
        logwarn._WARN.clear()

    def tearDown(self):
        logwarn._WARN.clear()

    def test_warn_collects_location_and_message(self):
        logwarn.warn("boom")
        self.assertEqual(logwarn.warn_count(), 1)
        self.assertIn("test_logwarn.py", logwarn._WARN[0])
        self.assertIn("boom", logwarn._WARN[0])

    def test_warn_default_message(self):
        logwarn.warn()
        self.assertIn("解析失败", logwarn._WARN[0])

    def test_warn_captures_active_exception(self):
        try:
            raise ValueError("bad news")
        except Exception:
            logwarn.warn()
        self.assertIn("ValueError", logwarn._WARN[0])
        self.assertIn("bad news", logwarn._WARN[0])

    def test_flush_prints_and_clears(self):
        logwarn.warn("a")
        logwarn.warn("b")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            logwarn.flush_warns("ctx")
        out = buf.getvalue()
        self.assertIn("2 处解析失败", out)
        self.assertIn("(ctx)", out)
        self.assertIn("a", out)
        self.assertIn("b", out)
        self.assertEqual(logwarn.warn_count(), 0)

    def test_flush_caps_output(self):
        for i in range(logwarn.CAP + 5):
            logwarn.warn(f"m{i}")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            logwarn.flush_warns()
        out = buf.getvalue()
        self.assertIn(f"另有 5 处", out)
        self.assertNotIn(f"m{logwarn.CAP}", out)

    def test_flush_silent_when_empty(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            logwarn.flush_warns("nothing")
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
