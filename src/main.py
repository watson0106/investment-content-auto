"""
パイプライン全体を順番に実行するエントリポイント

毎日（04:00 JST）:
  ① ニュース収集 → ② 記事執筆（個人視点・一人称） → ③ クリーンアップ
  → ④ 画像生成 → ⑤ タイトル生成（動的・PDCA反映）
  → ⑥ note 投稿（無料）
  → ⑨ 有料記事生成・投稿（推奨銘柄があれば毎日）
  → 無料記事に有料記事リンクを追記
  → ⑦ YouTube note 下書き
  → ⑧ PDCAトラッカー（スキ数更新）

月曜のみ追加:
  → ⑩ 週次PDCA分析（strategy_state.json 更新）

初回のみ:
  → プロフィール更新
"""

from __future__ import annotations

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
import fact_check
import generate_images
import generate_title
import post_to_note
import youtube_note_pipeline
import pdca_tracker
import generate_paid_article
import update_note_profile
import manage_magazine
import daily_report
import anomaly_detector

JST = datetime.timezone(datetime.timedelta(hours=9))


def is_weekly_analysis_day() -> bool:
    """月曜(0)"""
    return datetime.datetime.now(JST).weekday() == 0


def run_pipeline():
    print("=" * 50)
    print("投資記事自動生成パイプライン 開始")
    today = datetime.datetime.now(JST)
    print(f"  日時: {today.strftime('%Y-%m-%d %H:%M')} JST  曜日: {['月','火','水','木','金','土','日'][today.weekday()]}")
    print("=" * 50)

    # ── 毎日実行ステップ ──────────────────────────────────────────

    steps = [
        ("① ニュース収集",              collect_news.main),
        ("② Claude 記事執筆（個人視点）", deep_research.main),
        ("③ クリーンアップ",             fact_check.main),
        ("④ 画像生成",                  generate_images.main),
        ("⑤ タイトル生成（動的）",       generate_title.main),
        ("⑥ note 投稿（無料）",          post_to_note.main),
    ]

    posted_note_key = None
    free_article_url = None
    recommended_stocks: list[str] = []

    for name, func in steps:
        print(f"\n{'─'*40}")
        print(f"  {name}")
        print(f"{'─'*40}")
        try:
            result = func()
            if name.startswith("②") and isinstance(result, dict):
                recommended_stocks = result.get("recommended_stocks", [])

            # ⑥の結果からnote_keyを取得
            if name.startswith("⑥") and isinstance(result, dict):
                free_article_url = result.get("url", "")
                import re
                m = re.search(r"/n/([a-zA-Z0-9]+)$", free_article_url)
                if m:
                    posted_note_key = m.group(1)
        except Exception:
            print(f"\n[ERROR] {name} でエラー発生:")
            traceback.print_exc()
            if name.startswith("①") or name.startswith("②"):
                print("  重要ステップ失敗のため終了")
                sys.exit(1)
            # 非重要ステップは継続

    # ── draft.json から推奨銘柄を読み取り（②の返り値がなかった場合のフォールバック）──
    if not recommended_stocks:
        try:
            with open("output/draft.json", encoding="utf-8") as f:
                draft_data = json.load(f)
            recommended_stocks = draft_data.get("recommended_stocks", [])
        except Exception:
            pass

    # ── ⑨ 有料記事生成・投稿（推奨銘柄があれば毎日） ─────────────────

    paid_articles: list[dict] = []

    if recommended_stocks:
        print(f"\n{'─'*40}")
        print(f"  ⑨ 有料記事生成・投稿（推奨銘柄: {', '.join(recommended_stocks[:1])}）")
        print(f"{'─'*40}")
        for stock in recommended_stocks[:1]:  # 1番目の銘柄で1記事のみ
            try:
                paid_result = generate_paid_article.create_paid_article_for_stock(stock)
                if paid_result and paid_result.get("url"):
                    paid_articles.append(paid_result)
            except Exception:
                print(f"  [WARN] 有料記事生成失敗：{stock}")
                traceback.print_exc()
    else:
        print(f"\n{'─'*40}")
        print("  ⑨ 有料記事生成 → スキップ（推奨銘柄なし）")
        print(f"{'─'*40}")

    # ── 無料記事に有料記事リンクを追記 ──────────────────────────────

    if paid_articles and posted_note_key:
        print(f"\n{'─'*40}")
        print("  無料記事に有料記事リンクを追記")
        print(f"{'─'*40}")
        try:
            link_lines = []
            for pa in paid_articles:
                stock_name = pa.get("target_stock", "銘柄")
                paid_url = pa.get("url", "")
                link_lines.append(
                    f"▶ {stock_name}の詳細IR分析はこちら\n{paid_url}"
                )
            append_text = "\n\n---\n\n" + "\n\n".join(link_lines)
            headless = os.environ.get("HEADLESS", "true").lower() == "true"
            post_to_note.update_article_body(posted_note_key, append_text, headless=headless)
        except Exception:
            print("  [WARN] 無料記事へのリンク追記失敗（継続）:")
            traceback.print_exc()

    # ── ⑦ YouTube note 下書き ────────────────────────────────────

    print(f"\n{'─'*40}")
    print("  ⑦ YouTube note 下書き")
    print(f"{'─'*40}")
    try:
        youtube_note_pipeline.main()
    except Exception:
        print("  [WARN] YouTube note 下書きエラー（継続）:")
        traceback.print_exc()

    # ── ⑧ PDCAトラッカー（スキ数更新 + 記事登録） ─────────────────

    print(f"\n{'─'*40}")
    print("  ⑧ PDCAトラッカー（スキ数更新）")
    print(f"{'─'*40}")
    try:
        # 今日の記事をパフォーマンスDBに登録
        if posted_note_key:
            try:
                with open("output/final.json", encoding="utf-8") as f:
                    final_data = json.load(f)
                with open("output/collected_news.json", encoding="utf-8") as f:
                    news_data = json.load(f)
                source_news = [a.get("title", "") for a in news_data[:3]]
                pdca_tracker.record_posted_article(
                    note_key=posted_note_key,
                    title=final_data.get("title", ""),
                    source_news=source_news,
                    is_paid=False,
                    price=0,
                )
            except Exception as e:
                print(f"  [WARN] 記事登録失敗: {e}")

        # 直近30日分のスキ数を更新
        pdca_tracker.main(mode="daily")

    except Exception:
        print("  [WARN] PDCAトラッカーエラー（継続）:")
        traceback.print_exc()

    # ── ⑩ 週次PDCA分析（月曜のみ） ──────────────────────────────

    if is_weekly_analysis_day():
        print(f"\n{'─'*40}")
        print("  ⑩ 週次PDCA分析（strategy_state.json 更新）")
        print(f"{'─'*40}")
        try:
            pdca_tracker.main(mode="weekly")
        except Exception:
            print("  [WARN] 週次PDCA分析エラー（継続）:")
            traceback.print_exc()

    # ── ⑪ マガジン自動管理（高スキ記事を自動追加） ─────────────

    print(f"\n{'─'*40}")
    print("  ⑪ マガジン自動管理")
    print(f"{'─'*40}")
    try:
        manage_magazine.main()
    except Exception:
        print("  [WARN] マガジン管理エラー（継続）:")
        traceback.print_exc()

    # ── ⑫ 異常検知 ──────────────────────────────────────────────

    print(f"\n{'─'*40}")
    print("  ⑫ 異常検知・チェック")
    print(f"{'─'*40}")
    anomaly_result = {}
    try:
        anomaly_result = anomaly_detector.run_checks()
    except Exception:
        print("  [WARN] 異常検知エラー（継続）:")
        traceback.print_exc()

    # ── プロフィール更新（必要な場合のみ） ──────────────────────

    try:
        if update_note_profile.should_update_profile():
            print(f"\n{'─'*40}")
            print("  プロフィール更新")
            print(f"{'─'*40}")
            update_note_profile.main()
    except Exception:
        print("  [WARN] プロフィール更新エラー（継続）:")
        traceback.print_exc()

    # ── 完了 ─────────────────────────────────────────────────────

    print("\n" + "=" * 50)
    print("パイプライン完了")
    print("=" * 50)

    try:
        with open("output/posted.json") as f:
            result = json.load(f)
        print(f"投稿URL: {result.get('url', '不明')}")
    except Exception:
        pass

    # 記事履歴に追記
    try:
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

    # ── 日次レポート通知 ─────────────────────────────────────────
    try:
        posted_url = ""
        try:
            with open("output/posted.json") as f:
                posted_url = json.load(f).get("url", "")
        except Exception:
            pass
        daily_report.send_daily_report(
            posted_url=posted_url,
            anomaly_result=anomaly_result,
        )
    except Exception:
        print("  [WARN] 日次レポート送信エラー（継続）:")
        traceback.print_exc()


if __name__ == "__main__":
    run_pipeline()
