"""
パイプライン全体を順番に実行するエントリポイント

毎日:
  ① ニュース収集 → ② Gemini記事執筆 → ③ Claude添削
  → ④ 画像生成 → ⑤ タイトル生成
  → ⑥ note 投稿（無料記事）
  → ⑦ 投稿結果の検証
  → ⑧ 有料記事生成・投稿（100円）
  → ⑨ 無料記事に有料記事リンクを追記
  → ⑩ PDCAトラッカー（スキ数更新）
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
import generate_paid_article
import pdca_tracker

JST = datetime.timezone(datetime.timedelta(hours=9))


def verify_posted_article(url: str | None, note_key: str | None):
    """投稿された記事を検証する"""
    if not url:
        print("  [FAIL] 投稿URLがありません")
        return

    print(f"  検証対象: {url}")

    # final.json から期待値を読み取り
    with open("output/final.json", encoding="utf-8") as f:
        final = json.load(f)

    expected_title = final.get("title", "")
    expected_images = len(final.get("image_paths", []))
    article_len = len(final.get("article", ""))

    checks = []

    # 1. タイトルが日本語かチェック
    has_japanese = any('\u3000' <= c <= '\u9fff' or '\u30a0' <= c <= '\u30ff' for c in expected_title)
    if has_japanese:
        checks.append(("タイトルが日本語", True))
    else:
        checks.append(("タイトルが日本語", False))
        print(f"  [FAIL] タイトルが日本語でない: {expected_title}")

    # 2. タイトルにMarkdown/テーブル書式が残っていないか
    has_markdown = "|" in expected_title or "**" in expected_title
    if not has_markdown:
        checks.append(("タイトルにMarkdown残骸なし", True))
    else:
        checks.append(("タイトルにMarkdown残骸なし", False))
        print(f"  [FAIL] タイトルにMarkdown残骸あり: {expected_title}")

    # 3. 記事本文が十分な長さか（最低2000文字）
    if article_len >= 2000:
        checks.append((f"記事本文 {article_len}文字（2000字以上）", True))
    else:
        checks.append((f"記事本文 {article_len}文字（2000字未満）", False))
        print(f"  [FAIL] 記事本文が短すぎる: {article_len}文字")

    # 4. 記事本文がAI会話応答でないか
    article_text = final.get("article", "")
    reject_phrases = ["承知しています", "何か具体的な", "作業がありますか", "お手伝い"]
    is_conversational = any(p in article_text[:300] for p in reject_phrases)
    if not is_conversational:
        checks.append(("記事本文がAI会話応答でない", True))
    else:
        checks.append(("記事本文がAI会話応答でない", False))
        print(f"  [FAIL] 記事本文がAI会話応答: {article_text[:100]}")

    # 5. 見出し（##）が含まれているか
    heading_count = article_text.count("## ")
    if heading_count >= 3:
        checks.append((f"見出し{heading_count}個あり", True))
    else:
        checks.append((f"見出し{heading_count}個（3個未満）", False))
        print(f"  [FAIL] 見出しが少ない: {heading_count}個")

    # 結果表示
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    print(f"\n  検証結果: {passed}/{total} パス")
    for name, ok in checks:
        mark = "OK" if ok else "NG"
        print(f"    {mark} {name}")

    if passed < total:
        print(f"\n  [WARN] {total - passed}件の検証に失敗しています")
    else:
        print(f"\n  [OK] 全検証パス")


def run_pipeline():
    print("=" * 50)
    print("投資記事自動生成パイプライン 開始")
    today = datetime.datetime.now(JST)
    print(f"  日時: {today.strftime('%Y-%m-%d %H:%M')} JST  曜日: {['月','火','水','木','金','土','日'][today.weekday()]}")
    print("=" * 50)

    # ── 毎日実行ステップ ──────────────────────────────────────────

    # ── ①〜④ 記事生成ステップ ──────────────────────────────────────

    gen_steps = [
        ("① ニュース収集",    collect_news.main),
        ("② Gemini 記事執筆", deep_research.main),
        ("③ Claude 添削",     fact_check.main),
        ("④ タイトル生成",    generate_title.main),
    ]

    for name, func in gen_steps:
        print(f"\n{'─'*40}")
        print(f"  {name}")
        print(f"{'─'*40}")
        try:
            func()
        except Exception:
            print(f"\n[ERROR] {name} でエラー発生:")
            traceback.print_exc()
            if name.startswith("①") or name.startswith("②"):
                print("  重要ステップ失敗のため終了")
                sys.exit(1)

    # ── ⑤ 有料記事生成・投稿（先に投稿してURLを取得） ──────────────

    paid_url = None
    paid_article_text = ""
    print(f"\n{'─'*40}")
    print("  ⑤ 有料記事生成・投稿（100円）")
    print(f"{'─'*40}")
    try:
        with open("output/polished.json", encoding="utf-8") as f:
            polished_data = json.load(f)
        with open("output/final.json", encoding="utf-8") as f:
            final_data = json.load(f)

        free_article_text = polished_data.get("polished", "")
        free_title_text = final_data.get("title", "")

        paid_result = generate_paid_article.generate_paid_article(free_article_text, free_title_text)
        paid_article_text = paid_result.get("article", "")

        with open("output/paid_draft.json", "w", encoding="utf-8") as f:
            json.dump(paid_result, f, ensure_ascii=False, indent=2)

        print("  noteに有料記事を投稿中...")
        headless = os.environ.get("HEADLESS", "true").lower() == "true"
        paid_tags = ["投資", "有料記事", "投資戦略", "ポートフォリオ"]
        paid_url = post_to_note.post_article(
            title=paid_result["title"],
            body=paid_article_text,
            image_paths=[],
            tags=paid_tags,
            headless=headless,
            cover_path=None,
            price=100,
        )
        if paid_url:
            print(f"  有料記事投稿完了: {paid_url}")
            with open("output/paid_posted.json", "w", encoding="utf-8") as f:
                json.dump({"url": paid_url, "title": paid_result["title"], "price": 100}, f, ensure_ascii=False, indent=2)
    except Exception:
        print("  [WARN] 有料記事生成・投稿エラー（継続）:")
        traceback.print_exc()

    # ── ⑥ 無料記事投稿（有料記事への導線を含めて投稿） ────────────

    posted_note_key = None
    posted_url = None
    print(f"\n{'─'*40}")
    print("  ⑥ note 投稿（無料記事 + 有料記事への導線）")
    print(f"{'─'*40}")
    try:
        with open("output/final.json", encoding="utf-8") as f:
            final_data = json.load(f)

        free_body = final_data.get("article", "")

        # 有料記事URLがあれば導線テキストを末尾に追加してから投稿
        if paid_url:
            cta = generate_paid_article.build_free_article_cta(paid_url, paid_article_text)
            free_body = free_body.rstrip() + cta
            print("  有料記事への導線を本文末尾に追加")

        headless = os.environ.get("HEADLESS", "true").lower() == "true"
        result = post_to_note.post_article(
            title=final_data["title"],
            body=free_body,
            image_paths=[],
            tags=post_to_note.NOTE_TAGS,
            headless=headless,
            cover_path=None,
        )
        if result:
            posted_url = result
            import re
            m = re.search(r"/n/([a-zA-Z0-9]+)$", posted_url)
            if m:
                posted_note_key = m.group(1)
            print(f"  無料記事投稿完了: {posted_url}")

            with open("output/posted.json", "w", encoding="utf-8") as f:
                json.dump({"url": posted_url, "title": final_data["title"], "status": "success"}, f, ensure_ascii=False, indent=2)
    except Exception:
        print(f"\n[ERROR] 無料記事投稿エラー:")
        traceback.print_exc()

    # ── ⑦ 投稿結果の検証 ──────────────────────────────────────────

    print(f"\n{'─'*40}")
    print("  ⑦ 投稿結果の検証")
    print(f"{'─'*40}")
    try:
        verify_posted_article(posted_url, posted_note_key)
    except Exception:
        print("  [WARN] 検証エラー（継続）:")
        traceback.print_exc()

    # ── ⑩ PDCAトラッカー（スキ数更新 + 記事登録） ─────────────────

    print(f"\n{'─'*40}")
    print("  ⑩ PDCAトラッカー（スキ数更新）")
    print(f"{'─'*40}")
    try:
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
        pdca_tracker.main(mode="daily")
    except Exception:
        print("  [WARN] PDCAトラッカーエラー（継続）:")
        traceback.print_exc()

    # ── 完了 ─────────────────────────────────────────────────────

    print("\n" + "=" * 50)
    print("パイプライン完了")
    print("=" * 50)

    if posted_url:
        print(f"投稿URL: {posted_url}")

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


if __name__ == "__main__":
    run_pipeline()
