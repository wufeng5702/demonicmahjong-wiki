#!/usr/bin/env python3
"""枚举解析 + 标签/稀有度中文化。"""
import json
import re
from pathlib import Path

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


def parse_all_enums(dump_path):
    enums_json = Path(__file__).resolve().parent.parent / "assets" / "enums.json"
    if enums_json.exists():
        raw = json.loads(enums_json.read_text(encoding="utf-8"))
        print(f"  从 enums.json 加载枚举")
        ev = {}
        for etype, mapping in raw["enum_values"].items():
            ev[etype] = {int(k): v for k, v in mapping.items()}
        return ev, raw["inspector_names"]

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
