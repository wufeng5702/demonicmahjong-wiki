"""data.json 条目构造 —— 字段名/顺序的单一来源。

extract_shared (本体 sharedassets) 与 extract_bundle (DLC 主 bundle) 必须
产出同构条目: 字段结构改动只改这里, 两处自动同步, 避免"修一处漏一处"。

约定:
- 必填字段用 keyword-only 传入
- 可选字段 (icon_pid / src) 为 None 时不写入 key
"""
from __future__ import annotations


def relic_entry(*, id, rarity, stack, kind, src,
                nameKey="", descKey="", en="", cn="", icon_pid=None):
    e = {
        "id": int(id),
        "en": en,
        "cn": cn,
        "nameKey": nameKey,
        "descKey": descKey,
        "rarity": int(rarity),
        "stack": int(stack),
        "kind": kind,
    }
    if icon_pid is not None:
        e["icon_pid"] = icon_pid
    e["src"] = src
    return e


def offering_entry(*, id, en="", level=0, nameKey="", descKey="", adds=None,
                   fanZhong=0, useTiming=0, useType=0, icon_pid=None, src=None):
    e = {
        "id": int(id),
        "en": en,
        "level": int(level),
        "nameKey": nameKey,
        "descKey": descKey,
        "adds": adds if adds is not None else {},
        "fanZhong": int(fanZhong),
        "useTiming": int(useTiming),
        "useType": int(useType),
    }
    if icon_pid is not None:
        e["icon_pid"] = icon_pid
    if src is not None:
        e["src"] = src
    return e
