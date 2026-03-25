"""
⑨ 有料記事の自動生成・投稿（週2回：火・金）
- 今週の無料記事で反応が良かったテーマを選定
- Claudeで「私の実際の売買判断と戦略」を深掘り執筆
- noteに¥500の有料記事として公開
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time

from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
_BASE = os.path.join(os.path.dirname(__file__), "..")


# ─── トピック選定 ────────────────────────────────────────────────

def select_paid_topic() -> dict | None:
    """
    今週の無料記事から有料化に最適なトピックを選定。
    パフォーマンスDBがあれば高スキ記事を優先、なければcollected_newsから選ぶ。
    """
    # 今週の記事パフォーマンスを確認
    try:
        from pdca_tracker import load_performance
        from datetime import datetime, timezone, timedelta
        JST = timezone(timedelta(hours=9))
        perf = load_performance()
        now = datetime.now(JST)
        week_ago = now - timedelta(days=7)
        recent = [
            p for p in perf
            if not p.get("is_paid") and
               datetime.fromisoformat(p["posted_at"]) >= week_ago
        ]
        if recent:
            best = max(recent, key=lambda x: x.get("latest_likes", 0))
            if best.get("latest_likes", 0) >= 1:
                print(f"  [有料] 高スキ記事を選定: {best['title'][:40]} ({best['latest_likes']}スキ)")
                return best
    except Exception as e:
        print(f"  [WARN] パフォーマンスDB参照失敗: {e}")

    # フォールバック: collected_news.json から Gemini で選定
    news_path = os.path.join(_BASE, "output", "collected_news.json")
    if not os.path.exists(news_path):
        print("  [WARN] collected_news.json が見つかりません")
        return None

    with open(news_path, encoding="utf-8") as f:
        articles = json.load(f)

    client = genai.Client(api_key=GEMINI_API_KEY)
    article_list = "\n".join(
        f"{i+1}. [{a['source']}] {a['title']}\n   {a['summary'][:100]}"
        for i, a in enumerate(articles[:20])
    )
    prompt = f"""以下のニュースから、個人投資家の「私の売買判断と戦略」を深掘りするのに最も適した1本を選び、
JSONで返してください：
{{"index": 選んだ番号(1始まり), "reason": "50字以内で理由", "paid_title": "【有料版】で始まる記事タイトル（40字以内）"}}

選定基準：
- 「私ならどうする？」という具体的な行動判断が書けるテーマ
- 数値・銘柄・比率を使った分析が映えるテーマ
- 複数シナリオを描けるテーマ

【ニュース一覧】
{article_list}

JSONのみ出力。"""

    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=256),
        )
        m = re.search(r"\{.*\}", resp.text, re.DOTALL)
        if m:
            result = json.loads(m.group())
            idx = max(0, min(int(result.get("index", 1)) - 1, len(articles) - 1))
            topic = {**articles[idx], "paid_title": result.get("paid_title", "")}
            print(f"  [有料] Gemini選定: {topic.get('paid_title', topic['title'])[:40]}")
            return topic
    except Exception as e:
        print(f"  [WARN] Gemini選定失敗: {e}")

    return articles[0] if articles else None


# ─── 有料記事生成 ────────────────────────────────────────────────

def build_paid_prompt(topic: dict, free_article_summary: str = "") -> str:
    title = topic.get("paid_title") or topic.get("title", "")
    source_summary = topic.get("summary", "")[:300]
    free_summary_block = (
        f"\n【今週の無料記事で触れた内容（読者は既読と仮定）】\n{free_article_summary[:500]}\n"
        if free_article_summary
        else ""
    )

    return f"""あなたは「私」として書く個人投資家ブロガー（投資歴15年以上、インデックス×個別株のハイブリッド投資）です。
「{title}」について、有料読者向けに**私の実際の売買判断と具体的な戦略**を書いてください。
{free_summary_block}
【トピック概要】
{source_summary}

【有料記事の方針】
無料記事では「背景と注目理由」まで書いた。
有料版では「私が実際に何を・いつ・いくらで・なぜ動かすか（または動かさないか）」を書く。
読者が「この記事を読んで具体的に何をすべきか」が明確になることが最優先。

【記事構成（必ずこの順番で）】

## 無料記事のおさらい（2分で読める）
（200字程度。今週のニュースの核心を一人称でまとめる。読み直し不要にする）

---

## 私がここで有料にした理由
（150字程度。「考え抜いた判断プロセスを共有したい」という誠実なスタンスで。
「なぜ私はこのテーマで有料記事を書くほどの確信があるか」を伝える）

---

## 私の現在のポジションと判断根拠
（600字程度。現在私が何をどれだけ持っているか（または持っていないか）を開示。
「私はSPXLを総資産の5%保有しており〜」「現金比率は今30%で〜」など具体的に。
なぜその比率・銘柄にしたかの判断根拠を論理的に述べる。
「多くの人は〇〇と考えているが、私は〇〇という理由で〇〇にしている」という構造）

---

## シナリオ別の私の行動計画
（800字程度。楽観・中立・悲観の3シナリオ。各シナリオで私が何をするかを具体的に：
「〇〇が〇〇円を超えたら〇〇ETFを追加する（追加予算：〇〇万円）」
「〇〇が〇〇%以上下落したら逆に〇〇を買い増す」
「〇〇の場合は全体の比率を〇〇%に落とす」
各シナリオに発動条件（数値）を必ず明記する）

---

## 私が今週中に確認する具体的チェックリスト
（箇条書き6〜8項目。数値付きで「〇〇が〇〇以上ならXX」「〇〇社の〇〇日の決算発表を確認」など行動可能なレベルで）

---

## 読者へのメッセージ
（150字程度。誠実な免責事項。「あくまで私個人の判断です。最終判断はご自身で」というスタンス）

【執筆ルール】
- 全体で4000字以上
- 主語は必ず「私」。三人称NG
- 数字は徹底的に具体的に（「高め」でなく「35%」、「下落」でなく「-12%」）
- 「私なら〇〇する」「私は〇〇と考えている」という判断の言語化を最優先
- 一般論・教科書的な説明NG。「私の判断」を前面に
- 絵文字NG
- 冒頭に前置き不要。最初の文字は「## 無料記事のおさらい」で始めること"""


def generate_paid_article_text(topic: dict, free_article_summary: str = "") -> str:
    """Claude CLI で有料記事を生成（Gemini フォールバック付き）"""
    prompt = build_paid_prompt(topic, free_article_summary)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    draft = ""
    if subprocess.run(["which", "claude"], capture_output=True).returncode == 0:
        print("  Claude CLI で有料記事執筆中...")
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text", "--model", "claude-opus-4-6"],
            capture_output=True, text=True, timeout=600, env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            draft = result.stdout.strip()
            print(f"  Claude 執筆完了（{len(draft)} 文字）")
        else:
            print(f"  [WARN] Claude CLI 失敗: {result.stderr[:200]}")

    if not draft:
        print("  Gemini で有料記事執筆中（フォールバック）...")
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.6, max_output_tokens=8000),
        )
        draft = resp.text.strip()
        print(f"  Gemini 執筆完了（{len(draft)} 文字）")

    # クリーンアップ
    from deep_research import clean_article
    return clean_article(draft)


# ─── 有料記事投稿 ────────────────────────────────────────────────

def post_paid_to_note(title: str, body: str, price: int = 500) -> str:
    """note に有料記事として公開し URL を返す"""
    import post_to_note
    headless = os.environ.get("HEADLESS", "true").lower() == "true"

    # post_article でドラフト作成後、有料公開に切り替え
    url = post_to_note.post_article(
        title=title,
        body=body,
        image_paths=[],
        tags=["投資", "有料記事", "売買戦略", "ポートフォリオ"],
        headless=headless,
        cover_path=None,
        price=price,
    )
    return url


# ─── メイン ─────────────────────────────────────────────────────

def main() -> dict:
    print("=== ⑨ 有料記事生成・投稿 ===")

    topic = select_paid_topic()
    if not topic:
        print("  [WARN] トピック選定失敗。スキップします")
        return {}

    # 今週の無料記事サマリーを取得（あれば）
    free_summary = ""
    try:
        with open("output/polished.json", encoding="utf-8") as f:
            polished_data = json.load(f)
        free_summary = polished_data.get("polished", "")[:800]
    except Exception:
        pass

    paid_title = topic.get("paid_title") or f"【有料版】{topic['title'][:35]}"
    print(f"  有料記事タイトル: {paid_title}")

    article_text = generate_paid_article_text(topic, free_summary)

    # note に投稿
    url = post_paid_to_note(paid_title, article_text, price=500)

    # パフォーマンスDBに登録
    if url:
        import re as _re
        m = _re.search(r"/n/([a-zA-Z0-9]+)$", url)
        if m:
            from pdca_tracker import record_posted_article
            record_posted_article(
                note_key=m.group(1),
                title=paid_title,
                source_news=[topic.get("title", "")],
                is_paid=True,
                price=500,
            )
        # strategy_state の paid_article_history に追記
        try:
            from pdca_tracker import load_strategy_state, save_strategy_state
            from datetime import datetime, timezone, timedelta
            JST = timezone(timedelta(hours=9))
            state = load_strategy_state()
            state.setdefault("paid_article_history", []).append({
                "date": datetime.now(JST).strftime("%Y-%m-%d"),
                "title": paid_title,
                "note_key": m.group(1) if m else "",
                "price": 500,
            })
            save_strategy_state(state)
        except Exception:
            pass

    result = {
        "title": paid_title,
        "url": url,
        "price": 500,
        "status": "success" if url else "failed",
    }
    out_path = os.path.join(_BASE, "output", "paid_posted.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'✅ 有料記事公開: ' + url if url else '❌ 有料記事投稿失敗'}")
    return result


if __name__ == "__main__":
    main()
