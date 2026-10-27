import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "build_icons.py"


class TestIconSubprocessStatus(unittest.TestCase):
    def run_with_step_status(self, status):
        code = f"""
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import patch
sys.argv = [{str(SCRIPT)!r}, "--only", "lingyong"]
with patch("subprocess.run", return_value=SimpleNamespace(returncode={status})):
    runpy.run_path({str(SCRIPT)!r}, run_name="__main__")
"""
        return subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            encoding="utf-8",
        )

    def test_failed_icon_step_exits_nonzero(self):
        result = self.run_with_step_status(1)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_successful_icon_step_exits_zero(self):
        result = self.run_with_step_status(0)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
