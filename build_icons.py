#!/usr/bin/env python3
"""独立图标提取脚本: 在新进程中运行, 避免 build_web.py 内存累积导致的 MemoryError。

用法:
    python build_icons.py            # 提取全部图标
    python build_icons.py --only xxx # 仅提取指定类别
"""
import io
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from config import BUNDLE_PATH, SITE_DIR
from extract_icons import (
    extract_achievement_icons, extract_lingyong_icons,
    extract_character_avatars, extract_character_skill_icons,
    extract_relic_icons, extract_offering_icons,
    extract_offering_skill_icons, extract_baopai_icons,
    render_pailing_icons, composite_skill_icons,
)

# (名称, 可调用对象) —— 按依赖顺序排列, composite 必须最后
ICON_STEPS = [
    ("achievement", extract_achievement_icons),
    ("lingyong", extract_lingyong_icons),
    ("character", extract_character_avatars),
    ("character_skill", extract_character_skill_icons),
    ("relic", extract_relic_icons),
    ("offering", extract_offering_icons),
    ("offering_skill", extract_offering_skill_icons),
    ("baopai", extract_baopai_icons),
    ("pailing", lambda: render_pailing_icons(BUNDLE_PATH, SITE_DIR / "icons")),
    ("composite", composite_skill_icons),
]


def main():
    SITE_DIR.mkdir(exist_ok=True)

    # --step <name>: 实际执行单个步骤 (由父进程为每个步骤派生独立子进程,
    # 避免同一进程反复加载 2GB bundle 导致内存耗尽)
    if "--step" in sys.argv:
        name = sys.argv[sys.argv.index("--step") + 1]
        for n, fn in ICON_STEPS:
            if n == name:
                print(f"\n[{n}] extracting...")
                fn()
                return
        print(f"unknown step: {name}")
        sys.exit(1)

    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    failed = []
    for name, fn in ICON_STEPS:
        if only and name != only:
            continue
        # 每个步骤独立子进程运行
        rc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--step", name]).returncode
        if rc != 0:
            failed.append(name)
            print(f"  [WARN] {name} icon extraction subprocess exited with code {rc}")

    from logwarn import flush_warns
    flush_warns("icons")
    if failed:
        print(f"\n[ICONS FAILED: {', '.join(failed)}]")
        sys.exit(1)
    print("\n[ICONS DONE]")


if __name__ == "__main__":
    main()
