"""
X(Twitter)用の予告ツイートを自動生成

毎日のnote記事投稿後に呼び出し、output/x_teaser.txt に保存。
ユーザーは中身をX投稿アプリにコピペして手動投稿する（API設定不要）。

X流入はnoteメンバーシップの主要な獲得経路。記事タイトルだけより、
「示唆＋数字＋note URL」のフォーマットで貼ると平均クリック率が高い。

使い方:
  python generate_x_teaser.py              # 最新投稿のteaserを生成
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_latest_post() -> dict:
    """最新投稿のメタ情報をロード"""
    try:
        with open(OUTPUT_DIR / "posted.json", encoding="utf-8") as f:
            posted = json.load(f)
    except Exception:
        posted = {}
    try:
        with open(OUTPUT_DIR / "final.json", encoding="utf-8") as f:
            final = json.load(f)
    except Exception:
        final = {}
    return {
        "url": posted.get("url", ""),
        "title": final.get("title", ""),
        "body": final.get("body", "") or final.get("polished", ""),
    }


def extract_hook_lines(body: str) -> list[str]:
    """記事本文から訴求になる行を抽出（数字・銘柄名を含む短い文）"""
    out = []
    for line in body.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("__"):
            continue
        if len(line) < 20 or len(line) > 90:
            continue
        # 数字・%・円が含まれる行を優先
        has_number = any(ch.isdigit() for ch in line)
        if has_number:
            out.append(line)
        if len(out) >= 3:
            break
    return out


def build_teaser(post: dict) -> str:
    """X用の予告ツイートを生成（280字以内）"""
    title = post.get("title", "（タイトル不明）")
    url = post.get("url", "")
    hooks = extract_hook_lines(post.get("body", ""))

    # 1) タイトル＋示唆1行＋URL のシンプル版
    teaser_short = f"""{title}

▼今朝のnote
{url}"""

    # 2) 示唆フック付き
    if hooks:
        hook = hooks[0]
        teaser_long = f"""{title}

{hook}

詳しくは↓
{url}

毎朝7時のnoteメンバーシップで、買い水準・損切り・利確目安まで具体的な数字付きで配信しています。初月無料。"""
    else:
        teaser_long = teaser_short

    return teaser_long


def main():
    post = load_latest_post()
    if not post.get("url"):
        print("[WARN] 最新投稿のURLが見つかりません（output/posted.json を確認）")
        return

    teaser = build_teaser(post)

    out_path = OUTPUT_DIR / "x_teaser.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(teaser)

    print("=== X(Twitter)予告ツイート ===")
    print()
    print(teaser)
    print()
    print(f"({len(teaser)}文字 / 280字制限)")
    print(f"保存: {out_path}")
    print()
    print("【使い方】 上記をXに貼り付けてツイートしてください。LINE Botから")
    print("『今日のXツイート見せて』と聞いても確認できます。")


if __name__ == "__main__":
    main()
