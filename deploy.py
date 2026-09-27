"""部署脚本: 裁剪压缩图标 → output/site_deploy/"""
import json
import re
import shutil
from pathlib import Path
from PIL import Image

SITE = Path(__file__).parent / "output" / "site"
DEPLOY = Path(__file__).parent / "output" / "site_deploy"
ICON_HEIGHT = 128  # 裁剪目标高度 (网页显示64px, 2x适配)

# 部署输出图片格式 (单一来源, check_site/tests 引用同一常量)
IMG_FORMATS = {".webp": "WEBP", ".avif": "AVIF"}
IMG_EXT = ".webp"
IMG_QUALITY = 75
LEGACY_EXTS = tuple(e for e in IMG_FORMATS if e != IMG_EXT)  # 换格式后清理旧产物


def _pixels_differ(a, b):
    """逐像素比较两张图片是否不同 (忽略 EXIF 等元数据)。"""
    try:
        img_a = Image.open(a).convert("RGBA")
        img_b = Image.open(b).convert("RGBA")
        if img_a.size != img_b.size:
            return True
        return img_a.tobytes() != img_b.tobytes()
    except Exception:
        return True


def _optimize_one(src_png):
    """将单张 PNG 裁剪为部署格式 (始终保留 png, 页面只引用 IMG_EXT)。"""
    img = Image.open(src_png)
    ratio = ICON_HEIGHT / img.height
    new_w = max(1, int(img.width * ratio))
    img = img.resize((new_w, ICON_HEIGHT), Image.LANCZOS)
    img.save(src_png.with_suffix(IMG_EXT), IMG_FORMATS[IMG_EXT], quality=IMG_QUALITY)


def _sync_site(src, dst):
    """同步 site → site_deploy 中非图标文件 (源 mtime 清单增量)。

    用 .sync_manifest.json 记录源文件 mtime: deploy 改写产物后不会导致
    下次误判"源变了"而反复复制 (旧 mtime 对比方案的问题)。
    """
    manifest_path = dst / ".sync_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        manifest = {}
    src_files = set()
    copied = removed = changed = 0
    for root, _, files in src.walk():
        rel_dir = Path(root).relative_to(src)
        if rel_dir.parts and rel_dir.parts[0] == "icons":
            continue
        for f in files:
            s = Path(root) / f
            rel = s.relative_to(src)
            d = dst / rel
            src_files.add(rel)
            if d.exists() and manifest.get(str(rel)) == s.stat().st_mtime:
                continue
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
            manifest[str(rel)] = s.stat().st_mtime
            copied += 1
            changed = True
    for f in dst.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(dst)
        if rel.parts[0] == "icons" or rel.name == ".sync_manifest.json":
            continue
        if rel not in src_files:
            f.unlink()
            removed += 1
    for k in list(manifest):
        if Path(k) not in src_files:
            del manifest[k]
            changed = True
    if changed:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    if copied or removed:
        print(f"  site: {copied} copied, {removed} removed")


def sync_and_optimize(src_dir, dst_dir):
    """增量同步 + 优化: 像素变化才复制并生成 IMG_EXT, 未变化则跳过。"""
    src_pngs = set()
    copied = removed = optimized = skipped = 0
    first_run = not any(dst_dir.rglob(f"*{IMG_EXT}"))

    for src_img in src_dir.rglob("*.png"):
        rel = src_img.relative_to(src_dir)
        dst_png = dst_dir / rel
        src_pngs.add(rel)

        # 非首次且像素未变 → 跳过; 但若目标格式缺失(上次中断)则补生成
        if not first_run and dst_png.exists() and not _pixels_differ(src_img, dst_png):
            skipped += 1
            opt = dst_png.with_suffix(IMG_EXT)
            if not opt.exists():
                _optimize_one(dst_png)
                if opt.exists():
                    optimized += 1
                    skipped -= 1
            continue

        # 像素变化或首次部署 → 复制并生成目标格式
        dst_png.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_img, dst_png)
        copied += 1
        _optimize_one(dst_png)
        optimized += 1

    # 删除源中已无的文件 (png 及其对应产物), 以及旧格式残留
    for f in dst_dir.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(dst_dir)
        if rel.suffix == ".png" and rel not in src_pngs:
            f.unlink()
            for ext in IMG_FORMATS:
                stale = f.with_suffix(ext)
                if stale.exists():
                    stale.unlink()
            removed += 1
        elif rel.suffix in LEGACY_EXTS:
            f.unlink()
            removed += 1
        elif rel.suffix == IMG_EXT and rel.with_suffix(".png") not in src_pngs:
            f.unlink()
            removed += 1

    print(f"  icons: {copied} copied, {optimized} optimized, {skipped} unchanged (skipped), {removed} removed")


def _all_icons_have_opt(site_dir, deploy_dir):
    """site 的每个图标 png 是否都有对应部署格式产物。"""
    site_icons = site_dir / "icons"
    deploy_icons = deploy_dir / "icons"
    if not site_icons.is_dir():
        return False
    pngs = list(site_icons.rglob("*.png"))
    if not pngs:
        return False
    return all(
        (deploy_icons / p.relative_to(site_icons).with_suffix(IMG_EXT)).exists()
        for p in pngs
    )


def update_references(deploy_dir):
    """把引用统一到 IMG_EXT:
    - app.js: 改 ICON_EXT 常量 (全部图标就位才切换), 动态模板统一走常量
    - html/css/json: 字面 icons/*.png|旧格式 → IMG_EXT (按产物存在性判断)
    产物缺失时回退 .png, 让 check_site 报缺口而不是留下 404 的旧格式引用。
    """
    count = 0
    opt_icon = f'ICON_EXT = "{IMG_EXT}"'

    app_js = deploy_dir / "app.js"
    if app_js.exists():
        text = app_js.read_text(encoding="utf-8")
        m = re.search(r'ICON_EXT = "(\.\w+)"', text)
        if m and m.group(0) != opt_icon:
            if _all_icons_have_opt(SITE, deploy_dir):
                app_js.write_text(
                    text.replace(m.group(0), opt_icon), encoding="utf-8")
                count += 1
            else:
                print(f"  warning: 部分图标缺 {IMG_EXT}, ICON_EXT 保持 {m.group(1)}")

    known = "|".join([e.lstrip(".") for e in IMG_FORMATS] + ["png"])
    icon_ref = re.compile(rf"(icons/[^\"'`\s]+)\.({known})")

    def _repl(m):
        base = m.group(1)
        if (deploy_dir / (base + IMG_EXT)).exists():
            return base + IMG_EXT
        if m.group(2) == "png":
            return m.group(0)
        return base + ".png"

    for pat in ("*.html", "*.css", "*.json"):
        for f in deploy_dir.rglob(pat):
            text = f.read_text(encoding="utf-8")
            new = icon_ref.sub(_repl, text)
            if new != text:
                f.write_text(new, encoding="utf-8")
                count += 1
    print(f"  references: {count} files updated (→ {IMG_EXT})")


def main():
    print("=" * 50)
    print("Deploy: site → site_deploy")
    print("=" * 50)

    # 1. 同步非图标文件
    print("\nsyncing site...")
    _sync_site(SITE, DEPLOY)

    # 2. 增量同步 + 裁剪压缩图标
    print("\nsyncing & optimizing icons...")
    sync_and_optimize(SITE / "icons", DEPLOY / "icons")

    # 3. 更新引用
    print("\nupdating references...")
    update_references(DEPLOY)

    # 4. 完整性校验 (IMG_EXT 引用/文件一致性, 缺口则非零退出)
    print("\nchecking...")
    import check_site
    check_site.report("deploy", check_site.collect_deploy_errors())

    print("\n[DONE]")


if __name__ == "__main__":
    main()
