"""部署脚本: 裁剪压缩图标 → output/site_deploy/"""
import re
import shutil
from pathlib import Path
from PIL import Image

SITE = Path(__file__).parent / "output" / "site"
DEPLOY = Path(__file__).parent / "output" / "site_deploy"
ICON_HEIGHT = 128  # 裁剪目标高度 (网页显示64px, 2x适配)


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
    """将单张 PNG 裁剪为 avif, avif 更大则保留原图。"""
    img = Image.open(src_png)
    ratio = ICON_HEIGHT / img.height
    new_w = max(1, int(img.width * ratio))
    img = img.resize((new_w, ICON_HEIGHT), Image.LANCZOS)
    avif_path = src_png.with_suffix(".avif")
    img.save(avif_path, "AVIF", quality=75)
    if avif_path.stat().st_size >= src_png.stat().st_size:
        avif_path.unlink()


def _sync_site(src, dst):
    """同步 site → site_deploy 中非图标文件 (按修改时间判断)。"""
    src_files = set()
    copied = removed = 0
    for root, _, files in src.walk():
        rel_dir = Path(root).relative_to(src)
        if rel_dir == Path("icons") or str(rel_dir).startswith("icons" + "/"):
            continue
        for f in files:
            s = Path(root) / f
            rel = s.relative_to(src)
            d = dst / rel
            src_files.add(rel)
            if not d.exists() or s.stat().st_mtime != d.stat().st_mtime:
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, d)
                copied += 1
    for f in dst.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(dst)
        if rel.parts[0] == "icons":
            continue
        if rel not in src_files:
            f.unlink()
            removed += 1
    if copied or removed:
        print(f"  site: {copied} copied, {removed} removed")


def sync_and_optimize(src_dir, dst_dir):
    """增量同步 + 优化: 像素变化才复制并生成 avif, 未变化则跳过。"""
    src_pngs = set()
    copied = removed = optimized = skipped = 0
    first_run = not any(dst_dir.rglob("*.avif"))

    for src_img in src_dir.rglob("*.png"):
        rel = src_img.relative_to(src_dir)
        dst_png = dst_dir / rel
        src_pngs.add(rel)

        # 非首次且像素未变 → 跳过
        if not first_run and dst_png.exists() and not _pixels_differ(src_img, dst_png):
            skipped += 1
            continue

        # 像素变化或首次部署 → 复制并生成 avif
        dst_png.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_img, dst_png)
        copied += 1
        _optimize_one(dst_png)
        optimized += 1

    # 删除源中已无的文件 (png 及其对应的 avif)
    for f in dst_dir.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(dst_dir)
        if rel.suffix == ".png" and rel not in src_pngs:
            f.unlink()
            avif = f.with_suffix(".avif")
            if avif.exists():
                avif.unlink()
            removed += 1
        elif rel.suffix == ".avif" and rel.with_suffix(".png") not in src_pngs:
            f.unlink()
            removed += 1

    print(f"  icons: {copied} copied, {optimized} optimized, {skipped} unchanged (skipped), {removed} removed")


def update_references(deploy_dir):
    """把 HTML/JS/CSS/JSON 中图标 .png 引用改为 .avif。"""
    count = 0
    for f in list(deploy_dir.rglob("*.html")) + list(deploy_dir.rglob("*.js")) + list(deploy_dir.rglob("*.css")) + list(deploy_dir.rglob("*.json")):
        text = f.read_text(encoding="utf-8")
        new = re.sub(r'(icons/[^"\'`\s]+)\.png', r'\1.avif', text)
        if new != text:
            f.write_text(new, encoding="utf-8")
            count += 1
    print(f"  references: {count} files updated (.png → .avif)")


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

    print("\n[DONE]")


if __name__ == "__main__":
    main()
