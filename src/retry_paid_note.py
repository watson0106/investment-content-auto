"""
有料note生成リトライスクリプト
06:00 cronで実行。当日の無料記事に有料noteリンクがなければ
stock-analysis-auto を実行して有料noteを作成し、無料note下書きを更新する。
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import traceback

JST = datetime.timezone(datetime.timedelta(hours=9))
ARTICLE_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "article_1.json")
SA_MAIN = os.path.expanduser("~/stock-analysis-auto/src/main.py")


def already_has_paid_link(article_path: str) -> bool:
    """article_1.json に有料noteリンクが挿入済みか確認"""
    try:
        with open(article_path, encoding="utf-8") as f:
            data = json.load(f)
        article = data.get("article", "")
        # 有料リンクは article_linker.py が "詳しい分析はこちらの記事で" の後に挿入する
        return bool(re.search(r'note\.com/kawasewatson0106/n/\w+', article))
    except Exception:
        return False


def article_is_today(article_path: str) -> bool:
    """article_1.json が今日生成されたものか（更新日時で判定）"""
    try:
        mtime = os.path.getmtime(article_path)
        mtime_jst = datetime.datetime.fromtimestamp(mtime, tz=JST)
        today = datetime.datetime.now(JST).date()
        return mtime_jst.date() == today
    except Exception:
        return False


def run_stock_analysis() -> bool:
    """stock-analysis-auto を実行して有料noteを作成する"""
    article_abs = os.path.abspath(ARTICLE_PATH)
    env = {k: v for k, v in os.environ.items()
           if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "/usr/bin:/bin")
    try:
        result = subprocess.run(
            [sys.executable, SA_MAIN, "--article", article_abs],
            env=env,
            cwd=os.path.expanduser("~/stock-analysis-auto/src"),
            timeout=1800,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("  [WARN] stock-analysis-auto タイムアウト（30分）")
        return False
    except Exception:
        traceback.print_exc()
        return False


def repost_free_note() -> bool:
    """無料noteを有料リンク入りで再投稿"""
    src_dir = os.path.dirname(__file__)
    env = {k: v for k, v in os.environ.items()
           if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "/usr/bin:/bin")
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(src_dir, "main.py"), "--mode", "post1", "--force"],
            env=env,
            cwd=os.path.join(src_dir, ".."),
            timeout=600,
        )
        return result.returncode == 0
    except Exception:
        traceback.print_exc()
        return False


def main():
    now = datetime.datetime.now(JST)
    print(f"=== 有料noteリトライ === {now.strftime('%Y-%m-%d %H:%M')} JST")

    if not os.path.exists(ARTICLE_PATH):
        print("  article_1.json が存在しません → スキップ")
        return

    if not article_is_today(ARTICLE_PATH):
        print("  article_1.json が今日のものではありません → スキップ")
        return

    with open(ARTICLE_PATH, encoding="utf-8") as f:
        data = json.load(f)

    if data.get("skip_stock"):
        print("  skip_stock=True → 有料note不要 → スキップ")
        return

    if already_has_paid_link(ARTICLE_PATH):
        print("  有料noteリンクは挿入済みです → スキップ")
        return

    print("  有料noteリンクなし → stock-analysis-auto を実行します")

    ok = run_stock_analysis()
    if not ok:
        print("  ❌ stock-analysis-auto 失敗")
        return

    # リンクが挿入されたか確認
    if not already_has_paid_link(ARTICLE_PATH):
        print("  ⚠️  有料note作成は成功したが、リンク挿入が確認できませんでした")
        return

    print("  有料noteリンク挿入確認 → 無料noteを再投稿します")
    ok2 = repost_free_note()
    if ok2:
        print("  ✅ 無料note再投稿完了")
    else:
        print("  ⚠️  無料note再投稿失敗（手動で --mode post1 を実行してください）")


if __name__ == "__main__":
    main()
