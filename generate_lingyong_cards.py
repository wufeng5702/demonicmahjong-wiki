#!/usr/bin/env python3
"""
灵佣卡片详情图生成器
====================
从游戏资源和 data.json 中提取灵佣数据，生成类似游戏内的灵佣详情界面卡片图片。
输出到 lingyong_card_info/ 目录。

使用方法:
    python generate_lingyong_cards.py              # 生成全部灵佣卡片
    python generate_lingyong_cards.py --id 1 2 3   # 只生成指定ID的卡片
    python generate_lingyong_cards.py --test        # 测试模式，只生成前5张
"""

import json
import os
import re
import sys
import io
import argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 加载 .env
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from PIL import Image, ImageDraw, ImageFont

# ============================================================
# 路径配置
# ============================================================
BASE_DIR = Path(__file__).parent
DATA_JSON = BASE_DIR / "web_src" / "data.json"
ICONS_DIR = BASE_DIR / "output" / "site" / "icons" / "lingyong"
ASSETS_DIR = BASE_DIR / "assets" / "lingyong_card"
OUTPUT_DIR = BASE_DIR / "output" / "lingyong_card_info"

# 背景素材
BG_BASE = ASSETS_DIR / "SelectPopBgB.png"          # 深蓝色底图+金色边框 (619x964)
BG_NAME = ASSETS_DIR / "CardBgPop.png"             # 名称横幅衬底
# 稀有度色层 (覆盖上半部分)
BG_RARITY = {
    "普通": ASSETS_DIR / "SelectPopBgB01.png",     # 绿色
    "稀有": ASSETS_DIR / "SelectPopBgB02.png",     # 蓝色
    "史诗": ASSETS_DIR / "SelectPopBgB03.png",     # 紫色
    "传说": ASSETS_DIR / "SelectPopBgB04.png",     # 金色
}


# 卡片尺寸 (使用底图原始尺寸)
CARD_W = 638
CARD_H = 1020

# 中文字体路径（优先使用 .env 配置）
_FONT_ENV = os.environ.get("FONT_PATHS", "")
FONT_PATHS = [p.strip() for p in _FONT_ENV.split(";") if p.strip()] if _FONT_ENV else [
    r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",     # 黑体
    r"C:\Windows\Fonts\simsun.ttc",     # 宋体
    r"C:\Windows\Fonts\simkai.ttf",     # 楷体
]


def find_font():
    """查找可用的中文字体"""
    for fp in FONT_PATHS:
        p = Path(fp)
        if p.exists():
            return str(p)
    return None


def load_data():
    """从 data.json 读取灵佣数据"""
    data = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    return data["data"]["lingyong"]


def load_image(path, size=None):
    """加载图片，可选缩放"""
    img = Image.open(path).convert("RGBA")
    if size:
        img = img.resize(size, Image.LANCZOS)
    return img


def crop_center(img, target_w, target_h):
    """居中裁剪图片"""
    w, h = img.size
    left = (w - target_w) // 2
    top = (h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def paste_center(base, overlay, y_offset=0):
    """将 overlay 居中粘贴到 base 上，可选 y 偏移"""
    bw, bh = base.size
    ow, oh = overlay.size
    x = (bw - ow) // 2
    y = (bh - oh) // 2 + y_offset
    base.paste(overlay, (x, y), overlay)


def wrap_text(text, font, max_width, draw):
    """自动换行，返回行列表"""
    lines = []
    current_line = ""
    for char in text:
        test_line = current_line + char
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] > max_width:
            if current_line:
                lines.append(current_line)
            current_line = char
        else:
            current_line = test_line
    if current_line:
        lines.append(current_line)
    return lines


def draw_text_with_highlight(draw, text, x, y, font, fill="#FFFFFF", highlight_fill="#FF6B35", max_width=438):
    """
    绘制文本，按 \n 换行，超出 max_width 时自动折行，并高亮数字。
    返回文本总高度。
    """
    import re as _re
    pattern = _re.compile(r'([+-]?\d+(?:\.\d+)?%?)')

    # 先按 \n 拆分成段落
    paragraphs = text.split("\n")

    line_segments = []  # [ [(char, is_hl), ...], ...]

    for para in paragraphs:
        if not para:
            # 空行也保留一行高度
            line_segments.append([])
            continue

        # 分段
        segments = []
        last_end = 0
        for m in pattern.finditer(para):
            if m.start() > last_end:
                segments.append(("normal", para[last_end:m.start()]))
            segments.append(("highlight", m.group()))
            last_end = m.end()
        if last_end < len(para):
            segments.append(("normal", para[last_end:]))

        # 逐字符换行
        temp_line = ""
        temp_segs = []
        for seg_type, seg_text in segments:
            for char in seg_text:
                test_line = temp_line + char
                bbox = draw.textbbox((0, 0), test_line, font=font)
                if bbox[2] - bbox[0] > max_width and temp_line:
                    line_segments.append(temp_segs[:])
                    temp_line = char
                    temp_segs = [(char, seg_type == "highlight")]
                else:
                    temp_line = test_line
                    temp_segs.append((char, seg_type == "highlight"))
        if temp_segs:
            line_segments.append(temp_segs)

    # 绘制
    total_height = 0
    line_height = font.size + 8
    for segs in line_segments:
        x_offset = 0
        for char, is_hl in segs:
            color = highlight_fill if is_hl else fill
            draw.text((x + x_offset, y + total_height), char, font=font, fill=color)
            bbox = draw.textbbox((0, 0), char, font=font)
            x_offset += bbox[2] - bbox[0]
        total_height += line_height

    return total_height


def draw_rounded_rect(draw, bbox, radius, fill=None, outline=None, width=1):
    """绘制圆角矩形"""
    x1, y1, x2, y2 = bbox
    if fill:
        draw.rounded_rectangle(bbox, radius=radius, fill=fill)
    if outline:
        draw.rounded_rectangle(bbox, radius=radius, outline=outline, width=width)





def generate_card(entry, font_name, font_desc, bg_base, rarity_bgs, bg_name):
    """生成单张灵佣卡片"""
    card = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))

    # 1. 底图 - 深蓝色波浪纹背景+金色边框
    bg = bg_base.copy()
    bg = bg.resize((CARD_W, CARD_H), Image.LANCZOS)
    card.paste(bg, (0, 0), bg)

    # 2. 稀有度色层 - 原始尺寸居中对齐，向下偏移60像素
    rar = entry.get("rar", "普通")
    rarity_bg = rarity_bgs.get(rar, rarity_bgs.get("普通"))
    if rarity_bg:
        rarity_overlay = rarity_bg.copy()
        # 居中对齐，向下偏移60像素（使用原始尺寸，不拉伸）
        paste_x = (CARD_W - rarity_overlay.width) // 2
        paste_y = 60
        card.paste(rarity_overlay, (paste_x, paste_y), rarity_overlay)

    draw = ImageDraw.Draw(card)

    # 3. 灵佣图标
    icon_path = ICONS_DIR / f"{entry['id']}.png"
    if icon_path.exists():
        icon = load_image(icon_path)
        icon_max = 280
        icon_scale = min(icon_max / icon.width, icon_max / icon.height)
        icon = icon.resize((int(icon.width * icon_scale), int(icon.height * icon_scale)), Image.LANCZOS)
        paste_center(card, icon, y_offset=-180)

    # 4. 名称横幅
    name = entry.get("name", "")
    name_bar_y = int(CARD_H * 0.52)

    # 使用名称横幅素材
    if bg_name:
        name_bar = bg_name.copy()
        # 按卡片宽度缩放到 70%，保持比例
        scale = CARD_W / name_bar.width * 0.7
        name_bar = name_bar.resize((int(name_bar.width * scale), int(name_bar.height * scale)), Image.LANCZOS)
        paste_x = (CARD_W - name_bar.width) // 2
        card.paste(name_bar, (paste_x, name_bar_y), name_bar)
        name_bar_h = name_bar.height
    else:
        # 后备：程序绘制
        name_bar_h = 64
        name_bar_w = CARD_W - 100
        name_bar_x = (CARD_W - name_bar_w) // 2
        name_bg = Image.new("RGBA", (name_bar_w, name_bar_h), (25, 25, 45, 220))
        card.paste(name_bg, (name_bar_x, name_bar_y), name_bg)
        draw.rounded_rectangle(
            [name_bar_x, name_bar_y, name_bar_x + name_bar_w, name_bar_y + name_bar_h],
            radius=6, outline=(180, 165, 120, 255), width=2
        )

    # 绘制名称文字
    name_bbox = draw.textbbox((0, 0), name, font=font_name)
    name_w = name_bbox[2] - name_bbox[0]
    name_h = name_bbox[3] - name_bbox[1]
    name_x = (CARD_W - name_w) // 2
    name_y = name_bar_y + (name_bar_h - name_h) // 2
    draw.text((name_x, name_y), name, font=font_name, fill="#FFFFFF")

    # 5. 描述区域 - 从底部上方300像素开始，无暗色背景，两端对齐
    desc = entry.get("desc", "")
    desc_area_y = CARD_H - 300
    desc_x = 100  # 左边距100像素
    max_text_w = CARD_W - 200  # 左右各100像素边距

    # 绘制描述文字（带高亮）
    draw_text_with_highlight(draw, desc, desc_x, desc_area_y, font_desc,
                             fill="#E0E0E0", max_width=max_text_w)

    return card.convert("RGB")


def main():
    parser = argparse.ArgumentParser(description="灵佣卡片详情图生成器")
    parser.add_argument("--id", nargs="+", type=int, help="只生成指定ID的卡片")
    parser.add_argument("--test", action="store_true", help="测试模式，只生成前5张")
    args = parser.parse_args()

    # 查找字体
    font_path = find_font()
    if not font_path:
        print("错误: 未找到中文字体")
        sys.exit(1)
    print(f"使用字体: {font_path}")

    # 加载字体
    font_name = ImageFont.truetype(font_path, 42)
    font_desc = ImageFont.truetype(font_path, 32)

    # 加载灵佣数据
    entries = load_data()
    print(f"加载灵佣数据: {len(entries)} 条")

    # 过滤
    if args.id:
        entries = [e for e in entries if e["id"] in args.id]
        print(f"筛选指定ID: {len(entries)} 条")
    elif args.test:
        entries = entries[:5]
        print(f"测试模式: 前 {len(entries)} 条")

    # 加载背景素材
    print("加载背景素材...")
    bg_base = load_image(BG_BASE)
    bg_name = load_image(BG_NAME) if BG_NAME.exists() else None
    if bg_name:
        print(f"  名称横幅: {BG_NAME.name}")
    rarity_bgs = {}
    for rar_name, rar_path in BG_RARITY.items():
        if rar_path.exists():
            rarity_bgs[rar_name] = load_image(rar_path)
            print(f"  稀有度色层 [{rar_name}]: {rar_path.name}")

    # 创建输出目录
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 生成卡片
    success = 0
    skip = 0
    fail = 0
    for i, entry in enumerate(entries):
        xid = entry["id"]
        name = entry.get("name", f"ID{xid}")
        out_path = OUTPUT_DIR / f"{xid}_{name}.png"

        # 检查图标是否存在
        icon_path = ICONS_DIR / f"{xid}.png"
        if not icon_path.exists():
            print(f"  [{i+1}/{len(entries)}] 跳过 {name} (ID={xid}): 图标不存在")
            skip += 1
            continue

        try:
            card = generate_card(entry, font_name, font_desc, bg_base, rarity_bgs, bg_name)
            card.save(str(out_path), "PNG")
            success += 1
            if success % 50 == 0 or success <= 3:
                print(f"  [{i+1}/{len(entries)}] 已生成 {name} (ID={xid})")
        except Exception as e:
            fail += 1
            print(f"  [{i+1}/{len(entries)}] 失败 {name} (ID={xid}): {e}")

    print(f"\n完成! 成功={success}, 跳过={skip}, 失败={fail}")
    print(f"输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
