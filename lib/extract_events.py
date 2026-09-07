#!/usr/bin/env python3
"""神秘事件提取: EventNode 图 + 事件_* TextAsset JSON + 图标提取。"""
import json

from UnityPy import AssetsManager

from config import AA_DIR, BUNDLE_PATH, SHARED4, SITE_DIR
from extract_shared import classify_monobehaviours
from i2parse import tr, clean_markup
import rawparse as rp

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

ctx_baoling = {1: "红宝牌", 2: "蓝宝牌", 3: "绿宝牌", 4: "金宝牌", 5: "骷髅牌", 6: "红玉牌",
               7: "迷音牌", 8: "炸药牌", 9: "毒宝牌", 10: "无宝牌", 11: "水晶牌", 12: "迷幻牌",
               13: "黑玉牌", 14: "黑莲牌", 15: "幸运牌", 16: "真言牌"}

_data_relic_names = []
_data_offering_names = []


def set_data_names(relic_names, offering_names):
    global _data_relic_names, _data_offering_names
    _data_relic_names = relic_names
    _data_offering_names = offering_names


def _lingyou_name_by_pid(ctx, pid):
    return ctx["xc_names"].get(pid) or ""


def _relic_name(ctx, rid):
    return ctx["relic_names"].get(rid, str(rid))


def _offering_name(ctx, oid):
    return ctx["offering_names"].get(oid, str(oid))


def _baoling_name(bid):
    return ctx_baoling.get(bid, str(bid))


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
    if t in (500, 510): parts.append("商店")
    if t in (600, 610): parts.append("当铺")
    if not parts:
        return lab
    return f"{lab}({', '.join(parts)})" if lab not in parts[0] else parts[0]


def _extract_event_icons(bsf):
    """从 bundle 中提取事件插图 (Sprite -> PNG) 到 site/icons/events/。"""
    out_dir = SITE_DIR / "icons" / "events"
    out_dir.mkdir(parents=True, exist_ok=True)

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

    EVENT_ICON_MAP = {
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
    """从 bundle 中提取业镜 Buff 图标 (Sprite -> PNG) 到 site/icons/buff/。"""
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
    """神秘事件 v4: EventNode 图 + TextAsset JSON。"""
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

    icon_map = _extract_event_icons(bsf)
    _extract_buff_icons(bsf)

    def get_out_ports(n):
        return [all_ports[pr["path_id"]]
                for pr in (n.get("ports") or [])
                if pr.get("path_id") in all_ports]

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
    for e in _data_relic_names:
        ctx["relic_names"][e[0]] = e[1]
    for e in _data_offering_names:
        ctx["offering_names"][e[0]] = e[1]

    event_jsons = {}
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
            continue
        try:
            j = json.loads(data)
        except Exception:
            continue
        event_jsons[nm] = j
    print(f"  event JSONs loaded: {len(event_jsons)} (from bundle + sharedassets4)")

    def _fmt_effect_inner(n, ctx):
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

        matched = [n for n in all_nodes
                   if n.get("textContentTag") in ev_tags]

        ev_icon = icon_map.get(title, "")

        texts = []
        for n in matched:
            if n["type"] in (3, 5, 8):
                txt = n.get("textContent") or ev_map.get(n.get("textContentTag", ""), "")
                if txt and txt not in texts:
                    texts.append(txt)

        term_list_desc = j.get("TextTerms", [])
        intro_text = ""
        for t in term_list_desc:
            ch = clean_markup(t.get("Chinese", "")).strip()
            if not ch:
                continue
            is_opt = ch.startswith(chr(12304)) or ch.startswith("[")
            if is_opt:
                continue
            if len(ch) < 20:
                continue
            intro_text = ch
            break

        if intro_text:
            lines = intro_text.split("\n")
            kept = [l for l in lines if not l.strip().startswith("[") and not l.strip().startswith(chr(12304))]
            texts = ["\n".join(kept).strip()]
        else:
            cleaned = []
            for t in texts:
                lines = t.split("\n")
                kept = [l for l in lines if not l.strip().startswith("[") and not l.strip().startswith(chr(12304))]
                cleaned_text = "\n".join(kept).strip()
                if cleaned_text:
                    cleaned.append(cleaned_text)
            texts = cleaned

        options, seen_opt = [], set()
        limits = []
        graph_effects = {}
        for n in matched:
            if n.get("memo"):
                limits.append(n["memo"])
            if n["type"] in (49, 52):
                limits.append(_fmt_effect_inner(n, ctx))
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
                        effects.append(_fmt_effect_inner(m, ctx))
                    if m["type"] not in EFFECT_TYPES:
                        continue
                    for pp2 in get_out_ports(m):
                        m2 = node_by_id.get(pp2.get("targetNode"))
                        if m2:
                            q.append(m2)
                if otxt and otxt not in graph_effects:
                    graph_effects[otxt] = effects

        term_list = j.get("TextTerms", [])
        pending_opt = None
        pending_result_parts = []
        for t in term_list:
            ch = clean_markup(t.get("Chinese", "")).strip()
            if not ch:
                continue
            is_opt = ch.startswith(chr(12304)) or ch.startswith("[")
            if is_opt:
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
                if pending_opt is not None:
                    pending_result_parts.append(ch)
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
