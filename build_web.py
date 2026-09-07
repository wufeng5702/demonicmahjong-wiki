#!/usr/bin/env python3
"""
Demonic Mahjong - 网页数据构建脚本
====================================
从游戏资源中提取 角色/灵佣/祭品/遗物/牌灵/宝牌/番种/业镜Buff/成就 的
ID、数值与游戏内文本，生成可离线搜索的本地网页 (site/)。

业镜Buff(YeJingBuff): boss 阎罗王的技能"业镜"所产生的 buff。

数据源:
  1. Addressables 主 bundle —— 全部 Payload 数据
  2. sharedassets1.assets —— I2 Localization 语言表 (6语言, ~4800词条, path_id 自动定位)
     类型树被剥离, 按序列化布局手工解析 (锚点定位法, 见 parse_i2_source)

使用方法:
    python build_web.py             # 完整构建（提取数据+生成网页, 约2-5分钟）
    python build_web.py --web-only  # 仅同步 web_src/ -> site/（改页面后快速刷新）

输出:
    web_src/data.json    - { categories, entries }
    output/site/         - 构建整个网页
"""

import io
import json
import datetime
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent / "lib"))

from UnityPy import AssetsManager
from UnityPy.enums import ClassIDType

import rawparse as rp

GAME_DIR = Path(r"E:\DemonicMahjong")
GAME_DATA_DIR = GAME_DIR / "DemonicMahjong" / "Demonic Mahjong_Data"
AA_DIR = GAME_DATA_DIR / "StreamingAssets/aa/StandaloneWindows64"
CATALOG = GAME_DATA_DIR / "StreamingAssets/aa/catalog.json"
SHARED1 = GAME_DATA_DIR / "sharedassets1.assets"
SHARED4 = GAME_DATA_DIR / "sharedassets4.assets"
DUMP_CS = GAME_DIR / "dump_output/dump.cs"
SITE_DIR = GAME_DIR / "site"

# 加载 .env
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    GAME_DIR = Path(os.environ.get("GAME_DIR", GAME_DIR))
    GAME_DATA_DIR = GAME_DIR / "Demonic Mahjong_Data"
    AA_DIR = GAME_DATA_DIR / "StreamingAssets/aa/StandaloneWindows64"
    CATALOG = GAME_DATA_DIR / "StreamingAssets/aa/catalog.json"
    SHARED1 = GAME_DATA_DIR / "sharedassets1.assets"
    SHARED4 = GAME_DATA_DIR / "sharedassets4.assets"
    DUMP_CS = Path(os.environ.get("DUMP_CS", GAME_DIR.parent / "dump_output/dump.cs"))
    SITE_DIR = Path(__file__).parent / "output" / "site"


def locate_bundle():
    """从 catalog.json 解析当前版本的主数据 bundle (defaultlocalgroup*)。
    游戏更新会换 hash 文件名 (32a5e3a2→e9b62c39), 旧 bundle 是残留文件勿用。"""
    try:
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        for x in cat.get("m_InternalIds", []):
            s = str(x).replace("\\", "/")
            name = s.rsplit("/", 1)[-1]
            if name.startswith("defaultlocalgroup") and name.endswith(".bundle"):
                p = AA_DIR / name
                if p.exists():
                    return p
    except Exception:
        pass
    hits = sorted(AA_DIR.glob("defaultlocalgroup*.bundle"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


BUNDLE_PATH = locate_bundle()
I2_OBJECT_PATH_ID = 13759  # I2 LanguageSource path_id 提示 (漂移时 locate_i2_object 自动纠正)


def locate_i2_object(bf):
    """自动定位 I2 LanguageSource: 最大的含 I2 key 模式的 MonoBehaviour。
    游戏更新会漂移 path_id (13761→13759), 不能硬编码。"""
    try:
        raw = bf.objects[I2_OBJECT_PATH_ID].get_raw_data()
        if len(raw) > 1_000_000 and b"/Name" in raw[:200000]:
            return I2_OBJECT_PATH_ID
    except Exception:
        pass
    best = None
    for pid, obj in bf.objects.items():
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            raw = obj.get_raw_data()
        except Exception:
            continue
        if len(raw) > 1_000_000 and b"/Name" in raw[:200000] and b"/Description" in raw:
            if best is None or len(raw) > best[1]:
                best = (pid, len(raw))
    return best[0] if best else None

# I2 词条的 6 种语言顺序: [简中, 英, 日, 繁中, ?, 韩]
LANG_ZH = 0
LANG_EN = 1


# ============================================================
# 枚举解析 (优先读 enums.json，回退到 dump.cs)
# ============================================================
def parse_all_enums(dump_path):
    # 优先读预提取的 enums.json（~50KB，已提交 git）
    enums_json = Path(__file__).parent / "assets" / "enums.json"
    if enums_json.exists():
        raw = json.loads(enums_json.read_text(encoding="utf-8"))
        print(f"  从 enums.json 加载枚举")
        # JSON keys are strings, convert back to int
        ev = {}
        for etype, mapping in raw["enum_values"].items():
            ev[etype] = {int(k): v for k, v in mapping.items()}
        return ev, raw["inspector_names"]

    # 回退: 从 dump.cs 解析（40MB，不提交 git）
    if not dump_path.exists():
        print(f"  [WARN] 未找到 enums.json 或 dump.cs，跳过枚举解析")
        return {}, {}
    print(f"  从 dump.cs 解析枚举（建议运行 python extract_enums.py 生成 enums.json）")
    enum_values = {}
    inspector_names = {}
    content = dump_path.read_text(encoding="utf-8", errors="replace")
    pat_inspector = (
        r'\[InspectorName\("([^"]+)"\)\]\s*\n\s*(?:\[[^\]]*\]\s*\n\s*)*'
        r"public const (\w+) (\w+) = (-?\d+);"
    )
    for m in re.finditer(pat_inspector, content):
        cn, etype, _fname, val = m.groups()
        inspector_names[f"{etype}.{int(val)}"] = cn
    pat_val = r"public const (\w+) (\w+) = (-?\d+);"
    for m in re.finditer(pat_val, content):
        etype, fname, val = m.groups()
        enum_values.setdefault(etype, {})[int(val)] = fname
    return enum_values, inspector_names


RARITY_CN = {1: "普通", 2: "稀有", 3: "史诗", 4: "传说", 5: "限定"}

TAG_CN = {
    "Chi": "吃", "Peng": "碰", "GangZi": "杠子", "KeZi": "刻子",
    "ShunZi": "顺子", "DuiZi": "对子", "MenQianQing": "门前清", "Hu": "和牌",
    "Wan": "万", "Tong": "筒", "Suo": "索", "Zi": "字", "Feng": "风",
    "SanYuan": "三元", "Hun": "魂力", "Number": "数牌", "BaoPai": "宝牌",
    "ExtraPai": "额外牌", "PaiBaseScore": "牌基础分",
    "BossPassiveSkill": "BOSS被动", "BossActiveSkill": "BOSS主动",
    "BossLingYong": "BOSS灵佣", "LingYong": "灵佣",
    "KeJiFenDeLingYong": "可计分", "Offering": "祭品",
    "PaiLing": "牌灵", "NianLing": "念灵", "Minion": "小妖", "Doll": "娃娃",
    "FigureGui": "鬼俑", "FigureRen": "人俑",
    "Coin": "金币", "CoinEnhance": "金币强化", "Derive": "衍生",
    "Play": "打出", "Grow": "成长", "EmptyNest": "空巢",
    "Bird": "鸟", "Fox": "狐", "Loong": "龙", "Ox": "牛",
    "Cat": "猫", "Dog": "狗", "Monkey": "猴", "Horse": "马",
    "Snake": "蛇", "Rabbit": "兔", "Turtle": "龟", "Crane": "鹤",
    "Pig": "猪", "Elephant": "象", "Mouse": "鼠", "Fish": "鱼",
    "HuXian": "狐仙", "FourPerils": "四凶", "Toxic": "毒",
    "FengGuai": "风怪", "DiXian": "地仙", "Xian": "仙",
    "Odd": "奇数", "Even": "偶数", "Egg": "蛋", "Candle": "蜡烛",
    "HP": "血量", "DrawCount": "摸牌数",
    "Container": "容器", "Independent": "独立", "PayedEnhance": "付费强化",
}

TAG_ID_CN = {
    14: "万", 15: "筒", 16: "索", 17: "字", 20: "风",
    31: "三元", 40: "对子", 41: "刻子", 42: "顺子", 43: "杠子",
    44: "奇数", 45: "偶数", 52: "打出", 53: "吃", 54: "碰", 57: "和牌",
    60: "血量", 61: "魂力", 62: "金币", 65: "独立",
    71: "牌基础分", 73: "摸牌数",
    100: "门前清", 551: "衍生",
    1000: "灵佣", 1001: "BOSS灵佣",
    3000: "祭品", 4000: "宝牌",
    5000: "牌灵", 5200: "念灵",
    7000: "额外牌",
    10001: "鼠", 10002: "牛", 10004: "兔", 10005: "龙",
    10006: "蛇", 10007: "马", 10009: "猴",
    10011: "狗", 10012: "猪", 10013: "猫", 10014: "鸟",
    10015: "鹤", 10016: "龟", 10017: "鱼", 10018: "狐", 10019: "象",
    30002: "小妖",
    33000: "仙", 33501: "地仙", 33601: "狐仙",
    35001: "风怪", 35002: "四凶", 36000: "可计分",
    40002: "人俑", 40003: "鬼俑", 40004: "娃娃",
    48001: "蜡烛", 49003: "空巢",
    49500: "蛋",
    50001: "成长", 52100: "金币强化", 52101: "金币强化",
    57000: "毒",
    60000: "BOSS主动", 60001: "BOSS被动",
    60010: "仅技能", 60011: "仅主动技能", 60012: "仅被动技能",
    60500: "仅灵佣", 69999: "通用",
}


def _resolve_tag(raw_tags, enum_values=None):
    if not raw_tags:
        return []
    if enum_values:
        tag_enum = enum_values.get("Tag", {})
        if tag_enum:
            return [TAG_CN.get(tag_enum.get(int(t), ""), tag_enum.get(int(t), str(t))) for t in raw_tags]
    return [TAG_ID_CN.get(int(t), str(t)) for t in raw_tags]


def rarity_name(v, inspector_names):
    return inspector_names.get(f"Rarity.{v}") or RARITY_CN.get(v, str(v))


# ============================================================
# I2 LanguageSource 手工解析
# ============================================================
KEY_SEG_RE = re.compile(rb"[A-Za-z0-9][A-Za-z0-9_.\-]*(?:\s*/[A-Za-z0-9][A-Za-z0-9_.\-]*)+")
VALID_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*(?:\s*/[A-Za-z0-9][A-Za-z0-9_.\-]*)+$")


def parse_i2_source(raw):
    """从 MonoBehaviour 原始字节解析 I2 LanguageSource 的 mTerms。

    布局(类型树被剥离, 由字节分析得出):
      header(28) + m_Name("") + bool*4 + mTerms.count
      每 TermData: Term(str) [TermType(i32)?] Description(str)
                   Languages(vec<str>) Flags(vec<u8>) Languages_Touch(vec<str>)
    由于个别词条含额外字段导致顺序解析漂移,
    采用"锚点"(长度前缀+合法key模式)定位每个 Term 再逐个验证解析。
    """
    anchors = []
    for m in KEY_SEG_RE.finditer(raw):
        s, e = m.span()
        if s < 44:
            continue
        if struct.unpack_from("<i", raw, s - 4)[0] != e - s:
            continue
        raw_key = m.group().decode("ascii")
        key = re.sub(r'\s+', '', raw_key)
        if VALID_KEY_RE.match(key):
            anchors.append((s, key, e - s))
    anchors.sort()

    def rd_str(p):
        n = struct.unpack_from("<i", raw, p)[0]
        if n < 0 or n > 1_000_000:
            raise ValueError(f"bad strlen {n}@{p}")
        v = raw[p + 4:p + 4 + n].decode("utf-8", "replace")
        return v, p + 4 + n + ((-(p + 4 + n)) % 4)

    def parse_at(koff, klen):
        kend = koff + ((klen + 3) // 4 * 4)
        best = None
        for skip_type in (0, 4):  # 布局A / 布局B(含TermType)
            p = kend + skip_type
            try:
                _, p = rd_str(p)  # Description
                nl = struct.unpack_from("<i", raw, p)[0]
                p += 4
                if not 3 <= nl <= 8:
                    raise ValueError("nl")
                langs = []
                for _ in range(nl):
                    t, p = rd_str(p)
                    langs.append(t)
                nf = struct.unpack_from("<i", raw, p)[0]
                p += 4
                if not 0 <= nf <= 16:
                    raise ValueError("nf")
                p += nf + (-p % 4)
                nt = struct.unpack_from("<i", raw, p)[0]
                p += 4
                if not 0 <= nt <= 10:
                    raise ValueError("nt")
                for _ in range(nt):
                    _, p = rd_str(p)
                score = sum(len(x) for x in langs)
                cand = (langs, p, skip_type)
                if best is None or score > best[1]:
                    best = (cand[0], score, skip_type)
                if skip_type == 0:
                    break
            except Exception:
                continue
        return best[0] if best else None

    terms = {}
    ok = fail = 0
    for koff, key, raw_klen in anchors:
        langs = parse_at(koff, raw_klen)
        if langs is None:
            fail += 1
            continue
        ok += 1
        prev = terms.get(key)
        if prev is None or sum(map(len, langs)) > sum(map(len, prev)):
            terms[key] = langs
    return terms, ok, fail


def load_i2_terms():
    am = AssetsManager()
    bf = am.load_file(str(SHARED1))
    pid = locate_i2_object(bf)
    if pid is None:
        raise RuntimeError("未找到 I2 LanguageSource (sharedassets1 中无匹配对象)")
    if pid != I2_OBJECT_PATH_ID:
        print(f"  [warn] I2 path_id 漂移: {I2_OBJECT_PATH_ID} -> {pid} (已自动定位)")
    raw = bf.objects[pid].get_raw_data()
    terms, ok, fail = parse_i2_source(raw)
    print(f"  I2 terms parsed: {ok} ok, {fail} failed anchors -> {len(terms)} unique keys")
    return terms


def tr(term_key, i2):
    """取词条文本: 优先简中, 回退英文。"""
    if not term_key:
        return ""
    langs = i2.get(term_key)
    if not langs:
        langs = i2.get(re.sub(r'\s+', '', term_key))
    if not langs:
        return None  # 未命中 (与空串区分)
    zh = langs[LANG_ZH].strip()
    if zh:
        return clean_markup(zh)
    en = langs[LANG_EN].strip()
    return clean_markup(en) if en else ""


TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")


def clean_markup(s):
    """清洗 I2 内联标记: <Term Default=47>三元牌</Term> -> 三元牌"""
    if not s:
        return s
    return TAG_RE.sub("", s)


# ============================================================
# 主 bundle 提取
# ============================================================
def script_name(data):
    ms = getattr(data, "m_Script", None)
    if ms is None:
        return "?"
    try:
        return getattr(ms.read(), "m_ClassName", "?")
    except Exception:
        return "?"


def term_key_of(val):
    if val is not None and hasattr(val, "mTerm"):
        return val.mTerm or ""
    return ""


def fnum(v):
    """浮点转 int(当为整值时) 以精简输出。"""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def collect_adds(d, fields):
    out = {}
    for f in fields:
        try:
            v = getattr(d, f)
        except Exception:
            continue
        if isinstance(v, (int, float)) and v != 0:
            out[f] = fnum(v)
    return out


XIAOCHOU_ADD_FIELDS = [
    "addBaseScore", "addBaseScore2", "addBaseMagnification", "addBaseMagnification2",
    "baseMultiIndependent", "accMultiIndependent", "multiple", "addFan",
    "addCoin", "addCoin1", "addSoul", "addHp", "addHpMax", "addSwap", "addChou",
    "count", "count2", "percent", "percentLimit", "decline", "maxValue", "maxCount",
]
OFFERING_ADD_FIELDS = ["soulCost", "addBaseScore", "addFan", "addPaiMainNum", "multi",
                       "accMultiIndependent", "count", "count2"]


def extract_bundle(enum_values, inspector_names):
    print("  loading main bundle...")
    am = AssetsManager()
    # 新版游戏将脚本元数据拆到独立 monoscripts bundle，需先加载
    for ms_bf in AA_DIR.glob("*_monoscripts_*.bundle"):
        am.load_file(str(ms_bf))
        print(f"  loaded monoscripts: {ms_bf.name}")
        break
    bf = am.load_file(str(BUNDLE_PATH))
    cab_keys = [k for k in bf.files if k.startswith("CAB-")]
    sf = bf.files[cab_keys[0]]
    print(f"  objects: {len(sf.objects)}")

    KNOWN_PAYLOAD_CLASSES = {
        "CharacterPayload", "XiaoChouPaiPayload", "OfferingPayload",
        "FanZhongPayload", "AchievementPayload", "PaiLingPayload",
        "BaoPaiPayload", "YeJingBuffPayload",
    }
    relic_loose = []
    buckets = {}
    for pid, obj in sf.objects.items():
        if obj.type != ClassIDType.MonoBehaviour:
            continue
        try:
            d = obj.read()
            sn = script_name(d)
        except Exception:
            continue
        if sn and sn != "?":
            b = buckets.setdefault(sn, [])
            b.append((pid, d))
            # 游离遗物: 不在已知 payload 类里但有 RelicDisplay 特征字段 (需求 #26)
            if (sn not in KNOWN_PAYLOAD_CLASSES
                    and sn not in ("Dlc_RelicDisplayList", "Dlc_RelicDisplayMysteriousList")
                    and getattr(d, "displayId", None) is not None
                    and hasattr(d, "SameItemLoadCount")):
                relic_loose.append((pid, d))

    counts = {
        k: len(v) for k, v in buckets.items()
        if k in ("CharacterPayload", "XiaoChouPaiPayload", "OfferingPayload", "FanZhongPayload",
                 "PaiLingPayload", "BaoPaiPayload", "YeJingBuffPayload", "AchievementPayload")
    }
    print(f"  payloads: {counts}")

    data = {"lingyong": [], "offerings": [], "relics": [], "characters": [],
            "pailing": [], "baopai": [], "fanzhong": [], "yejingbuff": [], "achievements": []}

    # ---- 灵佣 (小丑牌) ----
    xc_enum = enum_values.get("XiaoChou", {})
    seen_xc = set()
    for pid, d in buckets.get("XiaoChouPaiPayload", []):
        xid = int(getattr(d, "id", 0))
        ic = getattr(d, "iconReference", None)
        guid = getattr(ic, "m_AssetGUID", "") if ic is not None else ""
        nk = term_key_of(getattr(d, "displayNameTerm", None))
        dk = term_key_of(getattr(d, "descriptionTerm", None))
        raw_tags = getattr(d, "tags", []) or []
        tags = _resolve_tag(raw_tags, enum_values)
        fan_list = [int(x) for x in (getattr(d, "fanZhongList", []) or [])]
        entry = {
            "id": xid,
            "en": xc_enum.get(xid, getattr(d, "m_Name", "")),
            "rarity": int(getattr(d, "rarity", 0)),
            "level": int(getattr(d, "skillLevel", 0)),
            "nameKey": nk, "descKey": dk,
            "iconGUID": guid,
            "adds": collect_adds(d, XIAOCHOU_ADD_FIELDS),
            "fanZhong": int(getattr(d, "fanZhong", 0)),
            "fanList": fan_list,
            "relicIds": [int(x) for x in (getattr(d, "relicIds", []) or [])],
            "huaSe": int(getattr(d, "huaSe", 0)),
            "number": int(getattr(d, "number", 0)),
            "isZi": bool(getattr(d, "isZi", 0)),
            "tags": [str(t) for t in tags],
        }
        data["lingyong"].append(entry)
        seen_xc.add(xid)

    # ---- 祭品 ----
    off_enum = enum_values.get("Offering", {})
    for pid, d in buckets.get("OfferingPayload", []):
        oid = int(getattr(d, "displayId", 0))
        data["offerings"].append({
            "id": oid,
            "en": off_enum.get(oid, getattr(d, "m_Name", "")),
            "level": int(getattr(d, "level", 0)),
            "nameKey": term_key_of(getattr(d, "displayNameTerm", None)),
            "descKey": term_key_of(getattr(d, "descriptionTerm", None)),
            "adds": collect_adds(d, OFFERING_ADD_FIELDS),
            "fanZhong": int(getattr(d, "fanZhong", 0)),
            "useTiming": int(getattr(d, "offeringUsageTiming", 0)),
            "useType": int(getattr(d, "useType", 0)),
        })

    # ---- 遗物 (经 Dlc_RelicDisplay*List 间接引用) ----
    # 注意: 神秘列表要打 kind 标签, 否则与 shared4 的神秘遗物合并时产生重复 (需求 #23)
    relic_bundle = {}
    for list_sn, kind in (("Dlc_RelicDisplayList", ""), ("Dlc_RelicDisplayMysteriousList", "神秘")):
        for pid, d in buckets.get(list_sn, []):
            vl = getattr(d, "value", [])
            if not isinstance(vl, list):
                continue
            for ref in vl:
                rpid = getattr(ref, "path_id", None)
                if rpid is None or rpid not in sf.objects:
                    continue
                try:
                    rd = sf.objects[rpid].read()
                    did = int(getattr(rd, "displayId", 0))
                    sn = script_name(rd)
                    k2 = ("诅咒" if sn in CURSED_RELIC_SCRIPTS else
                          "神秘" if sn in MYSTERIOUS_RELIC_SCRIPTS else kind)
                    relic_bundle[(did, k2)] = (rd, rpid)
                except Exception:
                    pass
    relic_enum = enum_values.get("RelicId", {})
    seen_rids = set()
    for (did, kind), (rd, rpid) in relic_bundle.items():
        seen_rids.add(did)
        data["relics"].append({
            "id": did,
            "en": relic_enum.get(did, ""),
            "cn": inspector_names.get(f"RelicId.{did}", ""),
            "nameKey": term_key_of(getattr(rd, "displayNameTerm", None)),
            "descKey": term_key_of(getattr(rd, "descriptionTerm", None)),
            "rarity": int(getattr(rd, "rarity", 0)),
            "stack": int(getattr(rd, "SameItemLoadCount", 0)),
            "kind": kind,
            "icon_pid": rpid,  # RelicDisplay 对象, 供图标导出解析 icon 字段
            "src": "bundle",
        })
    for pid, rd in relic_loose:
        did = int(getattr(rd, "displayId", 0))
        if did == 0 or did in seen_rids:
            continue
        seen_rids.add(did)
        sn = script_name(rd)
        data["relics"].append({
            "id": did,
            "en": relic_enum.get(did, ""),
            "cn": inspector_names.get(f"RelicId.{did}", ""),
            "nameKey": term_key_of(getattr(rd, "displayNameTerm", None)),
            "descKey": term_key_of(getattr(rd, "descriptionTerm", None)),
            "rarity": int(getattr(rd, "rarity", 0)),
            "stack": int(getattr(rd, "SameItemLoadCount", 0)),
            "kind": ("诅咒" if sn in CURSED_RELIC_SCRIPTS else
                     "神秘" if sn in MYSTERIOUS_RELIC_SCRIPTS else ""),
            "icon_pid": pid,
            "src": "bundle",
        })
    for rid in sorted(relic_enum.keys()):
        if rid == 0 or rid in seen_rids:
            continue
        data["relics"].append({
            "id": rid, "en": relic_enum.get(rid, ""),
            "cn": inspector_names.get(f"RelicId.{rid}", ""),
            "nameKey": "", "descKey": "", "rarity": 0, "stack": 0, "kind": "",
            "src": "enum",
        })

    # ---- 牌灵 / 宝牌 / 业镜Buff / 成就 / 番种 ----
    def simple(bucket, id_attr, cat):
        for pid, d in buckets.get(bucket, []):
            oid = int(getattr(d, id_attr, getattr(d, "displayId", 0)) or 0)
            adds = collect_adds(d, XIAOCHOU_ADD_FIELDS + OFFERING_ADD_FIELDS)
            data[cat].append({
                "id": oid,
                "en": getattr(d, "m_Name", ""),
                "nameKey": term_key_of(getattr(d, "displayNameTerm", None)),
                "descKey": term_key_of(getattr(d, "descriptionTerm", None)),
                "adds": adds,
            })

    simple("PaiLingPayload", "id", "pailing")
    simple("BaoPaiPayload", "id", "baopai")
    simple("YeJingBuffPayload", "id", "yejingbuff")

    for pid, d in buckets.get("AchievementPayload", []):
        nk = term_key_of(getattr(d, "displayNameTerm", None))
        dk = term_key_of(getattr(d, "descriptionTerm", None))
        if not nk and not dk:
            continue  # 跳过无文本的测试占位
        m = re.match(r"^(\d+)", getattr(d, "m_Name", ""))
        data["achievements"].append({
            "id": int(m.group(1)) if m else int(getattr(d, "id", 0)),
            "en": getattr(d, "m_Name", ""),
            "nameKey": nk,
            "descKey": dk,
        })

    fz_enum = enum_values.get("FanZhong", {})
    for pid, d in buckets.get("FanZhongPayload", []):
        fid = int(getattr(d, "id", 0))
        data["fanzhong"].append({
            "id": fid,
            "en": getattr(d, "m_Name", ""),
            "cn": inspector_names.get(f"FanZhong.{fid}", ""),
            "fan": int(getattr(d, "fan", 0)),
            "series": int(getattr(d, "series", 0)),
            "isDefault": bool(getattr(d, "isDefault", 0)),
            "paiNames": [str(x) for x in (getattr(d, "paiNames", []) or [])][:14],
            "nameKey": term_key_of(getattr(d, "displayNameTerm", None)),
            "descKey": term_key_of(getattr(d, "descriptionTerm", None)),
        })

    # ---- 角色 (含被动/主动技能解析) ----
    char_payloads = {}
    for pid, d in buckets.get("CharacterPayload", []):
        cid = int(getattr(d, "characterID", 0))
        char_payloads[cid] = (pid, d)

    char_enum = enum_values.get("CharacterID", {})
    skill_cache = {}

    def read_obj(rpid):
        if rpid in skill_cache:
            return skill_cache[rpid]
        if rpid not in sf.objects:
            skill_cache[rpid] = None
            return None
        try:
            d = sf.objects[rpid].read()
            skill_cache[rpid] = d
            return d
        except Exception:
            skill_cache[rpid] = None
            return None

    all_cids = sorted(set(char_payloads.keys()) | (set(char_enum.keys()) - {0}))
    for cid in all_cids:
        if cid == 0:
            continue
        entry = {
            "id": cid,
            "en": char_enum.get(cid, ""),
            "cn": inspector_names.get(f"CharacterID.{cid}", ""),
            "star": 0, "skin": 0,
            "passives": [], "actives": [],
            "fanList": [],
            "src": "enum",
        }
        payload = char_payloads.get(cid)
        if payload is not None:
            _, d = payload
            entry["star"] = int(getattr(d, "starLevel", 0))
            entry["skin"] = int(getattr(d, "skinId", 0))
            entry["fanList"] = [int(x) for x in (getattr(d, "fanZhongList", []) or [])]
            entry["src"] = "bundle"
            # 被动技能: XiaoChou 脚本对象, 自带 LingYong 词条
            for ref in (getattr(d, "passiveSkill", []) or []):
                sd = read_obj(getattr(ref, "path_id", None))
                if sd is None:
                    continue
                sid = int(getattr(sd, "id", 0))
                entry["passives"].append({
                    "id": sid,
                    "nameKey": term_key_of(getattr(sd, "displayNameTerm", None)),
                    "descKey": term_key_of(getattr(sd, "descriptionTerm", None)),
                    "adds": collect_adds(sd, XIAOCHOU_ADD_FIELDS),
                })
            # 主动技能: OfferingDisplay 对象, Payloads[] → OfferingPayload
            for ref in (getattr(d, "activeSkill", []) or []):
                od = read_obj(getattr(ref, "path_id", None))
                if od is None:
                    continue
                for pr in (getattr(od, "Payloads", []) or []):
                    pd = read_obj(getattr(pr, "path_id", None))
                    if pd is None:
                        continue
                    entry["actives"].append({
                        "id": int(getattr(pd, "displayId", 0)),
                        "level": int(getattr(pd, "level", 0)),
                        "nameKey": term_key_of(getattr(pd, "displayNameTerm", None)),
                        "descKey": term_key_of(getattr(pd, "descriptionTerm", None)),
                        "adds": collect_adds(pd, OFFERING_ADD_FIELDS),
                    })
        data["characters"].append(entry)

    return data


# ============================================================
# 本体数据提取 (sharedassets1/4, 类型树被剥离 → rawparse 手工解析)
# ============================================================
def classify_monobehaviours(sf):
    """按 MonoScript 类名分类所有 MonoBehaviour (不解析 body)。
    返回 {class_name: [path_id]}, 以及 {path_id: class_name}。"""
    by_cls, by_pid = {}, {}
    for pid, obj in sf.objects.items():
        if obj.type != ClassIDType.MonoBehaviour:
            continue
        try:
            d = obj.read(check_read=False)
            ms = getattr(d, "m_Script", None)
            sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
        except Exception:
            continue
        by_cls.setdefault(sn, []).append(pid)
        by_pid[pid] = sn
    return by_cls, by_pid


def extract_shared_assets(enum_values):
    """从 sharedassets1/4 提取本体数据。
    返回 dict: lingyong/offerings/achievements/characters/relics + relic_kind 映射"""
    print("  loading sharedassets1 ...")
    am1 = AssetsManager()
    bf1 = am1.load_file(str(SHARED1))
    sf1 = bf1
    cls1, pid1 = classify_monobehaviours(sf1)

    out = {"lingyong": [], "offerings": [], "achievements": [], "characters": [],
           "relics": [], "relic_kinds": {}}

    def parse_one(sf, pid, cls):
        raw = sf.objects[pid].get_raw_data()
        return rp.parse_payload(raw, cls)

    # ---- sharedassets1: 灵佣 / 祭品 / 成就 ----
    for pid in cls1.get("XiaoChouPaiPayload", []):
        try:
            d = parse_one(sf1, pid, "XiaoChouPaiPayload")
            if int(d.get("id", 0)) == 0:
                continue  # 测试/占位 payload
        except Exception:
            continue
        out["lingyong"].append(_xc_from_raw(d, enum_values))
    for pid in cls1.get("OfferingPayload", []):
        try:
            d = parse_one(sf1, pid, "OfferingPayload")
        except Exception:
            continue
        out["offerings"].append(_offering_from_raw(d))
    for pid in cls1.get("AchievementPayload", []):
        try:
            d = parse_one(sf1, pid, "AchievementPayload")
        except Exception:
            continue
        nk = d.get("displayNameTerm", "") or ""
        dk = d.get("descriptionTerm", "") or ""
        if not nk and not dk:
            continue
        m = re.match(r"^(\d+)", d.get("m_Name", ""))
        out["achievements"].append({
            "id": int(m.group(1)) if m else int(d.get("id", 0)),
            "en": d.get("m_Name", ""),
            "nameKey": nk,
            "descKey": dk,
            "src": "shared",
        })
    n1 = {k: len(v) for k, v in out.items() if isinstance(v, list)}
    print(f"  shared1 parsed: {n1}")

    # ---- sharedassets4: 角色 / 遗物 / RoleAvatar / 灵佣·祭品补充 ----
    print("  loading sharedassets4 ...")
    am4 = AssetsManager()
    sf4 = am4.load_file(str(SHARED4))
    cls4, pid4 = classify_monobehaviours(sf4)

    # 灵佣(含本体BOSS) 与 祭品 补充
    for pid in cls4.get("XiaoChouPaiPayload", []):
        try:
            d = parse_one(sf4, pid, "XiaoChouPaiPayload")
            if int(d.get("id", 0)) == 0:
                continue
        except Exception:
            continue
        out["lingyong"].append(_xc_from_raw(d, enum_values))
    for pid in cls4.get("OfferingPayload", []):
        try:
            d = parse_one(sf4, pid, "OfferingPayload")
        except Exception:
            continue
        out["offerings"].append(_offering_from_raw(d))
    for pid in cls4.get("AchievementPayload", []):
        try:
            d = parse_one(sf4, pid, "AchievementPayload")
        except Exception:
            continue
        nk = d.get("displayNameTerm", "") or ""
        dk = d.get("descriptionTerm", "") or ""
        if not nk and not dk:
            continue
        m = re.match(r"^(\d+)", d.get("m_Name", ""))
        out["achievements"].append({
            "id": int(m.group(1)) if m else int(d.get("id", 0)),
            "en": d.get("m_Name", ""),
            "nameKey": nk,
            "descKey": dk,
            "src": "shared4",
        })
    n4 = {"lingyong": len(cls4.get("XiaoChouPaiPayload", [])),
          "offerings": len(cls4.get("OfferingPayload", [])),
          "achievements": len(cls4.get("AchievementPayload", []))}
    print(f"  shared4 payloads: {n4}")

    # 角色名映射: 从 RoleAvatar 提取 I2 localizedNameTerm (UnityPy 无法读取 RoleAvatar，需用 rawparse)
    avatar_name_keys = {}
    for o in sf4.objects.values():
        if o.type.name != "MonoBehaviour":
            continue
        try:
            raw = o.get_raw_data()
            d2 = rp.parse_payload(raw, "RoleAvatar")
            cid = int(d2.get("characterID", 0))
            lnt = str(d2.get("localizedNameTerm", ""))
            if cid and lnt.startswith("RoleAvatar/"):
                avatar_name_keys[cid] = lnt
        except Exception:
            pass
    print(f"  avatar name keys: {len(avatar_name_keys)}")

    # 角色
    for pid in cls4.get("CharacterPayload", []):
        try:
            d = parse_one(sf4, pid, "CharacterPayload")
        except Exception:
            continue
        entry = _character_from_raw(d)
        entry["nameKey"] = avatar_name_keys.get(entry["id"], "")
        # 解析技能引用 (同文件内)
        passives = []
        for ref in d.get("passiveSkill", []) or []:
            tpid = (ref or {}).get("path_id")
            if tpid and pid4.get(tpid) == "XiaoChouPaiPayload":
                try:
                    sd = parse_one(sf4, tpid, "XiaoChouPaiPayload")
                    passives.append(_skill_from_raw(sd))
                except Exception:
                    pass
        actives = []
        for ref in d.get("activeSkill", []) or []:
            tpid = (ref or {}).get("path_id")
            if not tpid:
                continue
            try:
                od = parse_one(sf4, tpid, "OfferingDisplay")
                for pref in od.get("Payloads", []) or []:
                    ppid = (pref or {}).get("path_id")
                    if ppid and pid4.get(ppid) == "OfferingPayload":
                        pd = parse_one(sf4, ppid, "OfferingPayload")
                        actives.append(_offskill_from_raw(pd))
            except Exception:
                pass
        entry["passives"] = passives
        entry["actives"] = actives
        entry["src"] = "shared"
        out["characters"].append(entry)
    print(f"  shared4 characters: {len(out['characters'])}")

    # 遗物: 三个本体列表 (普通/神秘/外乡人)
    for list_name, kind in (("RelicDisplayList", ""), ("RelicDisplayMysteriousList", "神秘"),
                            ("RelicDisplayOutsiderList", "外乡人")):
        for lpid in cls4.get(list_name, []):
            try:
                raw = sf4.objects[lpid].get_raw_data()
                _, _, _, _, pos = rp.mb_header(raw)
                vals = rp.parse_fields(raw, pos, [("value", "vp")])["value"]
            except Exception as e:
                print(f"  {list_name} parse fail: {e}")
                continue
            for ref in vals:
                rpid = (ref or {}).get("path_id")
                if not rpid or rpid not in sf4.objects:
                    continue
                try:
                    rd = parse_one(sf4, rpid, "RelicDisplay")
                except Exception:
                    continue
                script_sn = pid4.get(rpid, "")
                kind2 = kind or ("诅咒" if script_sn in CURSED_RELIC_SCRIPTS else
                                 "神秘" if script_sn in MYSTERIOUS_RELIC_SCRIPTS else "")
                rid = int(rd.get("displayId", 0))
                out["relics"].append({
                    "id": rid,
                    "en": "",
                    "cn": "",
                    "nameKey": rd.get("displayNameTerm", "") or "",
                    "descKey": rd.get("descriptionTerm", "") or "",
                    "rarity": int(rd.get("rarity", 0)),
                    "stack": int(rd.get("SameItemLoadCount", 0)),
                    "src": "shared",
                    "kind": kind2,
                    "icon_pid": (rd.get("icon") or {}).get("path_id"),
                })
    print(f"  shared4 relics: {len(out['relics'])}")
    return out


def _xc_from_raw(d, enum_values=None):
    """rawparse 的 XiaoChouPaiPayload dict → lingyong 条目"""
    adds = {}
    for f in XIAOCHOU_ADD_FIELDS:
        v = d.get(f)
        if isinstance(v, (int, float)) and v:
            adds[f] = int(v) if float(v).is_integer() else round(v, 4)
    ic = d.get("iconReference") or {}
    raw_tags = d.get("tags") or []
    tags = _resolve_tag(raw_tags, enum_values)
    return {
        "id": int(d.get("id", 0)),
        "en": d.get("m_Name", ""),
        "rarity": int(d.get("rarity", 0)),
        "level": int(d.get("skillLevel", 0)),
        "nameKey": d.get("displayNameTerm", "") or "",
        "descKey": d.get("descriptionTerm", "") or "",
        "iconGUID": ic.get("guid", "") if isinstance(ic, dict) else "",
        "adds": adds,
        "fanZhong": int(d.get("fanZhong", 0)),
        "fanList": [int(x) for x in (d.get("fanZhongList") or [])],
        "relicIds": [int(x) for x in (d.get("relicIds") or [])],
        "huaSe": int(d.get("huaSe", 0)),
        "number": int(d.get("number", 0)),
        "isZi": bool(d.get("isZi")),
        "tags": tags,
        "src": "shared",
    }


def _offering_from_raw(d):
    adds = {}
    for f in OFFERING_ADD_FIELDS:
        v = d.get(f)
        if isinstance(v, (int, float)) and v:
            adds[f] = int(v) if float(v).is_integer() else round(v, 4)
    icon = d.get("icon") or {}
    return {
        "id": int(d.get("displayId", 0)),
        "en": d.get("m_Name", ""),
        "level": int(d.get("level", 0)),
        "nameKey": d.get("displayNameTerm", "") or "",
        "descKey": d.get("descriptionTerm", "") or "",
        "adds": adds,
        "fanZhong": int(d.get("fanZhong", 0)),
        "useTiming": int(d.get("offeringUsageTiming", 0)),
        "useType": int(d.get("useType", 0)),
        "icon_pid": icon.get("path_id"),
        "src": "shared",
    }


def _offskill_from_raw(d):
    """角色主动技能的 OfferingPayload (来自 OfferingDisplay.Payloads)"""
    adds = {}
    for f in OFFERING_ADD_FIELDS:
        v = d.get(f)
        if isinstance(v, (int, float)) and v:
            adds[f] = int(v) if float(v).is_integer() else round(v, 4)
    return {
        "id": int(d.get("displayId", 0)),
        "level": int(d.get("level", 0)),
        "nameKey": d.get("displayNameTerm", "") or "",
        "descKey": d.get("descriptionTerm", "") or "",
        "adds": adds,
    }


def _skill_from_raw(d):
    """角色被动技能 (XiaoChou 脚本对象)"""
    adds = {}
    for f in XIAOCHOU_ADD_FIELDS:
        v = d.get(f)
        if isinstance(v, (int, float)) and v:
            adds[f] = int(v) if float(v).is_integer() else round(v, 4)
    return {
        "id": int(d.get("id", 0)),
        "nameKey": d.get("displayNameTerm", "") or "",
        "descKey": d.get("descriptionTerm", "") or "",
        "adds": adds,
    }


def _character_from_raw(d):
    return {
        "id": int(d.get("characterID", 0)),
        "en": "",
        "cn": "",
        "nameKey": "",
        "star": int(d.get("starLevel", 0)),
        "skin": int(d.get("skinId", 0)),
        "passives": [], "actives": [],
        "fanList": [int(x) for x in (d.get("fanZhongList") or [])],
        "roleAvatar_pid": (d.get("roleAvatar") or {}).get("path_id"),
        "src": "shared",
    }
def offering_category(oid):
    """祭品分类 (用户需求#10): 按 Offering 枚举区间划分。"""
    if 10000 <= oid < 20000:
        return "奶茶"
    if 20000 <= oid < 30000:
        return "角色技能"
    if 1 <= oid <= 10:
        return "水果"
    if 11 <= oid <= 24:
        return "花草"
    if 25 <= oid <= 35:
        return "糕点"
    if 36 <= oid <= 37:
        return "花草"  # #34: 菘蓝/三色花
    return "其他"


def merge_shared(data, shared, inspector_names, relic_enum):
    """把本体数据合并进 DLC 数据: 同 ID 以 bundle(DLC/更新) 为准, 其余追加。"""
    def union(cat, keyfn):
        existing = {keyfn(e): e for e in data[cat]}
        added = 0
        for e in shared.get(cat, []):
            k = keyfn(e)
            if k in existing:
                continue
            data[cat].append(e)
            existing[k] = e
            added += 1
        print(f"  merge {cat}: +{added} from shared")

    union("lingyong", lambda e: (e["id"], e["level"]))
    union("offerings", lambda e: (e["id"], e["level"]))
    union("achievements", lambda e: e["en"])

    # 角色: 按 characterID 合并。
    # bundle 提取时为全部枚举 ID 生成了占位条目(src=enum);
    # 本体(shared)数据替换 enum 占位, 但不动真正的 DLC 数据(src=bundle)。
    by_id = {}
    for ch in list(data["characters"]):
        by_id.setdefault(ch["id"], []).append(ch)
    for ch in shared.get("characters", []):
        olds = by_id.get(ch["id"], [])
        has_real_bundle = any(o.get("src") == "bundle" for o in olds)
        if has_real_bundle:
            continue
        for o in olds:
            data["characters"].remove(o)
        ch["cn"] = inspector_names.get(f"CharacterID.{ch['id']}", "")
        data["characters"].append(ch)
        by_id[ch["id"]] = [ch]
    # 兜底补全枚举中文名
    for ch in data["characters"]:
        if not ch.get("cn"):
            ch["cn"] = inspector_names.get(f"CharacterID.{ch['id']}", "")
    print(f"  merge characters: total={len(data['characters'])}")

    # 遗物: displayId+kind 合并; enum 占位符被真实数据( shared )替换 (需求 #22/#23)
    def relic_key(e):
        return (e["id"], e.get("kind") or "")

    by_rkey = {}
    for e in data["relics"]:
        by_rkey.setdefault(relic_key(e), []).append(e)
    added = replaced = 0
    for r in shared.get("relics", []):
        k = relic_key(r)
        olds = by_rkey.get(k, [])
        real = [o for o in olds if o.get("src") != "enum"]
        if real:
            continue  # 已有真实数据
        for o in olds:
            data["relics"].remove(o)
        data["relics"].append(r)
        by_rkey.setdefault(k, []).append(r)
        added += 1
        if olds:
            replaced += 1
    # 清理 (需求 #32): id 已有真实数据的 enum 占位删除
    real_ids = {e["id"] for e in data["relics"] if e.get("src") != "enum"}
    before = len(data["relics"])
    data["relics"] = [e for e in data["relics"]
                      if e.get("src") != "enum" or e["id"] not in real_ids]
    print(f"  merge relics: +{added} from shared (替换占位 {replaced}, 删除冗余占位 {before - len(data['relics'])})")

    # 补全所有遗物的 en 字段（拼音）
    for e in data["relics"]:
        if not e.get("en"):
            e["en"] = relic_enum.get(e["id"], "")


# ============================================================
# 神秘事件提取 (需求 #27): EventNode 图 + 事件_* TextAsset JSON
# ============================================================
# 诅咒/神秘遗物的具体脚本类 (来自 dump.cs 继承链分析, 需求 #31)
CURSED_RELIC_SCRIPTS = {"GuiChengDisplay", "PoWanDisplay", "ShengXiuDingZiDisplay", "ShouKaoDisplay", "WuGuWaWaDisplay", "ZhiRenDisplay", "ZouMaDengDisplay"}
MYSTERIOUS_RELIC_SCRIPTS = {"BaiBaoXiangDisplay", "BaiYuShanDisplay", "BianXingFuDisplay", "DiZangWangBaoJianDisplay", "DuShiWangBaoJianDisplay", "LingDengDisplay", "LingLongBaoTaDisplay", "NingHunZhuDisplay", "NvWaTuDisplay", "QinGuangWangBaoJianDisplay", "RanHunQiangDisplay", "SenLuoBaoJianDisplay", "ShangHunRenDisplay", "ShenMiGongTaiDisplay", "ShiHunZhuDisplay", "ShouXiangDisplay", "TaiShanShiDisplay", "TaiShanWangBaoJianDisplay", "XuanYuanBaoJingDisplay", "YanLuoWangBaoJianDisplay", "YueGuangBaoHeDisplay", "YueGuangBaoHeSuiPianDisplay", "ZhaoYaoJingDisplay", "ZiJinTiYuDisplay"}

NODE_TYPE_LABELS = {
    3: "对话", 4: "选项", 5: "文本", 6: "事件插图", 7: "标题", 8: "描述", 9: "气泡",
    10: "加底分", 11: "加番", 12: "加独立倍率", 14: "加血", 15: "加魂", 16: "加低令牌",
    20: "设底分", 21: "设番", 22: "设独立倍率", 23: "设金币", 24: "设血", 25: "设魂",
    26: "设和牌槽", 27: "设摸牌数", 28: "设交换次数",
    30: "获得Buff", 31: "获得灵佣", 32: "获得宝牌", 33: "获得遗物", 34: "获得祭品",
    35: "获得临时灵佣",
    40: "失去Buff", 41: "失去灵佣", 42: "失去宝牌", 43: "失去遗物", 44: "失去祭品",
    48: "阶段分支", 49: "层数分支", 50: "随机分支", 51: "随机选项", 52: "难度分支",
    53: "设刷新价格", 54: "设确认价格", 55: "设确认次数",
    56: "新人模式条件", 57: "魂条件", 58: "血条件", 59: "金币条件", 60: "Buff条件",
    61: "灵佣条件", 62: "宝牌条件", 63: "遗物条件", 64: "祭品条件",
    65: "灵佣解锁条件", 66: "遗物解锁条件", 67: "天赋条件", 68: "难度条件",
    69: "全局数据条件", 70: "选牌面", 71: "设数量上限", 72: "设刷新次数",
    77: "切换遗物", 78: "事件配置", 79: "麻将对局",
    80: "回血", 81: "回魂", 90: "禁用", 92: "交互性", 93: "关闭", 94: "延迟",
    95: "发送事件", 96: "跳转", 97: "阻塞", 98: "刷新", 99: "结束", 100: "死亡",
    101: "游戏引导", 102: "引导结束", 110: "地图继续模式",
    301: "轮换分支", 302: "运行模式分支", 303: "随机模式分支",
    450: "角色等级分支", 452: "角色等级分支", 453: "技能等级分支", 454: "角色解锁条件",
    500: "商店配置", 510: "商店标签配置", 520: "商店购买次数",
    600: "当铺出售", 610: "当铺购买", 650: "天赋等级分支",
}
EFFECT_TYPES = {10, 11, 12, 14, 15, 16, 20, 21, 22, 23, 24, 25, 26, 27, 28,
                30, 31, 32, 33, 34, 35, 40, 41, 42, 43, 44, 77, 79, 80, 81,
                500, 510, 520, 600, 610}


def _fmt_effect(n, ctx):
    """效果节点 → 人类可读摘要"""
    t = n["type"]
    lab = NODE_TYPE_LABELS.get(t, f"效果{t}")
    parts = []
    if t in (10, 20) and n.get("baseScore"): parts.append(f"底分{n['baseScore']:+d}")
    if t in (11, 21) and n.get("fan"): parts.append(f"番{n['fan']:+d}")
    if t in (14, 24) and n.get("hp"): parts.append(f"血{n['hp']:+d}")
    if t in (15, 25) and n.get("hun"): parts.append(f"魂{n['hun']:+g}")
    if t == 23 and n.get("floatValue"): parts.append(f"金币{n['floatValue']:+g}")
    if t in (31, 35, 41):
        names = [_lingyou_name_by_pid(ctx, (r or {}).get("path_id"))
                 for r in (n.get("xiaoChouPaiGetList") or [])]
        names = [x for x in names if x]
        if names: parts.append("".join(names) if t != 41 else "失去" + "".join(names))
    if t in (32, 42) and n.get("baoLingGetList"):
        parts.append("宝牌 " + "/".join(_baoling_name(i) for i in n["baoLingGetList"]))
    if t in (33, 43) and n.get("relicGetList"):
        parts.append("遗物 " + "/".join(_relic_name(ctx, i) for i in n["relicGetList"]))
    if t in (34, 44) and n.get("offeringGetList"):
        parts.append("祭品 " + "/".join(_offering_name(ctx, i) for i in n["offeringGetList"]))
    if t == 49: parts.append(f"层数 {n.get('level', '?')}")
    if t == 52: parts.append(f"难度 {n.get('level', '?')}")
    if t == 450 and n.get("characterID"): parts.append(f"角色{n['characterID']}等级{n.get('level','')}")
    if t == 79: parts.append("麻将对局")
    if t in (500, 510): parts.append("商店")
    if t in (600, 610): parts.append("当铺")
    if not parts:
        return lab
    return f"{lab}({', '.join(parts)})" if lab not in parts[0] else parts[0]


def _lingyou_name_by_pid(ctx, pid):
    n = ctx["xc_names"].get(pid)
    return n or ""


def _relic_name(ctx, rid):
    return ctx["relic_names"].get(rid, str(rid))


def _offering_name(ctx, oid):
    return ctx["offering_names"].get(oid, str(oid))


def _baoling_name(bid):
    return ctx_baoling.get(bid, str(bid))


ctx_baoling = {1: "红宝牌", 2: "蓝宝牌", 3: "绿宝牌", 4: "金宝牌", 5: "骷髅牌", 6: "红玉牌",
               7: "迷音牌", 8: "炸药牌", 9: "毒宝牌", 10: "无宝牌", 11: "水晶牌", 12: "迷幻牌",
               13: "黑玉牌", 14: "黑莲牌", 15: "幸运牌", 16: "真言牌"}


def _extract_event_icons(bsf):
    """从 bundle 中提取事件插图 (Sprite → PNG) 到 site/icons/events/。
    返回 {event_image_name: icon_filename}。"""
    out_dir = SITE_DIR / "icons" / "events"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 收集 Sprite 名称 → object reader
    sprite_objs = {}
    for obj in bsf.objects.values():
        if obj.type.name == "Sprite":
            try:
                d = obj.read()
                nm = getattr(d, "m_Name", "")
                if nm:
                    sprite_objs[nm] = obj
            except Exception:
                pass

    # 事件中文名 → Sprite 名映射 (全部事件插图均在 bundle 中)
    EVENT_ICON_MAP = {
        # DLC 事件
        "三张戏面": "SanZhangXiMian",
        "压轴好戏": "YaZhouHaoXi",
        "夺命飞车": "DuoMingFeiChe",
        "幸运飞刀": "XingYunFeiDao",
        "恼热邀请函": "NaoReYaoQingHan",
        "抓娃娃机": "ZhuaWaWaJi",
        "搓背小鬼": "CuoBeiXiaoGui",
        "旋转木龙": "XuanZhuanMuLong",
        "杂耍摊": "ZaShuaTan",
        "沉骨许愿池": "ChenGuXuYuanChi",
        "沸骨药浴": "FeiGuYaoYu",
        "炼狱蒸包铺": "LianYuZhengBaoPu",
        "鬼屋冒险": "GuiWuMaoXian",
        "鬼怪脱口秀": "GuiGuaiTuoKouXiu",
        # 本体事件
        "三只葫芦": "Sanzhihulu",
        "不记得我啦": "Bujidewola",
        "两小妖辩大小": "Liangxiaoyaobiandaxiao",
        "古怪祭坛": "Guguaijitan",
        "命犯太岁": "Mingfantaisui",
        "回收铺子": "Huishoupuzi",
        "地府书院": "Difushuyuan",
        "大转盘": "Dazhuanpan",
        "奶茶研发": "Naichayanfa",
        "废弃的供养阁": "Feiqidegongyangge",
        "强力牌组": "Qianglipaizu",
        "斗兽表演": "Doushoubiaoyan",
        "灵俑套圈": "Lingyongtaiquan",
        "猩红祭坛": "Xinghongjitan",
        "畜生道": "Chushengdao",
        "疯癫道士": "Fengdiandaoshi",
        "石像废墟": "Shixiangfeixu",
        "神仙？妖怪？": "Shenxianyaoguai",
        "祭品促销": "Jipinchuxiao",
        "祭品福袋": "Jipinfudai",
        "缘分俑市": "Yuanfenyongshi",
        "蛋俑救助站": "Danyongjiuzhuzhan",
        "许愿池": "Xuyuanchi",
        "银蛇剑": "Yinshejian",
        "阴寿将尽": "YinSiJie",
        "青铜鹤": "Qingtonghe",
        "龙息谷": "Longxigu",
        "龟驮碑": "Guituobei",
        "牌风测试": "Guigeceshi",
        "冥府磨坊": "Mofangjingli",
        "风灵珠": "Dingfengzhu",
    }

    result = {}
    count = 0
    for cn_name, sprite_name in EVENT_ICON_MAP.items():
        if sprite_name not in sprite_objs:
            continue
        try:
            img = sprite_objs[sprite_name].read().image
            fname = f"{sprite_name}.png"
            img.save(str(out_dir / fname))
            result[cn_name] = f"icons/events/{fname}"
            count += 1
        except Exception:
            pass
    print(f"  event icons: {count} extracted to {out_dir}")
    return result


def _extract_buff_icons(bsf):
    """从 bundle 中提取业镜 Buff 图标 (Sprite → PNG) 到 site/icons/buff/。"""
    out_dir = SITE_DIR / "icons" / "buff"
    out_dir.mkdir(parents=True, exist_ok=True)

    sprite_objs = {}
    for obj in bsf.objects.values():
        if obj.type.name == "Sprite":
            try:
                d = obj.read()
                nm = getattr(d, "m_Name", "")
                if nm.startswith("Buff"):
                    sprite_objs[nm] = obj
            except Exception:
                pass

    count = 0
    for sprite_name, obj in sprite_objs.items():
        try:
            img = obj.read().image
            fname = f"{sprite_name}.png"
            img.save(str(out_dir / fname))
            count += 1
        except Exception:
            pass
    print(f"  buff icons: {count} extracted to {out_dir}")
    return count > 0


def extract_events(i2):
    """神秘事件 (需求 #27/#42/#43/#44/#45) v4: 完全重写。
    - 从 bundle CAB 加载 EventNode + NodePort 图
    - 每个事件使用独立 TextTerms 映射 (避免跨事件 key 复用导致文本污染)
    - 按 textContentTag 匹配节点到事件, 使用节点自带 textContent
    - 选项→效果: 仅追踪直接连接 (不做全局 BFS 避免跨事件)"""
    print("  loading event graph (bundle CAB)...")
    am = AssetsManager()
    for ms_bf in AA_DIR.glob("*_monoscripts_*.bundle"):
        am.load_file(str(ms_bf))
        break
    bf = am.load_file(str(BUNDLE_PATH))
    cab_keys = [k for k in bf.files if k.startswith("CAB-")]
    bsf = bf.files[cab_keys[0]]

    all_nodes, all_ports = [], {}
    for pid, obj in bsf.objects.items():
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            d = obj.read()
            ms = getattr(d, "m_Script", None)
            if not ms:
                continue
            cn = getattr(ms.read(), "m_ClassName", "")
        except Exception:
            continue
        try:
            raw = obj.get_raw_data()
            if cn == "EventNode":
                all_nodes.append(rp.parse_payload(raw, "EventNode"))
            elif cn == "NodePort":
                all_ports[pid] = rp.parse_payload(raw, "NodePort")
        except Exception:
            pass
    node_by_id = {n["id"]: n for n in all_nodes}
    print(f"  EventNode={len(all_nodes)}, NodePort={len(all_ports)}")

    # 提取事件插图
    icon_map = _extract_event_icons(bsf)

    # 提取业镜 Buff 图标
    _extract_buff_icons(bsf)

    def get_out_ports(n):
        return [all_ports[pr["path_id"]]
                for pr in (n.get("ports") or [])
                if pr.get("path_id") in all_ports]

    # 名称解析上下文 + sharedassets4 加载
    ctx = {"xc_names": {}, "relic_names": {}, "offering_names": {}}
    am4 = AssetsManager()
    sf4 = am4.load_file(str(SHARED4))
    cls4, _ = classify_monobehaviours(sf4)
    for pid in cls4.get("XiaoChouPaiPayload", []):
        try:
            d = rp.parse_payload(sf4.objects[pid].get_raw_data(), "XiaoChouPaiPayload")
            nm = tr(d.get("displayNameTerm", ""), i2) or d.get("m_Name", "")
            ctx["xc_names"][pid] = nm
        except Exception:
            pass
    for e in data_relic_names():
        ctx["relic_names"][e[0]] = e[1]
    for e in data_offering_names():
        ctx["offering_names"][e[0]] = e[1]

    # 加载事件 JSON (from bundle + sharedassets4)
    event_jsons = {}
    # 1. From bundle CAB
    for pid, obj in bsf.objects.items():
        if obj.type.name != "TextAsset":
            continue
        try:
            d = obj.read()
            nm, data = d.m_Name, d.m_Script
        except Exception:
            continue
        if isinstance(data, str):
            data = data.encode("utf-8", "ignore")
        if not (isinstance(nm, str) and (nm.startswith(chr(20107)+chr(20214)+"_") or nm.startswith(chr(24120)+chr(35215)+"_"))):
            continue
        try:
            j = json.loads(data)
        except Exception:
            continue
        event_jsons[nm] = j
    # 2. From sharedassets4 (base game events)
    for pid, obj in sf4.objects.items():
        if obj.type.name != "TextAsset":
            continue
        try:
            d = obj.read()
            nm, data = d.m_Name, d.m_Script
        except Exception:
            continue
        if isinstance(data, str):
            data = data.encode("utf-8", "ignore")
        if not (isinstance(nm, str) and (nm.startswith(chr(20107)+chr(20214)+"_") or nm.startswith(chr(24120)+chr(35215)+"_"))):
            continue
        if nm in event_jsons:
            continue  # bundle 版本优先
        try:
            j = json.loads(data)
        except Exception:
            continue
        event_jsons[nm] = j
    print(f"  event JSONs loaded: {len(event_jsons)} (from bundle + sharedassets4)")

    def _fmt_effect(n, ctx):
        t = n["type"]
        lab = NODE_TYPE_LABELS.get(t, f"效果{t}")
        parts = []
        if t in (10, 20) and n.get("baseScore"): parts.append(f"底分{n['baseScore']:+d}")
        if t in (11, 21) and n.get("fan"): parts.append(f"番{n['fan']:+d}")
        if t in (14, 24) and n.get("hp"): parts.append(f"血{n['hp']:+d}")
        if t in (15, 25) and n.get("hun"): parts.append(f"魂{n['hun']:+g}")
        if t == 23 and n.get("floatValue"): parts.append(f"金币{n['floatValue']:+g}")
        if t in (31, 35, 41):
            names = [_lingyou_name_by_pid(ctx, (r or {}).get("path_id"))
                     for r in (n.get("xiaoChouPaiGetList") or [])]
            names = [x for x in names if x]
            if names: parts.append("".join(names) if t != 41 else "失去" + "".join(names))
        if t in (32, 42) and n.get("baoLingGetList"):
            parts.append("宝牌 " + "/".join(_baoling_name(i) for i in n["baoLingGetList"]))
        if t in (33, 43) and n.get("relicGetList"):
            parts.append("遗物 " + "/".join(_relic_name(ctx, i) for i in n["relicGetList"]))
        if t in (34, 44) and n.get("offeringGetList"):
            parts.append("祭品 " + "/".join(_offering_name(ctx, i) for i in n["offeringGetList"]))
        if t == 49: parts.append(f"层数 {n.get('level', '?')}")
        if t == 52: parts.append(f"难度 {n.get('level', '?')}")
        if t == 450 and n.get("characterID"): parts.append(f"角色{n['characterID']}等级{n.get('level','')}")
        if t == 79: parts.append("麻将对局")
        if not parts:
            parts.append(lab)
        return " ".join(parts)

    events = []
    for nmj, j in sorted(event_jsons.items()):
        ev_map = {}
        for t in j.get("TextTerms", []):
            if t.get("Key") and t.get("Chinese"):
                ev_map[t["Key"]] = t["Chinese"]
        if not ev_map:
            continue
        ev_tags = set(ev_map.keys())
        title = nmj.replace(chr(20107)+chr(20214)+"_", "").replace(chr(24120)+chr(35215)+"_", "")
        kind = chr(20107)+chr(20214) if nmj.startswith(chr(20107)+chr(20214)+"_") else chr(24120)+chr(35215)

        # 匹配节点: textContentTag 在本事件 TextTerms 中
        matched = [n for n in all_nodes
                   if n.get("textContentTag") in ev_tags]

        # 事件插图: 直接通过事件中文名查找
        ev_icon = icon_map.get(title, "")

        # 描述文本: 仅取 TextTerms 中第一个非选项条目 (介绍文本)
        # 先从图匹配获取
        texts = []
        for n in matched:
            if n["type"] in (3, 5, 8):
                txt = n.get("textContent") or ev_map.get(n.get("textContentTag", ""), "")
                if txt and txt not in texts:
                    texts.append(txt)

        # 描述: 从 TextTerms 按顺序找介绍文本 (跳过标题, 排除选项结果)
        term_list_desc = j.get("TextTerms", [])
        intro_text = ""
        for t in term_list_desc:
            ch = clean_markup(t.get("Chinese", "")).strip()
            if not ch:
                continue
            is_opt = ch.startswith(chr(12304)) or ch.startswith("[")
            if is_opt:
                continue
            # 跳过短条目 (标题通常很短)
            if len(ch) < 20:
                continue
            intro_text = ch
            break

        # 清理描述: 移除选项行
        if intro_text:
            lines = intro_text.split("\n")
            kept = [l for l in lines if not l.strip().startswith("[") and not l.strip().startswith(chr(12304))]
            texts = ["\n".join(kept).strip()]
        else:
            # 兜底: 从图匹配的文本中清理选项行
            cleaned = []
            for t in texts:
                lines = t.split("\n")
                kept = [l for l in lines if not l.strip().startswith("[") and not l.strip().startswith(chr(12304))]
                cleaned_text = "\n".join(kept).strip()
                if cleaned_text:
                    cleaned.append(cleaned_text)
            texts = cleaned

        # 选项+结果: 按 TextTerms 顺序解析, 每个选项后跟对应的结果文本
        options, seen_opt = [], set()
        limits = []
        # 收集图匹配的效果 (如果有)
        graph_effects = {}  # option_text -> [effects]
        for n in matched:
            if n.get("memo"):
                limits.append(n["memo"])
            if n["type"] in (49, 52):
                limits.append(_fmt_effect(n, ctx))
            if n["type"] != 4:
                continue
            for pp in get_out_ports(n):
                ptag = pp.get("textContentTag", "")
                if ptag not in ev_tags:
                    continue
                otxt = pp.get("textContent") or ev_map.get(ptag, "")
                effects = []
                visited = set()
                q = [node_by_id.get(pp.get("targetNode"))]
                while q and len(effects) < 6:
                    m = q.pop(0)
                    if not m or m.get("id") in visited:
                        continue
                    visited.add(m.get("id"))
                    if m["type"] in EFFECT_TYPES:
                        effects.append(_fmt_effect(m, ctx))
                    if m["type"] not in EFFECT_TYPES:
                        continue
                    for pp2 in get_out_ports(m):
                        m2 = node_by_id.get(pp2.get("targetNode"))
                        if m2:
                            q.append(m2)
                if otxt and otxt not in graph_effects:
                    graph_effects[otxt] = effects

        # 按 TextTerms 顺序解析选项+结果对
        term_list = j.get("TextTerms", [])
        pending_opt = None
        pending_result_parts = []
        for t in term_list:
            ch = clean_markup(t.get("Chinese", "")).strip()
            if not ch:
                continue
            is_opt = ch.startswith(chr(12304)) or ch.startswith("[")  # 【或[
            if is_opt:
                # 保存上一个选项
                if pending_opt is not None:
                    result = "\n".join(pending_result_parts).strip()
                    key = pending_opt + "|"
                    if key not in seen_opt:
                        seen_opt.add(key)
                        eff = graph_effects.get(pending_opt, [])
                        options.append({"text": pending_opt, "effects": eff, "result": result})
                pending_opt = ch
                pending_result_parts = []
            else:
                # 结果文本: 追加到当前选项
                if pending_opt is not None:
                    pending_result_parts.append(ch)
        # 保存最后一个选项
        if pending_opt is not None:
            result = "\n".join(pending_result_parts).strip()
            key = pending_opt + "|"
            if key not in seen_opt:
                seen_opt.add(key)
                eff = graph_effects.get(pending_opt, [])
                options.append({"text": pending_opt, "effects": eff, "result": result})

        if not texts and not options:
            continue
        ev = {
            "id": title,
            "name": title,
            "kind": kind,
            "limits": sorted(set(l for l in limits if l)),
            "desc": chr(10).join(texts),
            "options": options,
        }
        if ev_icon:
            ev["icon"] = ev_icon
        events.append(ev)
    events.sort(key=lambda e: (e["kind"], e["name"]))
    print(f"  events extracted: {len(events)}")
    return events
def data_relic_names():
    """(id, 中文名) 列表 —— 从已构建数据缓存"""
    return getattr(data_relic_names, "cache", [])


def data_offering_names():
    return getattr(data_offering_names, "cache", [])


# ============================================================
# 文本回填 + 输出
# ============================================================
def apply_text(entries, i2, id_fields=("nameKey", "descKey")):
    missing = 0
    for e in entries:
        nk, dk = e.get("nameKey", ""), e.get("descKey", "")
        if not nk and not dk:
            continue
        name_txt = tr(nk, i2)
        desc_txt = tr(dk, i2)
        # 修正 descKey 路径格式错误 (如 "Individual30050" → "Individual/30050")
        if dk and desc_txt is None:
            fixed_dk = re.sub(r'(Individual)(\d)', r'\1/\2', dk)
            if fixed_dk != dk:
                desc_txt = tr(fixed_dk, i2)
                if desc_txt is not None:
                    dk = fixed_dk
                    e["descKey"] = dk
        e["name"] = name_txt if name_txt is not None else ""
        e["desc"] = desc_txt if desc_txt is not None else ""
        if (nk and name_txt is None) or (dk and desc_txt is None):
            missing += 1
    return missing


def extract_achievement_icons():
    """从 bundle 提取成就图标到 legendary_icons/achievements/。"""
    from UnityPy.enums import ClassIDType
    out_dir = GAME_DIR / "legendary_icons" / "achievements"
    out_dir.mkdir(parents=True, exist_ok=True)
    bpath = locate_bundle()
    if not bpath:
        print("  [WARN] bundle not found, skip achievement icons")
        return
    am = AssetsManager()
    bf = am.load_file(str(bpath))
    sf = bf.files[list(bf.files.keys())[0]]
    count = 0
    seen = set()
    for cpath, pp in sf.container.items():
        if "/Achievement/" not in cpath or not cpath.endswith(".png"):
            continue
        m = re.search(r"AchievementIcon(\d+)", cpath)
        if not m:
            continue
        icon_id = int(m.group(1))
        if icon_id in seen:
            continue
        seen.add(icon_id)
        try:
            obj = pp.read()
            img = obj.image
            img.save(str(out_dir / f"{icon_id}.png"))
            count += 1
        except Exception:
            continue
    print(f"  achievement icons: {count} extracted to {out_dir}")


def copy_web_files():
    """把 web_src/ 与图标同步到 site/（不重新提取数据）。"""
    WEB_SRC = Path(__file__).parent / "web_src"
    ASSETS = Path(__file__).parent / "assets"
    repo_url = os.environ.get("REPO_URL", "")
    for f in ("index.html", "app.js", "style.css", "data.json"):
        src = WEB_SRC / f
        if not src.exists():
            continue
        if f.endswith(".js") or f.endswith(".html"):
            # 格式化 JS/HTML
            cmd = ["pnpx", "prettier", "--write", str(src)]
            if sys.platform == "win32":
                cmd = ["cmd", "/C"] + cmd
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, shell=True)
                print(f"  web_src/{f} formatted")
            except subprocess.CalledProcessError as e:
                print(f"  web_src/{f} prettier format failed: {e.stderr.strip()}")
        content = src.read_text(encoding="utf-8")
        # 替换环境变量占位符
        if repo_url:
            content = content.replace("__REPO_URL__", repo_url)
        (SITE_DIR / f).write_text(content, encoding="utf-8")
        print(f"  site/{f} copied")

    # 复制 assets/enums.json 到 site/
    enums_src = ASSETS / "enums.json"
    if enums_src.exists():
        (SITE_DIR / "enums.json").write_text(enums_src.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  site/enums.json copied")

    icons_src = GAME_DIR / "legendary_icons"
    if icons_src.exists():
        dst = SITE_DIR / "icons"
        dst.mkdir(exist_ok=True)
        copied = 0
        for sub in icons_src.iterdir():
            if sub.is_dir():
                d = dst / sub.name
                if d.exists():
                    shutil.rmtree(d)
                shutil.copytree(sub, d)
                copied += len(list(d.glob("**/*.png")))
        print(f"  site/icons synced ({copied} png from legendary_icons)")


def main():
    web_only = "--web-only" in sys.argv
    export_events = "--export-events" in sys.argv
    print("=" * 60)
    print("Demonic Mahjong - Web Builder" + ("  (--web-only)" if web_only else ""))
    print("=" * 60)

    if web_only:
        print("\n[web-only] syncing site files (no data re-extraction)...")
        if not (Path(__file__).parent / "web_src" / "data.json").exists():
            print("  [WARN] web_src/data.json 不存在, 请先不带参数运行一次完整构建")
        copy_web_files()
        print("\n[DONE]")
        return

    print("\n[1/5] parsing enums...")
    enum_values, inspector_names = parse_all_enums(DUMP_CS)
    print(f"  {sum(len(v) for v in enum_values.values())} enum values, "
          f"{len(inspector_names)} inspector names")

    print("\n[2/5] extracting bundle (DLC) data...")
    data = extract_bundle(enum_values, inspector_names)

    print("\n[3/5] extracting base-game data (sharedassets)...")
    shared = extract_shared_assets(enum_values)
    relic_enum = enum_values.get("RelicId", {})
    merge_shared(data, shared, inspector_names, relic_enum)

    print("\n[4/5] parsing I2 localization...")
    i2 = load_i2_terms()

    # 神秘事件 (需求 #27): 依赖遗物/祭品/灵佣名称
    data_relic_names.cache = [(e["id"], e.get("name") or e.get("cn") or e.get("en", ""))
                              for e in data["relics"]]
    data_offering_names.cache = [(e["id"], e.get("name") or e.get("en", ""))
                                 for e in data["offerings"]]
    data["events"] = extract_events(i2)

    total_missing = 0
    for cat, entries in data.items():
        if not isinstance(entries, list):
            continue
        miss = apply_text(entries, i2)
        total_missing += miss
        print(f"  {cat}: {len(entries)} entries ({miss} keys unresolved)")

    # BOSS灵俑: level 从1开始, 去掉名字里 lv.1
    import re as _re
    for e in data["lingyong"]:
        xid = e.get("id", 0)
        if (10000 <= xid < 20000) or (30000 <= xid < 40000):
            e["level"] = e.get("level", 0) + 1
            name = e.get("name", "")
            e["name"] = _re.sub(r"\s*lv\.1$", "", name)

    # 业镜 Buff 图标映射: 中文名 → Sprite 文件名 (在 apply_text 之后)
    BUFF_ICON_MAP = {
        "惩贪": "BuffChengTan", "摧寿": "BuffCuiShou", "禁欲": "BuffJinYu",
        "断财": "BuffDuanCai", "破势": "BuffPoShi", "夺功": "BuffDuoGong",
        "折翼": "BuffFanBei", "镇邪": "BuffZhenXie",
    }
    for ev in data["yejingbuff"]:
        cn = ev.get("name", "")
        if cn in BUFF_ICON_MAP:
            ev["icon"] = f"icons/buff/{BUFF_ICON_MAP[cn]}.png"
    # 角色技能文本
    sk_miss = 0
    for ch in data["characters"]:
        for grp in ("passives", "actives"):
            for sk in ch[grp]:
                nt = tr(sk["nameKey"], i2)
                dt = tr(sk["descKey"], i2)
                sk["name"] = nt if nt is not None else ""
                sk["desc"] = dt if dt is not None else ""
                if (sk["nameKey"] and nt is None) or (sk["descKey"] and dt is None):
                    sk_miss += 1
    print(f"  character skills unresolved keys: {sk_miss}")
    # 番种中文名兜底
    for fz in data["fanzhong"]:
        if not fz.get("cn"):
            fz["cn"] = tr(fz["nameKey"], i2) or ""

    # 稀有度名
    for e in data["lingyong"]:
        e["rar"] = rarity_name(e["rarity"], inspector_names)
    for e in data["relics"]:
        kind = e.get("kind") or ""
        base_rar = rarity_name(e["rarity"], inspector_names) if e["rarity"] else ""
        e["rar"] = kind or base_rar          # 神秘/诅咒/外乡人 优先作为分类
        e["rar2"] = base_rar                  # 底层稀有度
    # 祭品分类 (item10): 按 Offering 枚举区间
    for e in data["offerings"]:
        e["cat"] = offering_category(e["id"])

    # 排序: 类别内按 id 升序, 同 id 按 level
    for cat in data:
        if isinstance(data[cat], list):
            data[cat].sort(key=lambda e: (e["id"], e.get("level", 0)))

    print(f"\ntotal unresolved keys: {total_missing}")

    # 导出事件原始数据为 JSON
    if export_events:
        events_file = SITE_DIR / "events_raw.json"
        with open(events_file, "w", encoding="utf-8") as fp:
            json.dump(data["events"], fp, ensure_ascii=False, indent=2)
        print(f"\n[export] events -> {events_file} ({events_file.stat().st_size:,} bytes)")

    print("\n[5/5] writing site files...")
    WEB_SRC = Path(__file__).parent / "web_src"
    SITE_DIR.mkdir(exist_ok=True)
    payload = {
        "_comment": f"本文件由 build_web.py 于 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 自动生成, 请勿手动修改",
        "meta": {"game": "我在地府打麻将", "build": "build_web.py"},
        "data": data,
    }
    data_json_path = WEB_SRC / "data.json"
    with open(data_json_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=1)
    size = data_json_path.stat().st_size
    print(f"  web_src/data.json written ({size:,} bytes)")
    extract_achievement_icons()
    copy_web_files()
    print("\n[DONE]")


if __name__ == "__main__":
    main()
