#!/usr/bin/env python3
"""从 Addressables 主 bundle 提取全部 Payload 数据。"""
import re

from UnityPy import AssetsManager
from UnityPy.enums import ClassIDType

from config import AA_DIR, BUNDLE_PATH

XIAOCHOU_ADD_FIELDS = [
    "addBaseScore", "addBaseScore2", "addBaseMagnification", "addBaseMagnification2",
    "baseMultiIndependent", "accMultiIndependent", "multiple", "addFan",
    "addCoin", "addCoin1", "addSoul", "addHp", "addHpMax", "addSwap", "addChou",
    "count", "count2", "percent", "percentLimit", "decline", "maxValue", "maxCount",
]
OFFERING_ADD_FIELDS = ["soulCost", "addBaseScore", "addFan", "addPaiMainNum", "multi",
                       "accMultiIndependent", "count", "count2"]

# 诅咒/神秘遗物的具体脚本类 (来自 dump.cs 继承链分析)
CURSED_RELIC_SCRIPTS = {"GuiChengDisplay", "PoWanDisplay", "ShengXiuDingZiDisplay", "ShouKaoDisplay", "WuGuWaWaDisplay", "ZhiRenDisplay", "ZouMaDengDisplay"}
MYSTERIOUS_RELIC_SCRIPTS = {"BaiBaoXiangDisplay", "BaiYuShanDisplay", "BianXingFuDisplay", "DiZangWangBaoJianDisplay", "DuShiWangBaoJianDisplay", "LingDengDisplay", "LingLongBaoTaDisplay", "NingHunZhuDisplay", "NvWaTuDisplay", "QinGuangWangBaoJianDisplay", "RanHunQiangDisplay", "SenLuoBaoJianDisplay", "ShangHunRenDisplay", "ShenMiGongTaiDisplay", "ShiHunZhuDisplay", "ShouXiangDisplay", "TaiShanShiDisplay", "TaiShanWangBaoJianDisplay", "XuanYuanBaoJingDisplay", "YanLuoWangBaoJianDisplay", "YueGuangBaoHeDisplay", "YueGuangBaoHeSuiPianDisplay", "ZhaoYaoJingDisplay", "ZiJinTiYuDisplay"}


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


def extract_bundle(enum_values, inspector_names):
    print("  loading main bundle...")
    am = AssetsManager()
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

    # Import tag resolver and add fields
    from enums import _resolve_tag

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

    # ---- 遗物 ----
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
            "icon_pid": rpid,
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
            continue
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
