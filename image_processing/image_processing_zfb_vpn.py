# -*- coding: utf-8 -*-
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

INPUT_DIR = Path(__file__).parent / "zfb-vpn" / "input"
OUTPUT_DIR = Path(__file__).parent / "zfb-vpn" / "output"

SF_FONT_PATH = str(Path(__file__).parent / "fonts" / "SFNS.ttf")      # 英文/数字
PF_FONT_PATH = str(Path(__file__).parent / "fonts" / "PingFang.ttc")  # 中文
FONT_WEIGHT = "Regular"  # 可选: Regular / Medium / Semibold
PF_INDEX = {"Regular": 3, "Medium": 7, "Semibold": 11}  # PingFang SC 各字重的 face 索引
TEXT_COLOR = (40, 40, 40)

# (文本, 左边距x, 行顶部y, 行高) —— 基于 1206x2622 的图片测得的固定位置
LINES = [
    ("2026-08-01 15:57:36", 379, 927, 32),           # 位置1: 时间戳（原位置1）
    ("2026080115570754043", 634, 1134, 30),          # 位置2: 新数据
    ("2026080122001433981427467326", 380, 1403, 30), # 位置3: 订单号（原位置2）
    ("2026080115570894950", 380, 1505, 30),          # 位置4: 交易号（原位置3，下移）
]


def is_cjk(ch: str) -> bool:
    return ord(ch) >= 0x2E80


def split_runs(text: str):
    """把文本按 中文/非中文 切分为若干段: [(片段, 是否中文), ...]"""
    runs = []
    for ch in text:
        cjk = is_cjk(ch)
        if runs and runs[-1][1] == cjk:
            runs[-1][0] += ch
        else:
            runs.append([ch, cjk])
    return [(s, c) for s, c in runs]


def load_fonts(size: int):
    sf = ImageFont.truetype(SF_FONT_PATH, size)
    sf.set_variation_by_name(FONT_WEIGHT)
    pf = ImageFont.truetype(PF_FONT_PATH, size, index=PF_INDEX[FONT_WEIGHT])
    return sf, pf


def line_metrics(runs, sf, pf):
    """返回整行相对基线的 (top, bottom)。top 为负值。"""
    top, bottom = 0, 0
    for run, cjk in runs:
        font = pf if cjk else sf
        ascent, _ = font.getmetrics()
        bbox = font.getbbox(run)
        top = min(top, bbox[1] - ascent)
        bottom = max(bottom, bbox[3] - ascent)
    return top, bottom


def fit_fonts(runs, target_height: int):
    """找到使整行渲染高度接近 target_height 的字号。"""
    size = target_height
    for _ in range(10):
        sf, pf = load_fonts(size)
        top, bottom = line_metrics(runs, sf, pf)
        h = bottom - top
        if abs(h - target_height) <= 1:
            break
        size = max(1, round(size * target_height / h))
    return load_fonts(size)


def draw_mixed_text(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, target_height: int):
    """中英文分别用 PingFang / SFNS 渲染,按基线对齐,整行顶部对齐到 y。"""
    runs = split_runs(text)
    sf, pf = fit_fonts(runs, target_height)
    top, _ = line_metrics(runs, sf, pf)
    baseline = y - top

    cursor = float(x)
    for i, (run, cjk) in enumerate(runs):
        font = pf if cjk else sf
        ascent, _ = font.getmetrics()
        if i == 0:
            cursor -= font.getbbox(run)[0]  # 首段左边缘精确对齐 x
        draw.text((cursor, baseline - ascent), run, font=font, fill=TEXT_COLOR)
        cursor += font.getlength(run)


def process(path: Path, out_path: Path):
    img = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(img)

    for text, x, y, h in LINES:
        draw.rectangle([x - 4, y - 6, img.width - 80, y + h + 6], fill=(255, 255, 255))
        draw_mixed_text(draw, text, x, y, h)

    img.save(out_path, quality=95)
    print(f"完成: {path.name} -> {out_path}")


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    images = sorted(
        p for p in INPUT_DIR.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    )
    if not images:
        print(f"未找到图片: {INPUT_DIR}")
        return
    for p in images:
        process(p, OUTPUT_DIR / p.name)


if __name__ == "__main__":
    main()
