"""
パイプライン エントリポイント

スケジュール:
  05:00  --mode generate  : ニュース収集 → 記事2本執筆 → 即座にnote下書き保存

引数なし（手動実行）: 同上（全ステップ一括）
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import traceback

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

sys.path.insert(0, os.path.dirname(__file__))

import collect_news
import deep_research
import post_to_note
import pdca_tracker
import daily_report
import anomaly_detector

JST = datetime.timezone(datetime.timedelta(hours=9))


def notify(title: str, message: str):
    """Mac通知"""
    os.system(f'osascript -e \'display notification "{message}" with title "{title}"\'')


def log_result(mode: str, url: str, title: str):
    """output/pipeline.log に記録"""
    os.makedirs("output", exist_ok=True)
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{now} [{mode}] {title} | {url}\n"
    with open("output/pipeline.log", "a", encoding="utf-8") as f:
        f.write(line)


# ─────────────────────────────────────────────────────────────────
# MODE: generate
# 05:00 に実行。ニュース収集 → 記事2本執筆 → ファイル保存
# ─────────────────────────────────────────────────────────────────

def mode_generate():
    print("=" * 50)
    print("投資記事生成パイプライン 開始（generate）")
    today = datetime.datetime.now(JST)
    print(f"  日時: {today.strftime('%Y-%m-%d %H:%M')} JST")
    print("=" * 50)

    os.makedirs("output", exist_ok=True)

    # ① ニュース収集
    print(f"\n{'─'*40}")
    print("  ① ニュース収集")
    print(f"{'─'*40}")
    try:
        collect_news.main()
    except Exception:
        print("❌ ニュース収集失敗（重要ステップ）")
        traceback.print_exc()
        sys.exit(1)

    # ② 記事2本執筆
    print(f"\n{'─'*40}")
    print("  ② 記事執筆（2本）")
    print(f"{'─'*40}")
    try:
        result = deep_research.main()
        a1 = result["article_1"]
        a2 = result["article_2"]
        print(f"  記事1: {a1['title']}")
        print(f"  記事2: {a2['title']}")
    except Exception:
        print("❌ 記事執筆失敗（重要ステップ）")
        traceback.print_exc()
        sys.exit(1)

    # ③ 記事1 即座に下書き保存
    print(f"\n{'─'*40}")
    print("  ③ 記事1 note下書き保存")
    print(f"{'─'*40}")
    try:
        r1 = mode_post(1)
    except SystemExit:
        r1 = {"url": ""}

    # ④ 記事2 即座に下書き保存
    print(f"\n{'─'*40}")
    print("  ④ 記事2 note下書き保存")
    print(f"{'─'*40}")
    try:
        r2 = mode_post(2)
    except SystemExit:
        r2 = {"url": ""}

    print("\n" + "=" * 50)
    print("✅ 生成・保存完了")
    print(f"  記事1: {r1.get('url', 'output/article_1.json')}")
    print(f"  記事2: {r2.get('url', 'output/article_2.json')}")
    print("=" * 50)

    notify("【下書き保存完了】", f"記事1: {a1['title']} / 記事2: {a2['title']}")
    return r1, r2


# ─────────────────────────────────────────────────────────────────
# MODE: post1 / post2
# ─────────────────────────────────────────────────────────────────

def mode_post(article_num: int):
    article_file = f"output/article_{article_num}.json"
    print("=" * 50)
    print(f"note 下書き保存（post{article_num}）")
    print("=" * 50)

    if not os.path.exists(article_file):
        print(f"❌ {article_file} が見つかりません。先に generate を実行してください。")
        sys.exit(1)

    with open(article_file, encoding="utf-8") as f:
        data = json.load(f)

    title = data["title"]
    print(f"  タイトル: {title}")

    try:
        result = post_to_note.main(article_file=article_file)
        url = result.get("url", "")
    except Exception:
        print(f"❌ post{article_num} 失敗:")
        traceback.print_exc()
        notify(f"【投稿失敗】記事{article_num}", title)
        sys.exit(1)

    # PDCAトラッカー登録
    try:
        import re
        m = re.search(r"/n/([a-zA-Z0-9]+)$", url)
        if m:
            note_key = m.group(1)
            source_news = [data.get("source_news", {}).get("title", "")]
            pdca_tracker.record_posted_article(
                note_key=note_key,
                title=title,
                source_news=source_news,
                is_paid=False,
                price=0,
            )
    except Exception as e:
        print(f"  [WARN] PDCA登録失敗: {e}")

    log_result(f"post{article_num}", url, title)

    print(f"\n✅ 下書き保存完了: {url}")
    print("  公開は手動で行ってください")
    notify(f"【下書き保存完了】記事{article_num}", f"{title}\n{url}")

    return result


# ─────────────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────────────

def run_pipeline():
    """引数なし手動実行: generate → post1 → post2"""
    print("=" * 50)
    print("投資記事自動生成パイプライン 開始（全ステップ）")
    today = datetime.datetime.now(JST)
    print(f"  日時: {today.strftime('%Y-%m-%d %H:%M')} JST  曜日: {['月','火','水','木','金','土','日'][today.weekday()]}")
    print("=" * 50)

    result1, result2 = mode_generate()

    # スキ数更新
    try:
        pdca_tracker.main(mode="daily")
    except Exception:
        pass

    # 異常検知
    anomaly_result = {}
    try:
        anomaly_result = anomaly_detector.run_checks()
    except Exception:
        pass

    # 日次レポート
    try:
        daily_report.send_daily_report(
            posted_url=result1.get("url", ""),
            anomaly_result=anomaly_result,
        )
    except Exception:
        pass

    print("\n" + "=" * 50)
    print("✅ パイプライン完了")
    print(f"  記事1: {result1.get('url', '不明')}")
    print(f"  記事2: {result2.get('url', '不明')}")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["generate", "post1", "post2"], default=None)
    args = parser.parse_args()

    if args.mode == "generate":
        mode_generate()
    elif args.mode == "post1":
        mode_post(1)
    elif args.mode == "post2":
        mode_post(2)
    else:
        run_pipeline()
