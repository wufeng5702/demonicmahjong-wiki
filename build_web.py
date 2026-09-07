#!/usr/bin/env python3
"""
Demonic Mahjong - 网页数据构建脚本
====================================
从游戏资源中提取数据，生成可离线搜索的本地网页 (site/)。

模块拆分:
  lib/config.py         - 环境变量、路径常量、bundle 定位
  lib/enums.py          - 枚举解析、标签/稀有度中文化
  lib/i2parse.py        - I2 本地化解析、翻译查找、文本回填
  lib/extract_bundle.py - 主 bundle 数据提取
  lib/extract_shared.py - sharedassets 数据提取
  lib/merge.py          - DLC + 本体数据合并
  lib/extract_events.py - 神秘事件提取
  lib/extract_icons.py  - 全部图标提取 (含牌灵 3D 渲染)

使用方法:
    python build_web.py             # 完整构建（约2-5分钟）
    python build_web.py --web-only  # 仅同步 web_src/ -> site/
"""

import io
import json
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from config import BUNDLE_PATH, SITE_DIR
from enums import parse_all_enums, rarity_name
from i2parse import load_i2_terms, tr, apply_text
from extract_bundle import extract_bundle
from extract_shared import extract_shared_assets
from merge import merge_shared, offering_category
from extract_events import extract_events, set_data_names
from extract_icons import (
    extract_achievement_icons, extract_lingyong_icons,
    extract_character_avatars, extract_character_skill_icons,
    extract_relic_icons, extract_offering_icons,
    extract_offering_skill_icons, extract_baopai_icons,
    render_pailing_icons, composite_skill_icons,
)

DUMP_CS = Path(os.environ.get("DUMP_CS",
    Path(__file__).resolve().parent.parent / "dump_output" / "dump.cs"
    if not Path(os.environ.get("GAME_DIR", "E:\\DemonicMahjong")).exists()
    else Path(os.environ["GAME_DIR"]) / "dump_output" / "dump.cs"))


def copy_web_files():
    """把 web_src/ 同步到 site/。"""
    from config import SITE_DIR as _sd
    WEB_SRC = Path(__file__).parent / "web_src"
    repo_url = os.environ.get("REPO_URL", "")
    for f in ("index.html", "app.js", "style.css", "data.json"):
        src = WEB_SRC / f
        if not src.exists():
            continue
        if f.endswith(".js") or f.endswith(".html"):
            cmd = ["pnpx", "prettier", "--write", str(src)]
            if sys.platform == "win32":
                cmd = ["cmd", "/C"] + cmd
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, shell=True)
                print(f"  web_src/{f} formatted")
            except subprocess.CalledProcessError as e:
                print(f"  web_src/{f} prettier format failed: {e.stderr.strip()}")
        content = src.read_text(encoding="utf-8")
        if repo_url:
            content = content.replace("__REPO_URL__", repo_url)
        (_sd / f).write_text(content, encoding="utf-8")
        print(f"  site/{f} copied")


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

    # 神秘事件: 依赖遗物/祭品/灵佣名称
    relic_names = [(e["id"], e.get("name") or e.get("cn") or e.get("en", ""))
                   for e in data["relics"]]
    offering_names = [(e["id"], e.get("name") or e.get("en", ""))
                      for e in data["offerings"]]
    set_data_names(relic_names, offering_names)
    data["events"] = extract_events(i2)

    total_missing = 0
    for cat, entries in data.items():
        if not isinstance(entries, list):
            continue
        miss = apply_text(entries, i2)
        total_missing += miss
        print(f"  {cat}: {len(entries)} entries ({miss} keys unresolved)")

    # BOSS灵俑: level 从1开始
    for e in data["lingyong"]:
        xid = e.get("id", 0)
        if (10000 <= xid < 20000) or (30000 <= xid < 40000):
            e["level"] = e.get("level", 0) + 1
            name = e.get("name", "")
            e["name"] = re.sub(r"\s*lv\.1$", "", name)

    # 业镜 Buff 图标映射
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
        e["rar"] = kind or base_rar
        e["rar2"] = base_rar

    # 祭品分类
    for e in data["offerings"]:
        e["cat"] = offering_category(e["id"])

    # 排序
    for cat in data:
        if isinstance(data[cat], list):
            data[cat].sort(key=lambda e: (e["id"], e.get("level", 0)))

    print(f"\ntotal unresolved keys: {total_missing}")

    # 导出事件原始数据
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

    print("\n[6/6] extracting icons...")
    extract_achievement_icons()
    extract_lingyong_icons()
    extract_character_avatars()
    extract_character_skill_icons()
    extract_relic_icons()
    extract_offering_icons()
    extract_offering_skill_icons()
    extract_baopai_icons()
    try:
        render_pailing_icons(BUNDLE_PATH, SITE_DIR / "icons")
    except Exception as e:
        print(f"  [WARN] pailing icon rendering failed: {e}")

    # 技能图标合成到底图上
    composite_skill_icons()

    copy_web_files()
    print("\n[DONE]")


if __name__ == "__main__":
    main()
