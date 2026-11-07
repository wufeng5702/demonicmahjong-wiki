import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from rawparse import EVENTNODE_SPEC, parse_payload


def string(text):
    raw = text.encode("utf-8")
    return struct.pack("<i", len(raw)) + raw + b"\0" * (-len(raw) % 4)


def pptr(pid):
    return struct.pack("<iq", 0, pid)


def header():
    return pptr(0) + struct.pack("<i", 1) + pptr(10) + string("Test")


class TestUpdatedPayloadLayouts(unittest.TestCase):
    def test_event_grant_fields_do_not_shift_icon_or_ports(self):
        added = {"allowReplace", "grantMode", "candidateRarityLimit", "fallbackRarityLimit"}
        raw = header()
        for name, kind in EVENTNODE_SPEC:
            if name in added:
                continue
            if kind in ("i", "b"):
                raw += struct.pack("<i", 0)
            elif kind == "f":
                raw += struct.pack("<f", 0)
            elif kind == "s":
                raw += string("icon-guid" if name == "spriteGUID" else "")
            elif kind == "p":
                raw += pptr(0)
            elif kind == "v2":
                raw += struct.pack("<2f", 0, 0)
            elif kind == "v3":
                raw += struct.pack("<3f", 0, 0, 0)
            elif kind in ("vi", "vp"):
                raw += struct.pack("<i", 1 if name == "ports" else 0)
                if name == "ports":
                    raw += pptr(42)
            else:
                self.fail(f"Unsupported fixture type: {kind}")
            if name == "fillFromWholePool":
                # 独立于解析规格写入新版的四个字段。
                raw += struct.pack("<4i", 1, 2, 3, 4)
        data = parse_payload(raw, "EventNode")
        self.assertTrue(data["allowReplace"])
        self.assertEqual(data["grantMode"], 2)
        self.assertEqual(data["candidateRarityLimit"], 3)
        self.assertEqual(data["fallbackRarityLimit"], 4)
        self.assertEqual(data["spriteGUID"], "icon-guid")
        self.assertEqual(data["ports"][0]["path_id"], 42)

    def test_character_base_id_does_not_shift_references(self):
        # 新版 bundle 类型树: skinId 后新增 baseCharacterID。
        raw = header() + struct.pack("<4i", 5, 41, 0, 2) + pptr(42)
        raw += struct.pack("<i", 1) + pptr(43)  # passiveSkill
        raw += struct.pack("<i", 1) + pptr(44)  # activeSkill
        raw += struct.pack("<3i", 2, 40, 42) + struct.pack("<i", 4)
        raw += pptr(45) + pptr(0)
        raw += string("guid") + string("") + string("")
        raw += pptr(0) + string("https://example.com")
        raw += pptr(0) * 3  # jiFenBank / jiFenPlay / jiFenStop
        data = parse_payload(raw, "CharacterPayload")
        self.assertEqual(data["baseCharacterID"], 2)
        self.assertEqual(data["roleAvatar"]["path_id"], 42)
        self.assertEqual(data["passiveSkill"][0]["path_id"], 43)
        self.assertEqual(data["activeSkill"][0]["path_id"], 44)
        self.assertEqual(data["fanZhongList"], [40, 42])
        self.assertEqual(data["url_Walkthrough"], "https://example.com")

    def test_offering_huases_does_not_shift_description_vector(self):
        # 新版 bundle 类型树: accMultiIndependent 后新增 huaSes。
        raw = header() + struct.pack("<i", 20033)
        raw += string("Offering/1/Name") + b"\0" * 16
        raw += string("Offering/1/Description") + b"\0" * 16
        raw += struct.pack("<2i", 0, 1) + pptr(42)
        raw += struct.pack("<2i", 2, 0) + pptr(0) + pptr(0)
        raw += struct.pack("<3i", 2, 0, 0)
        raw += struct.pack("<5f", 0, 0, 0, 15, 0.15)
        raw += struct.pack("<3i", 2, 1, 3)  # huaSes
        raw += struct.pack("<if2f", 40, 1.5, 0, 0)
        raw += struct.pack("<i", 1) + string("Offering/1/Dynamic") + b"\0" * 16
        raw += struct.pack("<i", 0)  # geShengAdd
        data = parse_payload(raw, "OfferingPayload")
        self.assertEqual(data["huaSes"], [1, 3])
        self.assertEqual(data["fanZhong"], 40)
        self.assertEqual(data["multi"], 1.5)
        self.assertEqual(data["dynamicDescriptionTerms"], ["Offering/1/Dynamic"])


if __name__ == "__main__":
    unittest.main()
