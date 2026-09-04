#!/usr/bin/env python3
"""
rawparse.py - 类型树被剥离的 MonoBehaviour 手工解析器
=====================================================
Unity 序列化的字节布局规则 (由 dump.cs 字段声明顺序 + 字节校准得出):

  MonoBehaviour 头部 28B: GameObject PPtr(12) + enabled(1+pad3) + Script PPtr(12)
  随后 m_Name(string), 再按 C# 声明顺序内联各字段。

  类型规则:
    int/enum/float = 4B;  bool = 1B (不主动对齐);
    任何非 bool 字段读取前先对齐到 4B;
    string = len(i32) + bytes + align4;
    PPtr = file_id(i32) + path_id(i64);
    List<T>/T[] = count(i32) + N×T;
    LocalizedString(struct) = mTerm(str) + bool + i32 + bool + bool
    SaintsDictionary(空表时) = 固定 7×4B (两个空 List + 2 enum + version + 2 空 List)

字段规格 SPECS 来自 dump_output/dump.cs 中各类的声明顺序。
"""

import re
import struct


class ParseError(Exception):
    pass


class RawReader:
    def __init__(self, buf, pos=0):
        self.b = buf
        self.p = pos

    def _align(self):
        self.p += (-self.p) % 4

    def i32(self):
        self._align()
        v = struct.unpack_from("<i", self.b, self.p)[0]
        self.p += 4
        return v

    def f32(self):
        self._align()
        v = struct.unpack_from("<f", self.b, self.p)[0]
        self.p += 4
        return v

    def b1(self):
        """Unity 序列化实测(本项目): 每个 bool 独立对齐——读1B后补齐到4。"""
        self._align()
        v = self.b[self.p]
        self.p += 1
        self._align()
        return bool(v)

    def string(self):
        self._align()
        n = struct.unpack_from("<i", self.b, self.p)[0]
        if n < 0 or n > 1_000_000:
            raise ParseError(f"bad strlen {n} @{self.p}")
        s = self.b[self.p + 4:self.p + 4 + n].decode("utf-8", "replace")
        self.p += 4 + n
        self._align()
        return s

    def pptr(self):
        self._align()
        fid = struct.unpack_from("<i", self.b, self.p)[0]
        pid = struct.unpack_from("<q", self.b, self.p + 4)[0]
        self.p += 12
        return {"file_id": fid, "path_id": pid}

    def color(self):
        vals = struct.unpack_from("<4f", self.b, self.p)
        self.p += 16
        return [round(x, 4) for x in vals]

    def v2(self):
        vals = struct.unpack_from("<2f", self.b, self.p)
        self.p += 8
        return list(vals)

    def v3(self):
        vals = struct.unpack_from("<3f", self.b, self.p)
        self.p += 12
        return list(vals)

    def asset_ref(self):
        """AssetReference(SerializeReference 实测): [guid][subName][类型名字符串]"""
        return {"guid": self.string(), "sub": self.string(), "type": self.string()}


def read_typed(r: RawReader, t):
    """按类型码读一个值。"""
    if t == "i":
        return r.i32()
    if t == "f":
        return round(r.f32(), 6)
    if t == "b":
        return r.b1()
    if t == "s":
        return r.string()
    if t == "p":
        return r.pptr()
    if t == "c4":
        return r.color()
    if t == "v2":
        return r.v2()
    if t == "v3":
        return r.v3()
    if t == "sd28":  # SaintsDictionary 假定空表
        r.i32(); r.i32(); r.i32(); r.i32(); r.i32(); r.i32(); r.i32()
        return {}
    if t == "ar":
        return r.asset_ref()
    raise ParseError(f"unknown type {t}")


VEC_OF = {"vi": "i", "vs": "s", "vp": "p", "vls": "ls"}


def read_ls(r: RawReader):
    """LocalizedString struct: mTerm(str) + bool + i32 + bool + bool (各 bool 独立对齐, 尾部共16B)"""
    term = r.string()
    r.b1()          # mRTL_IgnoreArabicFix
    r.i32()         # mRTL_MaxLineLength
    r.b1()          # mRTL_ConvertNumbers
    r.b1()          # m_DontLocalizeParameters
    return term


def parse_fields(buf: bytes, start: int, spec):
    """从 start 起按 spec=[(name,type)] 解析, 返回 dict。失败抛 ParseError。"""
    r = RawReader(buf, start)
    out = {}
    for name, t in spec:
        if t in VEC_OF:
            r._align()
            n = struct.unpack_from("<i", r.b, r.p)[0]
            if n < 0 or n > 100_000:
                raise ParseError(f"{name}: bad vec len {n} @{r.p}")
            r.p += 4
            et = VEC_OF[t]
            if t == "vls":
                out[name] = [read_ls(r) for _ in range(n)]
            else:
                out[name] = [read_typed(r, et) for _ in range(n)]
            r._align()
        elif t == "ls":
            out[name] = read_ls(r)
        else:
            out[name] = read_typed(r, t)
    return out


def mb_header(buf: bytes):
    """MonoBehaviour 头部: 返回 (go_pptr, enabled, script_pptr, name, fields_start_pos)。"""
    r = RawReader(buf, 0)
    go = r.pptr()
    enabled = r.b1()
    sc = r.pptr()
    name = r.string()
    return go, enabled, sc, name, r.p


# ============================================================
# 类字段规格 (源: dump.cs 声明顺序)
# ============================================================
LS = "ls"

XIAOCHOU_SPEC = [
    ("id", "i"), ("rarity", "i"),
    ("displayNameTerm", LS), ("descriptionTerm", LS),
    ("descriptionTranslation", "sd28"),
    ("dynamicDescriptionTerm", LS), ("dynamicDescriptionTerms", "vls"),
    ("tags", "vi"), ("skillLevel", "i"),
    ("iconReference", "ar"), ("modelReference", "ar"), ("prefabReference", "ar"),
    ("huaSe", "i"), ("number", "i"), ("numberType", "i"), ("isZi", "b"),
    ("jian", "i"), ("count", "i"), ("maxCount", "f"), ("count2", "i"),
    ("isExceptBaoPai", "b"), ("isFeng", "b"), ("isRandomNumber", "b"),
    ("addSoul", "i"), ("feng", "i"), ("pattern", "i"), ("fanZhong", "i"),
    ("fanZhongList", "vi"), ("requiredCount", "i"), ("compareType", "i"),
    ("paiXingType", "i"), ("RoundArr", "vi"), ("UsedLimit", "i"),
    ("addBaseScore", "f"), ("addBaseScore2", "f"),
    ("addBaseMagnification", "f"), ("addBaseMagnification2", "f"),
    ("baseMultiIndependent", "f"), ("accMultiIndependent", "f"),
    ("addCoin", "f"), ("addCoin1", "f"), ("addFan", "f"), ("decline", "f"),
    ("addChou", "i"), ("addHp", "i"), ("addHpMax", "i"), ("addSwap", "i"),
    ("huPaiSlotsCount", "i"), ("maxValue", "f"), ("isPlayerSkill", "b"),
    ("baoLingDisplayPrefab", "p"),
    ("paiMianScore", "i"), ("multiple", "f"), ("percent", "f"), ("percentLimit", "f"),
    ("relicIds", "vi"), ("zhuFuGangCount", "i"), ("bossJiFenPaiKu", "p"),
    ("zhuFuPlayingCount", "i"), ("lianHuaPlayingCount", "i"), ("lianHuaPlayingCount2", "i"),
    # offeringInfo: struct { OfferingDisplay offeringDisplay(PPtr); int level }
    ("offeringInfo_display", "p"), ("offeringInfo_level", "i"),
    ("gameEvent", "p"),
]

OFFERING_SPEC = [
    ("displayId", "i"),
    ("displayNameTerm", LS), ("descriptionTerm", LS),
    ("offeringUsageTiming", "i"), ("level", "i"), ("icon", "p"),
    ("useType", "i"), ("handSelectType", "i"),
    ("baoPaiPayload", "p"), ("paiLingPayload", "p"),
    ("count", "i"), ("count2", "i"), ("discardLimitedCount", "i"),
    ("addBaseScore", "f"), ("addFan", "f"), ("addPaiMainNum", "f"),
    ("soulCost", "f"), ("accMultiIndependent", "f"),
    ("fanZhong", "i"), ("multi", "f"), ("range", "v2"),
    ("dynamicDescriptionTerms", "vls"),
]

CHARACTER_SPEC = [
    ("starLevel", "i"), ("characterID", "i"), ("skinId", "i"),
    ("roleAvatar", "p"),
    ("passiveSkill", "vp"), ("activeSkill", "vp"),
    ("fanZhongList", "vi"), ("skillUsageTiming", "i"),
    ("StartRelicEvent", "p"), ("targetPassiveXiaoChouDisplay", "p"),
    ("modelReference", "ar"), ("lingyongRewardsEvent", "p"),
    ("url_Walkthrough", "s"),
]

ACHIEVEMENT_SPEC = [
    ("id", "i"), ("guid", "s"), ("onlyId", "s"), ("index", "i"),
    ("displayName", "s"),
    ("displayNameTerm", LS), ("descriptionTerm", LS),
]

RELIC_SPEC = [
    ("displayId", "i"),
    ("displayNameTerm", LS), ("descriptionTerm", LS),
    ("rarity", "i"), ("addBaseScore", "f"), ("addFan", "i"),
    ("accMultiIndependent", "f"), ("coinCoefficient", "f"), ("coinCost", "i"),
    ("icon", "p"), ("tags", "vi"), ("_title", "p"), ("SameItemLoadCount", "i"),
]

ROLEAVATAR_SPEC = [
    ("characterID", "i"),
    ("localizedNameTerm", LS),
    ("displayName", "s"), ("displayDesc", "s"), ("intro", "s"),
    ("localizedDescTerm", LS), ("localizedIntroTerm", LS),
    ("localizedUnlockConditionTerm", LS),
    ("cardBGColorType", "i"),
    ("cardBGColor", "c4"), ("cardBGShading", "c4"), ("cardMaskColor", "c4"),
    ("miniHeadIcon", "p"), ("headIcon", "p"), ("simpleIcon", "p"),
    ("headIconBG", "c4"),
    ("tachie", "p"), ("detailsBG", "p"), ("tachieBagBG", "p"), ("tachieLastUsedBG", "p"),
    ("characterDevelopmentDub", "p"),
]

EVENTNODE_SPEC = [
    ("type", "i"), ("id", "s"), ("gameGuideObjectId", "i"),
    ("textContent", "s"), ("textContentTag", "s"),
    ("dubTag", "s"), ("dubStopTag", "s"),
    ("textAnchor", "i"), ("duration", "f"), ("boolMark", "b"),
    ("eventName", "s"), ("effectTiming", "i"), ("targetType", "i"),
    ("baseScore", "i"), ("fan", "i"), ("independent", "f"), ("hp", "i"),
    ("hun", "f"), ("ceiling", "b"), ("drawCount", "i"), ("huSlotCount", "i"),
    ("swapCount", "i"), ("floatValue", "f"),
    ("poolType", "i"), ("guaranteePoolType", "i"), ("globalDataType", "i"),
    ("calSymbol", "s"), ("gameObject", "p"),
    ("range", "v2"), ("position", "v3"), ("eulerAngles", "v3"), ("localScale", "v3"),
    ("stringValue", "s"),
    ("count", "i"), ("count2", "i"), ("totalCount", "i"), ("leastCount", "i"),
    ("fillFromWholePool", "b"), ("spriteGUID", "s"),
    ("selectType", "i"), ("randomType", "i"),
    ("rarities", "vi"), ("tags", "vi"),
    ("decisionSymbol", "s"), ("paiMianTypes", "vi"), ("paiMianDecisionSymbol", "s"),
    ("talentType", "i"), ("characterID", "i"), ("level", "i"), ("index", "i"),
    ("xiaoChouPaiGetList", "vp"), ("xiaoChouPaiPriorityList", "vp"),
    ("baoPai", "b"), ("paiLing", "b"),
    ("baoLingGetList", "vi"), ("baoLingGuaranteeList", "vi"), ("baoLingPriorityList", "vi"),
    ("relicGetList", "vi"), ("offeringGetList", "vi"),
    ("inventoryList", "p"), ("gameLevel", "p"), ("gameEvent", "p"),
    ("ports", "vp"), ("memo", "s"),
]

NODEPORT_SPEC = [
    ("type", "i"), ("targetNode", "s"),
    ("textContent", "s"), ("textContentTag", "s"),
    ("weight", "f"), ("level", "i"), ("needCost", "b"),
    ("resourceType", "i"), ("cost", "f"), ("delay", "f"), ("onlyID", "i"),
]

SPECS = {
    "EventNode": EVENTNODE_SPEC,
    "NodePort": NODEPORT_SPEC,
    "XiaoChouPaiPayload": XIAOCHOU_SPEC,
    "OfferingPayload": OFFERING_SPEC,
    "CharacterPayload": CHARACTER_SPEC,
    "AchievementPayload": ACHIEVEMENT_SPEC,
    "RelicDisplay": RELIC_SPEC,
    "RoleAvatar": ROLEAVATAR_SPEC,
}

# OfferingDisplay 及其具体子类(JiYuSkillDisplay 等): 基类字段在前, 只需前几个
OFFERINGDISPLAY_SPEC = [
    ("Payloads", "vp"), ("icon", "p"), ("btn", "p"),
]
SPECS["OfferingDisplay"] = OFFERINGDISPLAY_SPEC


def parse_payload(buf: bytes, cls: str, skip_header_name=False):
    """解析整个 MonoBehaviour。返回 (dict, fields_end_pos)。"""
    _, _, _, name, pos = mb_header(buf)
    d = {"m_Name": name}
    fields = parse_fields(buf, pos, SPECS[cls])
    d.update(fields)
    return d
