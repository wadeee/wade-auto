# -*- coding: utf-8 -*-
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

INPUT_DIR = Path(__file__).parent / "input"
OUTPUT_DIR = Path(__file__).parent / "output"

FONT_PATH = str(Path(__file__).parent / "fonts" / "PingFang.ttc")
TEXT_COLOR = (40, 40, 40)

# (文本, 左边距x, 行顶部y, 行高) —— 基于 1206x2622 的图片测得的固定位置
LINES = [
    ("2026年8月21日 19:16:31", 360, 1405, 37),
    ("4500000292202607306641838414", 360, 1828, 31),
    ("2026073017150345719", 360, 1912, 31),
]


def fit_font(text: str, target_height: int):
    size = target_height
    for _ in range(10):
        font = ImageFont.truetype(FONT_PATH, size)
        h = font.getbbox(text)[3] - font.getbbox(text)[1]
        if abs(h - target_height) <= 1:
            break
        size = max(1, round(size * target_height / h))
    return ImageFont.truetype(FONT_PATH, size)


def process(path: Path, out_path: Path):
    img = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(img)

    for text, x, y, h in LINES:
        # 擦除该行原文本(从左边距到图片右侧)
        draw.rectangle([x - 4, y - 6, img.width - 20, y + h + 6], fill=(255, 255, 255))
        # 绘制新文本,保持原左边距和字高
        font = fit_font(text, h)
        tb = font.getbbox(text)
        draw.text((x - tb[0], y - tb[1]), text, font=font, fill=TEXT_COLOR)

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
