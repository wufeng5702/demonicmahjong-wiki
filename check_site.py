#!/usr/bin/env python3
"""站点完整性校验 —— build_web.py / deploy.py 结尾自动运行, 有缺口即非零退出。

把"用户浏览时肉眼发现缺口"变成"构建时自动失败并列出缺口"。

检查项:
  site 模式:    data.json 条目按 web_src/app.js 的分类路由必须有对应图标文件
  deploy 模式:  以上 (针对 site_deploy) + 图标引用全部为 .avif + png↔avif 一一对应

用法:
  uv run python check_site.py            # 校验 output/site
  uv run python check_site.py deploy     # 校验 output/site_deploy
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SITE = BASE / "output" / "site"
DEPLOY = BASE / "output" / "site_deploy"


def _entries(data: dict) -> dict[str, list]:
    """按 app.js getEntries 的路由展开需要头像的分类。

    - lingyong 数组按 ID 区间拆成 灵佣 / BOSS 两栏 (20000+ 角色技能不在栏目展示)
    - offerings 只展示 0 < id < 20000 (20000+ 是角色技能祭品)
    - fanzhong 无头像, 不检查
    """
    ly = data.get("lingyong") or []
    return {
        "characters": data.get("characters") or [],
        "lingyong": [e for e in ly if e["id"] < 10000],
        "bosslingyong": [
            e for e in ly
            if (10000 <= e["id"] < 20000)
            or (30000 <= e["id"] < 40000 and "BOSS主动" in (e.get("tags") or []))
        ],
        "offerings": [
            e for e in (data.get("offerings") or []) if 0 < e["id"] < 20000
        ],
        "relics": data.get("relics") or [],
        "achievements": data.get("achievements") or [],
        "events": data.get("events") or [],
        "pailing": data.get("pailing") or [],
        "baopai": data.get("baopai") or [],
        "yejingbuff": data.get("yejingbuff") or [],
    }


def _icon_rel(cat: str, e: dict) -> str | None:
    """期望图标相对路径 (无后缀)。enum 占位条目返回 None (允许无图标)。"""
    if e.get("src") == "enum":
        return None
    # avatarHtml/cardHtml 一律优先使用 e.icon 字段
    if e.get("icon"):
        return str(e["icon"]).rsplit(".", 1)[0]
    if cat == "characters":
        sub = "character"
    elif cat == "lingyong":
        sub = "lingyong"
    elif cat == "bosslingyong":
        sub = "lingyong_BOSS"
    elif cat == "offerings":
        sub = "offerings"
    elif cat == "relics":
        sub = "relics"
    elif cat == "achievements":
        sub = "achievements"
    elif cat == "pailing":
        sub = "pailing"
    elif cat == "baopai":
        sub = "baopai"
    elif cat in ("events", "yejingbuff"):
        sub = "events" if cat == "events" else "buff"
    else:
        return None
    return f"icons/{sub}/{e['id']}"


def collect_errors(root: Path, suffix: str) -> list[str]:
    """校验 root 目录 (data.json + 图标), 返回错误列表。suffix: .png / .avif"""
    data_path = root / "data.json"
    if not data_path.exists():
        return [f"{data_path} 不存在"]
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))["data"]
    except Exception as e:
        return [f"data.json 解析失败: {e}"]

    errs = []
    for cat, entries in _entries(data).items():
        for e in entries:
            rel = _icon_rel(cat, e)
            if rel is None:
                continue
            if not (root / f"{rel}{suffix}").exists():
                label = e.get("en") or e.get("name") or ""
                errs.append(f"{cat} id={e['id']} {label} 缺图标 {rel}{suffix}")
    return errs


def collect_deploy_errors() -> list[str]:
    """deploy 模式: site 校验 + avif 引用/文件一致性。"""
    errs = collect_errors(DEPLOY, ".avif")

    # 1) site 的每个图标 png 在 deploy 必须有对应 avif (反向孤儿也报错)
    site_icons = SITE / "icons"
    deploy_icons = DEPLOY / "icons"
    if site_icons.is_dir():
        for png in site_icons.rglob("*.png"):
            rel = png.relative_to(site_icons).with_suffix(".avif")
            if not (deploy_icons / rel).exists():
                errs.append(f"icons/{rel} 缺失 (site 有对应 png)")
    if deploy_icons.is_dir():
        for avif in deploy_icons.rglob("*.avif"):
            rel = avif.relative_to(deploy_icons).with_suffix(".png")
            if not (site_icons / rel).exists():
                errs.append(f"icons/{avif.relative_to(deploy_icons)} 孤儿 avif (site 无对应 png)")

    # 2) 引用中不得残留 icons/*.png
    png_ref = re.compile(r"icons/[^\"'`\s]+\.png")
    for pat in ("*.html", "*.js", "*.css", "*.json"):
        for f in DEPLOY.rglob(pat):
            text = f.read_text(encoding="utf-8", errors="ignore")
            for m in png_ref.finditer(text):
                errs.append(f"{f.name}: 残留 png 引用 {m.group()}")

    # 3) ICON_EXT 常量 (存在时) 必须已切换
    app_js = DEPLOY / "app.js"
    if app_js.exists():
        text = app_js.read_text(encoding="utf-8", errors="ignore")
        if "ICON_EXT" in text and 'ICON_EXT = ".avif"' not in text:
            errs.append('app.js: ICON_EXT 未切换为 ".avif"')

    return errs


def report(mode: str, errs: list[str]) -> None:
    if errs:
        print(f"check {mode}: FAILED ({len(errs)} 处)")
        for e in errs[:30]:
            print(f"  - {e}")
        if len(errs) > 30:
            print(f"  ... 还有 {len(errs) - 30} 条")
        raise SystemExit(1)
    print(f"check {mode}: OK")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "site"
    if mode == "deploy":
        report(mode, collect_deploy_errors())
    else:
        report(mode, collect_errors(SITE, ".png"))


if __name__ == "__main__":
    main()
