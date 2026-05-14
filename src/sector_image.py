"""
セクター動向画像生成（Pillow、1920×420px）

強いセクター／弱いセクターを視覚的に対比表示する横長バナー画像。
OS別に日本語フォントを自動選択。
"""
from __future__ import annotations

import os
import platform
import re

from PIL import Image, ImageDraw, ImageFont


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """OS別の日本語フォント取得（Windows=Yu Gothic, macOS=ヒラギノ）"""
    system = platform.system()
    if system == "Windows":
        candidates = [
            r"C:\Windows\Fonts\YuGothB.ttc" if bold else r"C:\Windows\Fonts\YuGothM.ttc",
            r"C:\Windows\Fonts\meiryob.ttc" if bold else r"C:\Windows\Fonts\meiryo.ttc",
            r"C:\Windows\Fonts\msgothic.ttc",
        ]
    elif system == "Darwin":
        candidates = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc" if bold
            else "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
        ]
    else:
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold
            else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_sector_image(strong_list: list[str], weak_list: list[str],
                          output_path: str, date_label: str = "") -> str | None:
    """
    Args:
        strong_list: 強いセクター名のリスト（最大6個表示）
        weak_list:   弱いセクター名のリスト（最大6個表示）
        output_path: 出力PNGパス
        date_label:  右下に表示する日付ラベル（例: "4月10日 デイトレード"）
    """
    if not strong_list and not weak_list:
        return None

    W, H = 1920, 420
    BG       = (15, 18, 35)
    UP_COL   = (38, 166, 154)
    DOWN_COL = (239, 83, 80)
    TEXT_COL = (220, 220, 220)
    DIM_COL  = (100, 105, 130)

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # 背景グラデーション
    for y in range(H):
        factor = 1.0 + (y / H) * 0.15
        r = min(255, int(BG[0] * factor))
        g = min(255, int(BG[1] * factor))
        b = min(255, int(BG[2] * factor))
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    mid = W // 2
    draw.line([(mid, 20), (mid, H - 20)], fill=(50, 55, 80), width=2)

    font_item  = _get_font(38)
    label_font = _get_font(44, bold=True)
    arrow_font = _get_font(56, bold=True)

    def draw_side(x_start: int, x_end: int, label: str, items: list[str],
                  header_col: tuple, arrow: str):
        cx = (x_start + x_end) // 2
        draw.rectangle([(x_start + 30, 20), (x_end - 30, 100)], fill=header_col)
        draw.text((cx - 160, 28), arrow, font=arrow_font, fill=(255, 255, 255))
        draw.text((cx - 80,  32), label, font=label_font, fill=(255, 255, 255))
        y_cur = 120
        for item in items[:6]:
            draw.ellipse([(x_start + 60, y_cur + 14), (x_start + 84, y_cur + 38)],
                         fill=header_col)
            draw.text((x_start + 98, y_cur), item, font=font_item, fill=TEXT_COL)
            bbox = draw.textbbox((0, 0), item, font=font_item)
            y_cur += (bbox[3] - bbox[1]) + 16

    draw_side(0, mid, "強いセクター", strong_list, UP_COL, "↑")
    draw_side(mid, W,  "弱いセクター", weak_list,   DOWN_COL, "↓")

    if date_label:
        wm_font = _get_font(28)
        draw.text((W - 360, H - 48), date_label, font=wm_font, fill=DIM_COL)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path)
    print(f"  セクター画像生成: {output_path}")
    return os.path.abspath(output_path)


def generate_sector_image_from_body(body: str, output_path: str,
                                    date_label: str = "") -> str | None:
    """記事本文から強い/弱いセクター行を自動抽出して画像生成"""
    strong_m = re.search(r'強いセクター[：:]\s*(.+)', body)
    weak_m   = re.search(r'弱いセクター[：:]\s*(.+)', body)
    if not strong_m or not weak_m:
        return None
    split_re = r'[・、,，/／\s]+'
    strong_list = [s for s in re.split(split_re, strong_m.group(1)) if s]
    weak_list   = [s for s in re.split(split_re, weak_m.group(1))   if s]
    return generate_sector_image(strong_list, weak_list, output_path, date_label)


if __name__ == "__main__":
    import datetime
    out = os.path.join(os.path.dirname(__file__), "..", "output", "sector_test.png")
    today = datetime.date.today()
    generate_sector_image(
        strong_list=["半導体", "電線", "資源エネルギー", "銀行"],
        weak_list=["小売", "ゲーム", "内需ディフェンシブ"],
        output_path=out,
        date_label=f"{today.month}月{today.day}日 デイトレード",
    )
