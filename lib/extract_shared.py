#!/usr/bin/env python3
"""从 sharedassets1/4 提取本体数据 (类型树被剥离 -> rawparse 手工解析)。"""
import re

from UnityPy import AssetsManager
from UnityPy.enums import ClassIDType

from config import SHARED1, SHARED4
from enums import _resolve_tag
import rawparse as rp

XIAOCHOU_ADD_FIELDS = [
    "addBaseScore", "addBaseScore2", "addBaseMagnification", "addBaseMagnification2",
    "baseMultiIndependent", "accMultiIndependent", "multiple", "addFan",
    "addCoin", "addCoin1", "addSoul", "addHp", "addHpMax", "addSwap", "addChou",
    "count", "count2", "percent", "percentLimit", "decline", "maxValue", "maxCount",
]
OFFERING_ADD_FIELDS = ["soulCost", "addBaseScore", "addFan", "addPaiMainNum", "multi",
                       "accMultiIndependent", "count", "count2"]

# 诅咒/神秘遗物脚本类名
CURSED_RELIC_SCRIPTS = {"GuiChengDisplay", "PoWanDisplay", "ShengXiuDingZiDisplay", "ShouKaoDisplay", "WuGuWaWaDisplay", "ZhiRenDisplay", "ZouMaDengDisplay"}
MYSTERIOUS_RELIC_SCRIPTS = {"BaiBaoXiangDisplay", "BaiYuShanDisplay", "BianXingFuDisplay", "DiZangWangBaoJianDisplay", "DuShiWangBaoJianDisplay", "LingDengDisplay", "LingLongBaoTaDisplay", "NingHunZhuDisplay", "NvWaTuDisplay", "QinGuangWangBaoJianDisplay", "RanHunQiangDisplay", "SenLuoBaoJianDisplay", "ShangHunRenDisplay", "ShenMiGongTaiDisplay", "ShiHunZhuDisplay", "ShouXiangDisplay", "TaiShanShiDisplay", "TaiShanWangBaoJianDisplay", "XuanYuanBaoJingDisplay", "YanLuoWangBaoJianDisplay", "YueGuangBaoHeDisplay", "YueGuangBaoHeSuiPianDisplay", "ZhaoYaoJingDisplay", "ZiJinTiYuDisplay"}


def classify_monobehaviours(sf):
    """按 MonoScript 类名分类所有 MonoBehaviour (不解析 body)。"""
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


def _xc_from_raw(d, enum_values=None):
    """rawparse 的 XiaoChouPaiPayload dict -> lingyong 条目"""
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


def extract_shared_assets(enum_values):
    """从 sharedassets1/4 提取本体数据。"""
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
                continue
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

    # 角色名映射: 从 RoleAvatar 提取 I2 localizedNameTerm
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
