#!/usr/bin/env python3
"""神秘事件提取: EventNode 图 + 事件_* TextAsset JSON + 图标提取。"""
import json
import re
import struct
from collections import deque
from pathlib import Path

from UnityPy import AssetsManager

from config import AA_DIR, BUNDLE_PATH, CATALOG_BIN, SHARED0, SHARED1, SHARED2, SHARED3, SHARED4, SITE_DIR
from extract_shared import classify_monobehaviours
from i2parse import tr, clean_markup
from enums import TAG_ID_CN, RARITY_CN
from catalog import Catalog
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
                29, 30, 31, 32, 33, 34, 35, 40, 41, 42, 43, 44, 70, 77, 78, 79,
                80, 81, 95, 96, 500, 510, 520, 600, 610}
# 遇到这些类型停止跨越（并列选项/随机选项），避免效果串到兄弟分支
_STOP_CROSS_TYPES = {4, 51}

GLOBAL_DATA_CN = {
    0: "金币", 1: "血量", 2: "血量上限", 3: "魂力", 4: "魂力上限",
    5: "摸牌数", 6: "总摸牌数", 7: "和牌槽", 8: "交换次数",
    9: "灵佣槽位", 10: "祭品槽位",
    11: "商店刷新价", 12: "商店刷新加价", 13: "商店购买次数", 14: "当前刷新次数",
    16: "灵佣获取修正", 17: "魂力回复", 18: "玩家底分",
    21: "跳过怪物数", 22: "令牌商店购买次数", 23: "令牌商店已购",
    24: "DLC地图风格", 25: "DLC开启状态",
    100: "局外金币倍率", 101: "局内金币倍率", 102: "消费金币倍率", 103: "商店价格倍率",
}

EVENT_TYPE_CN = {
    0: "默认", 1: "宝箱", 2: "俑道",
    10: "注能台", 11: "注能台(简)",
    21: "锻造台", 22: "幻灵台",
    50: "灵俑奖励", 51: "遗物奖励", 52: "祭品奖励",
    97: "胜利事件", 98: "失败事件", 99: "神秘事件",
    1001: "商店", 1002: "当铺",
    1010: "奶茶店", 1011: "奶茶点单", 1012: "神秘商店",
    1013: "酒馆", 1014: "令牌商店",
    1020: "编成灵俑", 1021: "编成遗物", 1022: "编成祭品",
}

# 宝牌 ID → 中文名（与 data.json baopai 一致; ID 5/8/9/10... 曾整体错位, 真言牌实为 9999）
ctx_baoling = {1: "红宝牌", 2: "蓝宝牌", 3: "绿宝牌", 4: "金宝牌", 5: "螺钿牌",
               8: "红玉牌", 9: "银宝牌", 10: "炸药牌", 11: "毒宝牌", 12: "雾宝牌",
               29: "水晶牌", 33: "迷幻牌", 34: "黑玉牌", 35: "黑莲牌", 37: "幸运牌",
               9999: "真言牌"}

_data_relic_names = []
_data_offering_names = []
_data_baopai_names = {}
_data_pailing_names = {}

_EVENT_NAME_RE = re.compile(r"^(事件|常规)_(.+)$")
_MRP_NAME_RE = re.compile(r"^(事件|常规)(\d+)_(.+)$")
_GAMEEVENT_SPEC = [("id", "s"), ("rarity", "i"), ("displayName", "s"),
                   ("eventType", "i"), ("description", "s"), ("memo", "s")]


def set_data_names(relic_names, offering_names, baopai_names=None, pailing_names=None):
    global _data_relic_names, _data_offering_names, _data_baopai_names, _data_pailing_names
    _data_relic_names = relic_names
    _data_offering_names = offering_names
    _data_baopai_names = dict(baopai_names or {})
    _data_pailing_names = dict(pailing_names or {})


def _lingyou_name_by_pid(ctx, pid):
    return ctx["xc_names"].get(pid) or ""


def _pool_filter_str(n):
    """EventNode tags/rarities → 可读池限制；任意/通用/无则返回空串。"""
    parts = []
    seen = set()
    for r in n.get("rarities") or []:
        iv = int(r)
        if iv in (99, 0):
            continue
        nm = RARITY_CN.get(iv, str(iv))
        if nm not in seen:
            seen.add(nm)
            parts.append(nm)
    for t in n.get("tags") or []:
        iv = int(t)
        if iv in (0, 69999, 99999):
            continue
        nm = TAG_ID_CN.get(iv, str(iv))
        if nm not in seen:
            seen.add(nm)
            parts.append(nm)
    return "/".join(parts)


def _relic_name(ctx, rid):
    return ctx["relic_names"].get(rid, str(rid))


def _offering_name(ctx, oid):
    return ctx["offering_names"].get(oid, str(oid))


def _baoling_name(bid):
    if bid in _data_baopai_names:
        return _data_baopai_names[bid]
    if bid in _data_pailing_names:
        return _data_pailing_names[bid]
    return ctx_baoling.get(bid, str(bid))


def _baoling_kind(n):
    """判定 type 32/42 效果是宝牌还是牌灵。

    baoPai/paiLing 可能同时为真（游戏数据如此），此时按 ID 空间判定:
    牌灵 ID >= 10000, 宝牌 ID < 10000。
    """
    ids = n.get("baoLingGetList") or []
    if ids:
        if all(int(i) >= 10000 for i in ids):
            return "牌灵"
        if all(int(i) < 10000 for i in ids):
            return "宝牌"
    is_pal = bool(n.get("paiLing"))
    is_bao = bool(n.get("baoPai"))
    if is_pal and not is_bao:
        return "牌灵"
    if is_bao and not is_pal:
        return "宝牌"
    if is_pal:
        return "牌灵"
    return "宝牌"


def _fmt_effect(n, ctx):
    t = n["type"]
    lab = NODE_TYPE_LABELS.get(t, f"效果{t}")
    parts = []
    cal = n.get("calSymbol") or ""
    if t in (10, 20) and n.get("baseScore"): parts.append(f"底分{n['baseScore']:+d}")
    if t in (11, 21) and n.get("fan"): parts.append(f"番{n['fan']:+d}")
    if t in (14, 24) and n.get("hp"):
        hv = -abs(n["hp"]) if cal == "-" else abs(n["hp"]) if cal == "+" else n["hp"]
        if n.get("ceiling"):
            parts.append(f"血上限{hv:+d}")
        else:
            parts.append(f"血{hv:+d}")
    elif t in (14, 24):
        return ""
    if t in (15, 25) and n.get("hun"):
        hv = -abs(n["hun"]) if cal == "-" else abs(n["hun"]) if cal == "+" else n["hun"]
        if n.get("ceiling"):
            parts.append(f"魂力上限{hv:+g}")
        else:
            parts.append(f"魂{hv:+g}")
    if t == 23:
        fv = n.get("floatValue") or 0.0
        if not fv and n.get("range"):
            fv = float(n["range"][0] or 0.0)
        if fv:
            cal = n.get("calSymbol") or ""
            if cal == "-":
                fv = -abs(fv)
            elif cal == "+":
                fv = abs(fv)
            parts.append(f"金币{fv:+g}")
    if t in (31, 35, 41):
        names = [_lingyou_name_by_pid(ctx, (r or {}).get("path_id"))
                 for r in (n.get("xiaoChouPaiGetList") or [])]
        names = [x for x in names if x]
        if names: parts.append("".join(names) if t != 41 else "失去" + "".join(names))
    if t in (32, 42) and n.get("baoLingGetList"):
        kind = _baoling_kind(n)
        ids = n["baoLingGetList"]
        names = "/".join(_baoling_name(i) for i in ids)
        verb = "失去" if t == 42 else "获得"
        if len(ids) > 1:
            return f"{verb}随机{kind}"
        return f"{verb}{kind}({names})"
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


def _load_catalog():
    """加载 Addressables catalog.bin（GUID -> EventImage 路径）。失败返回 None。"""
    try:
        if CATALOG_BIN and Path(CATALOG_BIN).exists():
            return Catalog.load_bin(CATALOG_BIN)
    except Exception as e:
        print(f"  catalog.bin load failed: {e}")
    return None


def _event_title_from_gname(nm):
    """GameEvent m_Name (事件_xxx / 常规_xxx) -> 事件标题；非事件返回 None。"""
    m = _EVENT_NAME_RE.match(nm or "")
    return m.group(2) if m else None


def _collect_type6_icons(ge_by_name, resolve_node, catalog):
    """从各 GameEvent 的 type=6 (EventImage) 节点 spriteGUID 解析封面图。

    返回 {事件标题: sprite 文件名 stem}。catalog 缺失或 GUID 无效则跳过。
    """
    if catalog is None:
        return {}
    result = {}
    for nm, ge in ge_by_name.items():
        title = _event_title_from_gname(nm)
        if not title:
            continue
        gfile = ge.get("_file", "")
        t6 = []
        for fid, pid in ge.get("node_refs") or []:
            n = resolve_node(gfile, fid, pid)
            if n is not None and n.get("type") == 6:
                t6.append(n)
        if not t6:
            continue
        pick = next((n for n in t6 if n.get("id") == "1"), t6[0])
        stem = catalog.guid_to_sprite_stem(pick.get("spriteGUID") or "")
        if stem:
            result[title] = stem
    return result


def _extract_event_icons(bsf, title_to_sprite=None):
    """从 bundle 中提取事件插图 (Sprite -> PNG) 到 site/icons/events/。

    title_to_sprite: {中文事件名: sprite 文件名 stem}；由 type6 spriteGUID
    经 catalog 解析得到。缺省时回退到内置 EVENT_ICON_MAP。
    """
    out_dir = SITE_DIR / "icons" / "events"
    out_dir.mkdir(parents=True, exist_ok=True)

    sprite_objs = {}
    sprite_lower = {}
    for obj in bsf.objects.values():
        if obj.type.name == "Sprite":
            try:
                d = obj.read()
                nm = getattr(d, "m_Name", "")
                if nm:
                    sprite_objs[nm] = obj
                    sprite_lower.setdefault(nm.lower(), nm)
            except Exception:
                pass

    # type6 解析失败的事件回退到硬编码表（几乎不再命中）
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
        "阴寿将尽": "Yingshoujiangjin",
        "青铜鹤": "Qingtonghe",
        "龙息谷": "Longxigu",
        "龟驮碑": "Guituobei",
        "牌风测试": "Guigeceshi",
        "冥府磨坊": "Mofangjingli",
        "风灵珠": "Dingfengzhu",
    }

    merged = dict(EVENT_ICON_MAP)
    if title_to_sprite:
        merged.update(title_to_sprite)

    result = {}
    count = 0
    for cn_name, sprite_name in merged.items():
        actual = sprite_name
        obj = sprite_objs.get(actual)
        if obj is None:
            actual = sprite_lower.get(sprite_name.lower())
            obj = sprite_objs.get(actual) if actual else None
        if obj is None or not actual:
            continue
        try:
            img = obj.read().image
            fname = f"{actual}.png"
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


def _collect_event_ids(*sfs):
    """从多个 SerializedFile 收集事件数值 ID: MapRandomPoolItem(优先) + GameEvent(回退)。"""
    ge_ids = {}
    mrp_ids = {}
    for sf in sfs:
        if sf is None:
            continue
        for pid, obj in sf.objects.items():
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                d = obj.read(check_read=False)
                mn = getattr(d, "m_Name", "") or ""
                cn = getattr(d.m_Script.read(), "m_ClassName", "")
            except Exception:
                continue
            raw = obj.get_raw_data()
            if cn == "MapRandomPoolItem":
                m = _MRP_NAME_RE.match(mn)
                if not m:
                    continue
                try:
                    _, _, _, _, pos = rp.mb_header(raw)
                    sid = rp.RawReader(raw, pos).string()
                    num = int(sid) if sid.isdigit() else int(m.group(2))
                    mrp_ids[(m.group(1), m.group(3))] = num
                except Exception:
                    pass
            elif cn == "GameEvent":
                m = _EVENT_NAME_RE.match(mn)
                if not m:
                    continue
                try:
                    _, _, _, _, pos = rp.mb_header(raw)
                    f = rp.parse_fields(raw, pos, _GAMEEVENT_SPEC)
                    sid = str(f.get("id", ""))
                    if sid.isdigit():
                        ge_ids[(m.group(1), m.group(2))] = int(sid)
                except Exception:
                    pass
    ids = dict(ge_ids)
    ids.update(mrp_ids)  # MapRandomPoolItem 覆盖 GameEvent（避免 GE id 冲突）
    return ids


def _parse_gameevent_raw(raw, name):
    """GameEvent: 已知字段 + nodes(PPtr列表) + initID。失败返回 None。"""
    try:
        _, _, _, _, pos = rp.mb_header(raw)
        f = rp.parse_fields(raw, pos, _GAMEEVENT_SPEC)
        r = rp.RawReader(raw, 0)
        r.p = pos
        r.string()  # id
        r.i32()     # rarity
        r.string()  # displayName
        r.i32()     # eventType
        r.string()  # description
        r.string()  # memo
        after = r.p
        cnt = struct.unpack_from("<i", raw, after)[0]
        if not (0 <= cnt < 500):
            return None
        node_refs = []
        p = after + 4
        for _ in range(cnt):
            fid = struct.unpack_from("<i", raw, p)[0]
            pid = struct.unpack_from("<q", raw, p + 4)[0]
            node_refs.append((fid, pid))
            p += 12
        init_id = rp.RawReader(raw, p).string()
        return {**f, "m_Name": name, "node_refs": node_refs, "initID": init_id}
    except Exception:
        return None


def _load_graph_sfs():
    """加载含 EventNode/NodePort/GameEvent 的 SerializedFile 列表。"""
    sfs = []
    am = AssetsManager()
    for ms_bf in AA_DIR.glob("*_monoscripts_*.bundle"):
        am.load_file(str(ms_bf))
        break
    bf = am.load_file(str(BUNDLE_PATH))
    cab_keys = [k for k in bf.files if k.startswith("CAB-")]
    bsf = bf.files[cab_keys[0]]
    sfs.append(("bundle", bsf, am))

    for tag, path in (("s0", SHARED0), ("s1", SHARED1), ("s2", SHARED2),
                      ("s3", SHARED3), ("s4", SHARED4)):
        if path is None or not Path(path).exists():
            continue
        amN = AssetsManager()
        try:
            sf = amN.load_file(str(path))
        except Exception:
            continue
        sfs.append((tag, sf, amN))
    return sfs, bsf


def _index_graph_objects(sfs):
    """按 (file_tag, path_id) 索引 EventNode / NodePort。

    sharedassets 类型树被剥离，必须 check_read=False + rawparse。
    """
    node_by_key = {}
    port_by_key = {}
    node_by_pid = {}
    port_by_pid = {}
    for tag, sf, _am in sfs:
        for pid, obj in sf.objects.items():
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                d = obj.read(check_read=False)
                ms = getattr(d, "m_Script", None)
                if not ms:
                    continue
                cn = getattr(ms.read(), "m_ClassName", "")
            except Exception:
                continue
            if cn not in ("EventNode", "NodePort"):
                continue
            try:
                raw = obj.get_raw_data()
                if cn == "EventNode":
                    n = rp.parse_payload(raw, "EventNode")
                    n["_file"] = tag
                    n["_pid"] = pid
                    node_by_key[(tag, pid)] = n
                    node_by_pid.setdefault(pid, []).append(n)
                else:
                    p = rp.parse_payload(raw, "NodePort")
                    p["_file"] = tag
                    p["_pid"] = pid
                    port_by_key[(tag, pid)] = p
                    port_by_pid.setdefault(pid, []).append(p)
            except Exception:
                pass
    return node_by_key, port_by_pid, port_by_key


def _collect_gameevents(sfs):
    gameevents = []
    for tag, sf, _am in sfs:
        for pid, obj in sf.objects.items():
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                d = obj.read(check_read=False)
                mn = getattr(d, "m_Name", "") or ""
                cn = getattr(d.m_Script.read(), "m_ClassName", "")
            except Exception:
                continue
            if cn != "GameEvent":
                continue
            g = _parse_gameevent_raw(obj.get_raw_data(), mn)
            if g is None:
                continue
            g["_file"] = tag
            g["_pid"] = pid
            gameevents.append(g)
    return gameevents


def _resolve_pptr(file_tag, fid, pid, by_key, by_pid):
    """PPtr 解析：file_id=0 视为同文件；否则按 path_id 列表回退。"""
    if fid == 0:
        hit = by_key.get((file_tag, pid))
        if hit is not None:
            return hit
    # 跨文件：path_id 碰撞时取第一个
    lst = by_pid.get(pid) or []
    return lst[0] if lst else None


def extract_events(i2):
    """神秘事件 v5: 按 GameEvent 圈定子图 + 端口选项 + 效果 BFS。"""
    print("  loading event graph...")
    sfs, bsf = _load_graph_sfs()
    sf4 = next((sf for tag, sf, _am in sfs if tag == "s4"), None)
    node_by_key, port_by_pid, port_by_key = _index_graph_objects(sfs)
    print(f"  EventNode={len(node_by_key)}, NodePort={len(port_by_key)}")

    gameevents = _collect_gameevents(sfs)
    print(f"  GameEvent={len(gameevents)}")

    node_by_pid = {}
    for (_t, _p), n in node_by_key.items():
        node_by_pid.setdefault(_p, []).append(n)

    def _resolve_node(gfile, fid, pid):
        if fid == 0:
            hit = node_by_key.get((gfile, pid))
            if hit is not None:
                return hit
        lst = node_by_pid.get(pid) or []
        return lst[0] if lst else None

    def _local_graph(ge):
        local = {}
        gfile = ge.get("_file", "")
        for fid, pid in ge.get("node_refs") or []:
            n = _resolve_node(gfile, fid, pid)
            if n is not None:
                local[n["id"]] = n
        return local

    # 同名 GameEvent 可能有多份（bundle 权威 / shared 副本）——
    # 优先选 node_refs 能解析出 EventNode 的那份。
    ge_by_name = {}
    for g in gameevents:
        name = g["m_Name"]
        prev = ge_by_name.get(name)
        if prev is None:
            ge_by_name[name] = g
            continue
        prev_ok = sum(
            1
            for fid, pid in prev.get("node_refs") or []
            if _resolve_node(prev.get("_file", ""), fid, pid) is not None
        )
        cur_ok = sum(
            1
            for fid, pid in g.get("node_refs") or []
            if _resolve_node(g.get("_file", ""), fid, pid) is not None
        )
        if cur_ok > prev_ok or (cur_ok == prev_ok and prev.get("_file") != "bundle" and g.get("_file") == "bundle"):
            ge_by_name[name] = g

    catalog = _load_catalog()
    type6_icons = _collect_type6_icons(ge_by_name, _resolve_node, catalog)
    print(f"  type6 spriteGUID icons: {len(type6_icons)} resolved via catalog")
    icon_map = _extract_event_icons(bsf, type6_icons)
    _extract_buff_icons(bsf)

    ctx = {"xc_names": {}, "relic_names": {}, "offering_names": {}}
    for _tag, sf, _am in sfs:
        try:
            cls, _ = classify_monobehaviours(sf)
        except Exception:
            continue
        for pid in cls.get("XiaoChouPaiPayload", []):
            try:
                d = rp.parse_payload(sf.objects[pid].get_raw_data(), "XiaoChouPaiPayload")
                nm = tr(d.get("displayNameTerm", ""), i2) or d.get("m_Name", "")
                if nm:
                    ctx["xc_names"][pid] = nm
            except Exception:
                pass
    for e in _data_relic_names:
        ctx["relic_names"][e[0]] = e[1]
    for e in _data_offering_names:
        oid, nm = e[0], e[1]
        prev = ctx["offering_names"].get(oid)
        if prev is None or (prev.endswith("+") and not nm.endswith("+")):
            ctx["offering_names"][oid] = nm

    # GameEvent path_id -> eventType（用于 type 78 格式化）
    ge_type_by_pid = {}
    for g in gameevents:
        ge_type_by_pid[(g["_file"], g["_pid"])] = g.get("eventType", 0)
        ge_type_by_pid.setdefault(g["_pid"], g.get("eventType", 0))

    def _fmt_effect_inner(n, n_file, ctx):
        t = n["type"]
        lab = NODE_TYPE_LABELS.get(t, f"效果{t}")
        parts = []
        cal = n.get("calSymbol") or ""
        if t in (10, 20) and n.get("baseScore"):
            parts.append(f"底分{n['baseScore']:+d}")
        if t in (11, 21) and n.get("fan"):
            parts.append(f"番{n['fan']:+d}")
        if t in (14, 24) and n.get("hp"):
            hv = -abs(n["hp"]) if cal == "-" else abs(n["hp"]) if cal == "+" else n["hp"]
            if n.get("ceiling"):
                parts.append(f"血上限{hv:+d}")
            else:
                parts.append(f"血{hv:+d}")
        elif t in (14, 24):
            return ""
        if t in (15, 25) and n.get("hun") is not None and n.get("hun") != 0:
            hv = -abs(n["hun"]) if cal == "-" else abs(n["hun"]) if cal == "+" else n["hun"]
            if n.get("ceiling"):
                parts.append(f"魂力上限{hv:+g}")
            else:
                parts.append(f"魂{hv:+g}")
        if t == 23:
            fv = n.get("floatValue") or 0.0
            if not fv and n.get("range"):
                fv = float(n["range"][0] or 0.0)
            if fv:
                if cal == "-":
                    fv = -abs(fv)
                elif cal == "+":
                    fv = abs(fv)
                parts.append(f"金币{fv:+g}")
        if t in (31, 35, 41):
            names = [
                _lingyou_name_by_pid(ctx, (r or {}).get("path_id"))
                for r in (n.get("xiaoChouPaiGetList") or [])
            ]
            names = [x for x in names if x]
            verb = "失去" if t == 41 else "获得"
            kind = "临时灵佣" if t == 35 else "灵佣"
            if names:
                return f"{verb}{kind}({'/'.join(names)})"
            filt = _pool_filter_str(n)
            if filt:
                rnd = "随机" if n.get("randomType") else ""
                return f"{verb}{rnd}{kind}({filt})"
            return f"{verb}{kind}"
        if t in (32, 42):
            kind = _baoling_kind(n)
            ids = n.get("baoLingGetList") or []
            names = []
            for i in ids:
                if kind == "牌灵":
                    nm = _data_pailing_names.get(i) or _data_baopai_names.get(i) or ctx_baoling.get(i)
                else:
                    nm = _data_baopai_names.get(i) or ctx_baoling.get(i) or _data_pailing_names.get(i)
                if nm:
                    names.append(str(nm))
            verb = "失去" if t == 42 else "获得"
            if names:
                if len(ids) > 1:
                    return f"{verb}随机{kind}"
                return f"{verb}{kind}({'/'.join(names)})"
            if n.get("randomType"):
                return f"{verb}随机{kind}"
            return f"{verb}{kind}"
        if t in (33, 43):
            verb = "失去" if t == 43 else "获得"
            if n.get("relicGetList"):
                return f"{verb}遗物({'/'.join(_relic_name(ctx, i) for i in n['relicGetList'])})"
            filt = _pool_filter_str(n)
            if filt:
                rnd = "随机" if n.get("randomType") else ""
                return f"{verb}{rnd}遗物({filt})"
            return f"{verb}遗物"
        if t in (34, 44):
            verb = "失去" if t == 44 else "获得"
            if n.get("offeringGetList"):
                return f"{verb}祭品({'/'.join(_offering_name(ctx, i) for i in n['offeringGetList'])})"
            filt = _pool_filter_str(n)
            if filt:
                rnd = "随机" if n.get("randomType") else ""
                return f"{verb}{rnd}祭品({filt})"
            return f"{verb}祭品"
        if t == 49:
            parts.append(f"层数 {n.get('level', '?')}")
        if t == 52:
            parts.append(f"难度 {n.get('level', '?')}")
        if t in (450, 452) and n.get("characterID"):
            parts.append(f"角色{n['characterID']}等级{n.get('level', '')}")
        if t == 70:
            parts.append("选择牌面")
        if t == 29:
            gdt = n.get("globalDataType", 0)
            gname = GLOBAL_DATA_CN.get(gdt, f"全局{gdt}")
            fv = n.get("floatValue")
            sym = n.get("calSymbol") or "="
            if fv is None:
                return f"设置{gname}"
            if float(fv) == int(float(fv)):
                fvs = str(int(float(fv)))
            else:
                fvs = f"{float(fv):g}"
            return f"设置{gname}{sym}{fvs}"
        if t == 78:
            ge = n.get("gameEvent") or {}
            et = ge_type_by_pid.get((n_file, ge.get("path_id"))) or ge_type_by_pid.get(
                ge.get("path_id")
            )
            if et is None:
                return "进入子事件"
            return f"进入{EVENT_TYPE_CN.get(et, f'事件{et}')}"
        if t == 79:
            return "麻将对局"
        if t == 95:
            en = n.get("eventName") or ""
            return f"发送事件 {en}".rstrip() if en else "发送事件"
        if t == 96:
            return f"跳转到节点 {n.get('id', '?')}"
        if t in (500, 510):
            return "商店配置"
        if t in (600, 610):
            return "当铺"
        if not parts:
            return lab
        # 魂/血等：优先展示参数本身（含 ceiling → 魂力上限）
        if t in (15, 25) and n.get("ceiling") and parts:
            return parts[0]
        return f"{lab}({', '.join(parts)})"

    def _out_ports(n):
        res = []
        n_file = n.get("_file", "")
        for pr in (n.get("ports") or []):
            fid = pr.get("file_id", 0)
            pid = pr.get("path_id")
            pp = _resolve_pptr(n_file, fid, pid, port_by_key, port_by_pid)
            if pp is not None:
                res.append(pp)
        return res

    def _collect_effects(local, start_id):
        """从选项目标 BFS，收集效果节点。

        - type 4/51 玩家并列选项：不跨越（避免串兄弟分支）
        - 例外：若已经过 type 50 随机分支，后续 type 4 是随机结果文本，可跨越
        """
        effects = []
        visited = set()
        q = deque([start_id])
        steps = 0
        seen_random = False
        while q and len(effects) < 8 and steps < 64:
            steps += 1
            nid = q.popleft()
            if nid in visited:
                continue
            visited.add(nid)
            m = local.get(nid)
            if m is None:
                continue
            mt = m["type"]
            if mt == 50:
                seen_random = True
            if mt in EFFECT_TYPES:
                fx = _fmt_effect_inner(m, m.get("_file", ""), ctx)
                if fx and fx not in effects:
                    effects.append(fx)
            # type 51 随机选项：停
            # type 4：并列玩家选项（多端口且非随机结果）停；单端口确认选项继续
            if mt == 51:
                continue
            if mt == 4 and not seen_random:
                ports_n = _out_ports(m)
                if len(ports_n) > 1:
                    continue
            if mt in _STOP_CROSS_TYPES and mt != 4:
                continue
            for pp in _out_ports(m):
                t2 = pp.get("targetNode")
                if t2 and t2 not in visited:
                    q.append(t2)
        return effects

    # 事件文本 JSON
    event_jsons = {}

    def _load_event_jsons(sf):
        for pid, obj in sf.objects.items():
            if obj.type.name != "TextAsset":
                continue
            try:
                d = obj.read()
                nm, data = d.m_Name, d.m_Script
            except Exception:
                continue
            if isinstance(data, str):
                data = data.encode("utf-8", "ignore")
            if not (
                isinstance(nm, str)
                and (nm.startswith(chr(20107) + chr(20214) + "_") or nm.startswith(chr(24120) + chr(35215) + "_"))
            ):
                continue
            if nm in event_jsons:
                continue
            try:
                event_jsons[nm] = json.loads(data)
            except Exception:
                pass

    _load_event_jsons(bsf)
    for _tag, sf, _am in sfs:
        if _tag != "bundle":
            _load_event_jsons(sf)
    print(f"  event JSONs loaded: {len(event_jsons)}")

    event_ids = _collect_event_ids(bsf, sf4)
    print(f"  event numeric IDs collected: {len(event_ids)}")

    events = []
    fx_stats = {"opt": 0, "with_fx": 0, "no_ge": 0}
    for nmj, j in sorted(event_jsons.items()):
        ev_map = {}
        for t in j.get("TextTerms", []):
            if t.get("Key") and t.get("Chinese"):
                ev_map[t["Key"]] = t["Chinese"]
        if not ev_map:
            continue
        ev_tags = set(ev_map.keys())
        title = nmj.replace(chr(20107) + chr(20214) + "_", "").replace(chr(24120) + chr(35215) + "_", "")
        kind = (
            chr(20107) + chr(20214)
            if nmj.startswith(chr(20107) + chr(20214) + "_")
            else chr(24120) + chr(35215)
        )

        ge = ge_by_name.get(nmj)
        local = _local_graph(ge) if ge and ge.get("node_refs") is not None else {}
        if not ge or not ge.get("node_refs"):
            fx_stats["no_ge"] += 1

        # 本事件子图内按 tag 匹配文本节点
        matched = [n for n in local.values() if n.get("textContentTag") in ev_tags]
        # 回退：子图为空时用全局 tag 匹配（旧逻辑，至少保住文案）
        if not matched:
            matched = [
                n
                for n in node_by_key.values()
                if n.get("textContentTag") in ev_tags
            ]

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
            kept = [
                l
                for l in lines
                if not l.strip().startswith("[") and not l.strip().startswith(chr(12304))
            ]
            texts = ["\n".join(kept).strip()]
        else:
            cleaned = []
            for t in texts:
                lines = t.split("\n")
                kept = [
                    l
                    for l in lines
                    if not l.strip().startswith("[") and not l.strip().startswith(chr(12304))
                ]
                cleaned_text = "\n".join(kept).strip()
                if cleaned_text:
                    cleaned.append(cleaned_text)
            texts = cleaned

        options, seen_opt = [], set()
        limits = []
        graph_effects_by_tag = {}
        graph_effects = {}

        # limits：子图节点 memo / 分支
        for n in local.values():
            if n.get("memo"):
                limits.append(n["memo"])
            if n["type"] in (49, 52):
                limits.append(_fmt_effect_inner(n, n.get("_file", ""), ctx))

        # 选项端口（tag 挂在端口上）→ 效果 BFS；按 tag 索引
        for n in local.values():
            if n["type"] not in (4, 51):
                continue
            for pp in _out_ports(n):
                ptag = pp.get("textContentTag") or ""
                if ptag not in ev_tags or not ptag:
                    continue
                otxt = pp.get("textContent") or ev_map.get(ptag, "")
                if not otxt:
                    continue
                prev = graph_effects_by_tag.get(ptag)
                if prev:
                    continue
                graph_effects_by_tag[ptag] = _collect_effects(local, pp.get("targetNode"))
                graph_effects[otxt] = graph_effects_by_tag[ptag]

        def _norm_opt(s):
            return (s or "").replace(chr(12304), "[").replace(chr(12305), "]").strip()

        graph_by_norm = {}
        for k, v in graph_effects.items():
            nk = _norm_opt(k)
            if nk and (nk not in graph_by_norm or (v and not graph_by_norm[nk])):
                graph_by_norm[nk] = v

        def _lookup_effects(tag, text):
            if tag and graph_effects_by_tag.get(tag):
                return graph_effects_by_tag[tag]
            if text and graph_effects.get(text):
                return graph_effects[text]
            if text and graph_by_norm.get(_norm_opt(text)):
                return graph_by_norm[_norm_opt(text)]
            if tag and tag in graph_effects_by_tag:
                return graph_effects_by_tag[tag] or []
            if text and _norm_opt(text) in graph_by_norm:
                return graph_by_norm[_norm_opt(text)] or []
            return []

        term_list = j.get("TextTerms", [])
        pending_opt = None
        pending_opt_tag = None
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
                        eff = _lookup_effects(pending_opt_tag, pending_opt)
                        options.append(
                            {"text": pending_opt, "effects": eff, "result": result}
                        )
                pending_opt = ch
                pending_opt_tag = t.get("Key") or ""
                pending_result_parts = []
            else:
                if pending_opt is not None:
                    pending_result_parts.append(ch)
        if pending_opt is not None:
            result = "\n".join(pending_result_parts).strip()
            key = pending_opt + "|"
            if key not in seen_opt:
                seen_opt.add(key)
                eff = _lookup_effects(pending_opt_tag, pending_opt)
                options.append({"text": pending_opt, "effects": eff, "result": result})

        fx_stats["opt"] += len(options)
        fx_stats["with_fx"] += sum(1 for o in options if o.get("effects"))

        if not texts and not options:
            continue
        eid = event_ids.get((kind, title))
        ev = {
            "id": eid if eid is not None else 0,
            "name": title,
            "kind": kind,
            "limits": sorted(set(l for l in limits if l)),
            "desc": chr(10).join(texts),
            "options": options,
        }
        if ev_icon:
            ev["icon"] = ev_icon
        events.append(ev)
    events.sort(key=lambda e: (e["kind"], e["id"] if e["id"] else 10**9, e["name"]))
    print(
        f"  events extracted: {len(events)} | options={fx_stats['opt']} "
        f"with_effects={fx_stats['with_fx']} no_ge={fx_stats['no_ge']}"
    )
    return events
