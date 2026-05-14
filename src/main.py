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
import subprocess
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


def already_ran_today() -> bool:
    """今日すでにpost1を実行済みか確認（重複投稿防止）"""
    log_path = "output/pipeline.log"
    if not os.path.exists(log_path):
        return False
    today = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith(today) and "[post1]" in line:
                return True
    return False


# ─────────────────────────────────────────────────────────────────
# MODE: generate
# 05:00 に実行。ニュース収集 → 記事2本執筆 → ファイル保存
# ─────────────────────────────────────────────────────────────────

def run_stock_analysis(article_num: int, article: dict):
    """1記事分の株式短期分析（有料note生成）を実行する"""
    _sa_main = os.path.expanduser("~/stock-analysis-auto/src/main.py")
    if article.get("skip_stock"):
        print(f"  [SKIP] 記事{article_num}: 銘柄セクションなし → 有料note生成スキップ")
        return
    if not os.path.exists(_sa_main):
        print("  [SKIP] ~/stock-analysis-auto が見つかりません")
        return
    article_abs = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), f"output/article_{article_num}.json")
    if not os.path.exists(article_abs):
        print(f"  [SKIP] {article_abs} が見つかりません")
        return
    sa_env = {k: v for k, v in os.environ.items()
              if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
    sa_env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + sa_env.get("PATH", "/usr/bin:/bin")
    sa_env["PYTHONUNBUFFERED"] = "1"
    # /usr/bin/python3 を明示的に使う（Claude Code の venv を避けるため）
    python_bin = "/usr/bin/python3"
    print(f"  [INFO] 実行: {python_bin} {_sa_main} --article {article_abs}")
    try:
        sa_result = subprocess.run(
            [python_bin, _sa_main, "--article", article_abs],
            env=sa_env,
            cwd=os.path.expanduser("~/stock-analysis-auto/src"),
            timeout=1800,
            stderr=subprocess.STDOUT,  # stderr を stdout にマージして pipeline.log に出力
        )
        if sa_result.returncode != 0:
            print(f"  [WARN] 株式短期分析（記事{article_num}）非ゼロ終了 (code={sa_result.returncode})")
        else:
            print(f"  [INFO] 株式短期分析（記事{article_num}）正常終了")
    except subprocess.TimeoutExpired:
        print(f"  [WARN] 株式短期分析（記事{article_num}）タイムアウト（30分）")
    except Exception:
        print(f"  [WARN] 株式短期分析（記事{article_num}）失敗")
        traceback.print_exc()


def mode_generate(topic_keyword: str = None, skip_collect: bool = False):
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
    if skip_collect:
        print("  [SKIP] --skip-collect: 既存の collected_news.json を使用")
    else:
        try:
            collect_news.main()
        except Exception:
            print("❌ ニュース収集失敗（重要ステップ）")
            traceback.print_exc()
            sys.exit(1)

    # ② 記事執筆（複数トピック・複数記事）
    print(f"\n{'─'*40}")
    print("  ② 記事執筆（複数ニュース・複数記事）")
    print(f"{'─'*40}")
    try:
        articles_result = deep_research.main(force_topic_keyword=topic_keyword)
        article_nums = sorted(
            int(k.split("_")[1]) for k in articles_result if k.startswith("article_")
        )
        print(f"  執筆完了: {len(article_nums)}本")
        for n in article_nums:
            print(f"    記事{n}: {articles_result[f'article_{n}']['title']}")
    except Exception:
        print("❌ 記事執筆失敗（重要ステップ）")
        traceback.print_exc()
        sys.exit(1)

    results = []
    for article_num in article_nums:
        article = articles_result[f"article_{article_num}"]

        # ③ 株式短期分析（有料note）
        print(f"\n{'─'*40}")
        print(f"  ③ 株式短期分析（記事{article_num}）")
        print(f"{'─'*40}")
        run_stock_analysis(article_num, article)

        # ④ note下書き保存
        print(f"\n{'─'*40}")
        print(f"  ④ note下書き保存（記事{article_num}）")
        print(f"{'─'*40}")
        try:
            r = mode_post(article_num)
            results.append(r)
        except SystemExit:
            results.append({"url": ""})

    r1 = results[0] if results else {"url": ""}

    print("\n" + "=" * 50)
    print(f"✅ 生成・保存完了（{len(results)}本）")
    for i, r in enumerate(results, 1):
        print(f"  記事{i}: {r.get('url', f'output/article_{i}.json')}")
    print("=" * 50)

    notify("【下書き保存完了】", f"{len(results)}本の記事を保存しました")
    return r1, r1


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

    # ── 公開前QAチェック ──
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from pre_publish_check import check_and_auto_fix
        print("  公開前QAチェック中...")
        qa_ok, fixed_article = check_and_auto_fix(title, data.get("article", ""))
        if fixed_article != data.get("article", ""):
            data["article"] = fixed_article
            with open(article_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        if not qa_ok:
            print("  [QA] 重大エラーあり（投稿は続行・手動確認推奨）")
    except Exception as _e:
        print(f"  [WARN] QAチェックスキップ: {_e}")

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

    # X告知ポストのURLを実際のnote URLに置換して表示
    x_post = data.get("x_post", "")
    if x_post and url:
        x_post_final = x_post.replace("[note_url]", url)
        print(f"\n📢 X告知ポスト（コピペ用）:")
        print("─" * 40)
        print(x_post_final)
        print("─" * 40)
        # article JSONにも更新
        try:
            data["x_post_final"] = x_post_final
            with open(article_file, "w", encoding="utf-8") as _f:
                json.dump(data, _f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    print(f"\n✅ 下書き保存完了: {url}")
    print("  公開は手動で行ってください")
    notify(f"【下書き保存完了】記事{article_num}", f"{title}\n{url}")

    return result


# ─────────────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────────────

def run_pipeline(topic_keyword: str = None, skip_collect: bool = False):
    """引数なし手動実行: generate → post1"""
    print("=" * 50)
    print("投資記事自動生成パイプライン 開始（全ステップ）")
    today = datetime.datetime.now(JST)
    print(f"  日時: {today.strftime('%Y-%m-%d %H:%M')} JST  曜日: {['月','火','水','木','金','土','日'][today.weekday()]}")
    print("=" * 50)

    result1, _ = mode_generate(topic_keyword=topic_keyword, skip_collect=skip_collect)

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
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["generate", "post1", "post2"], default=None)
    parser.add_argument("--force", action="store_true", help="当日実行済みチェックをスキップ")
    parser.add_argument("--topic-keyword", default=None, help="このキーワードを含むニュースを強制選定")
    parser.add_argument("--skip-collect", action="store_true", help="ニュース収集をスキップして既存のcollected_news.jsonを使用")
    args = parser.parse_args()

    if args.mode == "generate":
        mode_generate()
    elif args.mode == "post1":
        mode_post(1)
    elif args.mode == "post2":
        mode_post(2)
    else:
        if not args.force and already_ran_today():
            print("⚠️  本日すでに記事を投稿済みです。重複投稿を防ぐためスキップします。")
            print("   強制実行する場合は --force オプションを使用してください。")
            sys.exit(0)
        run_pipeline(topic_keyword=args.topic_keyword, skip_collect=args.skip_collect)
