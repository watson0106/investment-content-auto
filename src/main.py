"""
パイプライン全体を順番に実行するエントリポイント
"""

from __future__ import annotations


import sys
import os
import traceback
from dotenv import load_dotenv

# プロジェクトルートの .env を読み込む
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

sys.path.insert(0, os.path.dirname(__file__))

import collect_news
import deep_research
import fact_check
import generate_images
import generate_title
import post_to_note


def run_pipeline():
    print("=" * 50)
    print("投資記事自動生成パイプライン 開始")
    print("=" * 50)

    steps = [
        ("① ニュース収集",       collect_news.main),
        ("② Gemini 深掘り分析",  deep_research.main),
        ("③ Claude 添削",        fact_check.main),
        ("④ 画像生成",           generate_images.main),
        ("⑤ タイトル生成",       generate_title.main),
        ("⑥ note 投稿",          post_to_note.main),
    ]

    for name, func in steps:
        print(f"\n{'─'*40}")
        print(f"  {name}")
        print(f"{'─'*40}")
        try:
            func()
        except Exception as e:
            print(f"\n❌ {name} でエラー発生:")
            traceback.print_exc()
            sys.exit(1)

    print("\n" + "=" * 50)
    print("✅ パイプライン完了")
    print("=" * 50)

    try:
        import json
        with open("output/posted.json") as f:
            result = json.load(f)
        print(f"投稿URL: {result.get('url', '不明')}")
    except Exception:
        pass

    # 履歴に今回の記事を追加保存
    try:
        import json
        from article_history import add_article
        print("\n── 記事履歴を更新中...")
        with open("output/polished.json", encoding="utf-8") as f:
            polished = json.load(f)
        with open("output/collected_news.json", encoding="utf-8") as f:
            news = json.load(f)
        news_titles = [a.get("title", "") for a in news[:5]]
        add_article(polished.get("polished", ""), news_titles)
    except Exception as e:
        print(f"  [WARN] 履歴保存エラー: {e}")


if __name__ == "__main__":
    run_pipeline()
