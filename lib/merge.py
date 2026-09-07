#!/usr/bin/env python3
"""DLC + 本体数据合并、去重、祭品分类。"""


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
        return "花草"
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

    # 角色: 按 characterID 合并
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
    for ch in data["characters"]:
        if not ch.get("cn"):
            ch["cn"] = inspector_names.get(f"CharacterID.{ch['id']}", "")
    print(f"  merge characters: total={len(data['characters'])}")

    # 遗物: displayId+kind 合并
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
            continue
        for o in olds:
            data["relics"].remove(o)
        data["relics"].append(r)
        by_rkey.setdefault(k, []).append(r)
        added += 1
        if olds:
            replaced += 1
    real_ids = {e["id"] for e in data["relics"] if e.get("src") != "enum"}
    before = len(data["relics"])
    data["relics"] = [e for e in data["relics"]
                      if e.get("src") != "enum" or e["id"] not in real_ids]
    print(f"  merge relics: +{added} from shared (替换占位 {replaced}, 删除冗余占位 {before - len(data['relics'])})")

    for e in data["relics"]:
        if not e.get("en"):
            e["en"] = relic_enum.get(e["id"], "")
