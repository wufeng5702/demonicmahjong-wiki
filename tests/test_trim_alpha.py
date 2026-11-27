import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from PIL import Image

from extract_icons import _trim_alpha


def _icon(size, box):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    im.paste((255, 255, 255, 255), box)
    return im


class TestTrimAlpha(unittest.TestCase):
    def test_removes_asymmetric_padding(self):
        # 模拟 303 那类左侧留白: 内容 40..90, 左边 40px / 右边 10px
        out = _trim_alpha(_icon((100, 50), (40, 10, 90, 40)), pad=2)
        self.assertEqual(out.size, (54, 34))

    def test_keeps_padding_smaller_than_pad(self):
        out = _trim_alpha(_icon((100, 50), (1, 1, 99, 49)), pad=2)
        self.assertEqual(out.size, (100, 50))

    def test_transparent_area_with_white_rgb_is_ignored(self):
        im = Image.new("RGBA", (60, 40), (255, 255, 255, 0))
        im.paste((255, 0, 0, 255), (20, 10, 30, 20))
        out = _trim_alpha(im, pad=2)
        self.assertEqual(out.size, (14, 14))

    def test_faint_alpha_below_threshold_is_transparent(self):
        im = Image.new("RGBA", (60, 40), (0, 0, 0, 0))
        im.paste((255, 255, 255, 5), (0, 0, 5, 40))  # 低于阈值
        im.paste((255, 255, 255, 255), (30, 10, 40, 20))
        out = _trim_alpha(im, pad=2, thresh=8)
        self.assertEqual(out.size, (14, 14))

    def test_fully_transparent_returns_original(self):
        im = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        self.assertIs(_trim_alpha(im), im)

    def test_no_alpha_channel_returns_original(self):
        im = Image.new("RGB", (20, 20), (0, 0, 0))
        self.assertIs(_trim_alpha(im), im)


if __name__ == "__main__":
    unittest.main()
