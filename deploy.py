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
    """将单张 PNG 裁剪为 avif (始终保留, 页面只引用 avif)。"""
    img = Image.open(src_png)
    ratio = ICON_HEIGHT / img.height
    new_w = max(1, int(img.width * ratio))
    img = img.resize((new_w, ICON_HEIGHT), Image.LANCZOS)
    img.save(src_png.with_suffix(".avif"), "AVIF", quality=75)


def _sync_site(src, dst):
    """同步 site → site_deploy 中非图标文件 (按修改时间判断)。"""
    src_files = set()
    copied = removed = 0
    for root, _, files in src.walk():
        rel_dir = Path(root).relative_to(src)
        if rel_dir.parts and rel_dir.parts[0] == "icons":
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

        # 非首次且像素未变 → 跳过; 但若 avif 缺失(上次中断)则补生成
        if not first_run and dst_png.exists() and not _pixels_differ(src_img, dst_png):
            skipped += 1
            avif = dst_png.with_suffix(".avif")
            if not avif.exists():
                _optimize_one(dst_png)
                if avif.exists():
                    optimized += 1
                    skipped -= 1
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
    """把 HTML/JS/CSS/JSON 中图标 .png 引用改为 .avif（仅当对应 avif 存在）。"""
    count = 0
    prefix_ok = {}

    def _prefix_all_avif(prefix):
        """动态模板路径 (含 ${}) 的静态前缀下是否全部 png 都有 avif。"""
        if prefix not in prefix_ok:
            pdir = deploy_dir / prefix
            pngs = list(pdir.rglob("*.png")) if pdir.is_dir() else []
            prefix_ok[prefix] = bool(pngs) and all(p.with_suffix(".avif").exists() for p in pngs)
            if not prefix_ok[prefix]:
                print(f"  warning: missing avif under {prefix}, keeping .png refs")
        return prefix_ok[prefix]

    def _repl(m):
        path = m.group(1)
        if "${" in path:
            # 动态模板 (如 icons/${dir}/${id}.png): 前缀下全部有 avif 才改写
            if _prefix_all_avif(path.split("${", 1)[0]):
                return path + ".avif"
            return m.group(0)
        if (deploy_dir / (path + ".avif")).exists():
            return path + ".avif"
        return m.group(0)

    for f in list(deploy_dir.rglob("*.html")) + list(deploy_dir.rglob("*.js")) + list(deploy_dir.rglob("*.css")) + list(deploy_dir.rglob("*.json")):
        text = f.read_text(encoding="utf-8")
        new = re.sub(r"(icons/[^\"'`\s]+)\.png", _repl, text)
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
