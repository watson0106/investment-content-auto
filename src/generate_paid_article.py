"""
有料記事の自動生成・投稿（推奨銘柄IR分析レポート）
- output/draft.json の recommended_stocks から銘柄を取得
- Claudeで5年IR分析レポートを執筆
- noteに有料記事として公開（¥480）
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
DEFAULT_PRICE = 480


# ─── トピック選定 ────────────────────────────────────────────────

def select_paid_topic() -> dict | None:
    """
    output/draft.json の recommended_stocks から有料記事の対象銘柄を取得。
    recommended_stocks がなければ None を返してスキップ。
    複数銘柄がある場合は1番目で1記事作成。
    """
    draft_path = os.path.join(_BASE, "output", "draft.json")
    if not os.path.exists(draft_path):
        print("  [有料] draft.json が見つかりません。スキップ")
        return None

    with open(draft_path, encoding="utf-8") as f:
        draft_data = json.load(f)

    stocks = draft_data.get("recommended_stocks", [])
    if not stocks:
        print("  [有料] recommended_stocks が空です。有料記事スキップ")
        return None

    target = stocks[0]
    print(f"  [有料] 対象銘柄: {target}（候補{len(stocks)}件中1番目）")
    return {
        "target_stock": target,
        "all_stocks": stocks,
    }


# ─── 有料記事生成 ────────────────────────────────────────────────

def build_paid_prompt(topic: dict) -> str:
    target_stock = topic["target_stock"]

    return f"""あなたはゴールドマンサックスのウォーレン・バフェットにも劣らない超優秀なアナリストです。
銘柄コード {target_stock} について、個人投資家向けのIR分析レポートを執筆してください。

【重要な禁止事項】
- 「○○円で買い」「今が買い時」等の具体的な売買タイミングは絶対に記載禁止
- 「今すぐ買え」「売れ」等の断定的な投資助言は禁止
- あくまで投資判断の「材料」を提供する立場で書くこと

【事前リサーチ（必須）】
まず以下を調査してから執筆を開始してください：
- この銘柄の正式企業名、事業内容、東証業種分類
- 過去5年分のIR資料（有価証券報告書、決算短信、決算説明資料）
- 業界の市場規模、主要プレイヤー、競合状況
- 最新のアナリストレポートや市場コンセンサス

【記事構成（必ずこの順番・見出しで）】

## 企業概要

（400字程度）
- 正式社名、設立年、本社所在地、従業員数
- 主要事業内容・サービス
- 現在の時価総額、株価水準
- 東証業種分類またはGICSセクター

---

## 5年IR分析

（1000字程度。IR資料に基づく事実ベースの分析）
- 売上高・営業利益・純利益の5年推移（具体的な数値で）
- 売上高成長率・営業利益率の推移
- ROE・ROAの推移と変動要因
- キャッシュフロー分析（営業CF、投資CF、FCF）
- 配当推移・配当性向・自社株買い実績

---

## 業界と競合分析

（600字程度）
- 属する業界の市場規模と成長率
- 主要プレイヤー3〜5社との比較
- 市場シェアとポジショニング
- 業界の構造変化（新規参入、統合、技術革新）

---

## 成長シナリオ

（800字程度。3シナリオを定量的に提示）

### ブルシナリオ（強気）
- 前提条件、売上・利益の想定水準、確度

### ベースシナリオ（中立）
- 前提条件、売上・利益の想定水準、確度

### ベアシナリオ（弱気）
- 前提条件、売上・利益の想定水準、確度

---

## リスク分析

（500字程度）
- 規制リスク（法改正、許認可、コンプライアンス）
- 競合リスク（新規参入、価格競争、技術代替）
- マクロリスク（為替、金利、景気サイクル、地政学）
- 固有リスク（経営陣、ガバナンス、訴訟、特定顧客依存）

---

## 注目KPI

（400字程度）
- この銘柄を追跡する上で投資家が注視すべき指標を5〜8個
- 各KPIの現在値、過去推移、なぜ重要かを簡潔に

---

## バリュエーション

（600字程度）
- PER、PBR、PSR、EV/EBITDA等の主要指標
- 同業他社との比較（具体的な数値で）
- 過去5年の自社バリュエーション推移
- 現在の水準が割高/割安かの定量的評価

---

## 私の見解

（400字程度）
- なぜこの銘柄に注目しているのか
- どういうタイプの投資家に向いている銘柄か（成長株志向、配当志向、バリュー志向等）
- 投資判断にあたって最も重視すべきポイント
- ※売買推奨ではなく、あくまで筆者個人の分析視点として

---

## まとめ

（箇条書き5〜7項目。数値を交えて要点整理）

【執筆ルール】
- 全体で5000字以上
- 具体的な数値・事実を重視（「高い」ではなく「15.3%」）
- IR資料に基づく客観的事実を軸に記述
- 売買タイミングや価格目標は一切記載しない
- 投資助言にならないよう、判断材料の提供に留める
- 専門用語は都度説明
- 絵文字NG
- 冒頭に前置き不要。最初の文字は「## 企業概要」で始めること

【免責表記（記事末尾に必ず記載）】
※本記事は特定の金融商品の売買を推奨するものではありません。投資判断はご自身の責任で行ってください。記載された情報は執筆時点のものであり、正確性を保証するものではありません。"""


def generate_paid_article_text(topic: dict) -> str:
    """Claude CLI で有料記事を生成（Gemini フォールバック付き）"""
    prompt = build_paid_prompt(topic)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    draft = ""
    import shutil
    claude_path = shutil.which("claude")
    if claude_path:
        print("  Claude CLI で有料記事執筆中...")
        result = subprocess.run(
            [claude_path, "-p", prompt, "--output-format", "text", "--model", "claude-opus-4-6"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, env=env,
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

def post_paid_to_note(title: str, body: str, price: int = DEFAULT_PRICE) -> str:
    """note に有料記事として公開し URL を返す"""
    import post_to_note
    headless = os.environ.get("HEADLESS", "true").lower() == "true"

    url = post_to_note.post_article(
        title=title,
        body=body,
        image_paths=[],
        tags=["投資", "有料記事", "IR分析", "個別銘柄分析", "企業分析"],
        headless=headless,
        cover_path=None,
        price=price,
    )
    return url


def create_paid_article_for_stock(target_stock: str, free_summary: str = "") -> dict:
    """推奨銘柄に対してIR分析レポートを生成・公開する"""
    topic = {
        "target_stock": target_stock,
    }
    title = f"【IR分析】{target_stock} 5年財務分析と成長シナリオ"
    print(f"  [有料] {target_stock} のIR分析レポートを生成中...")
    article_text = generate_paid_article_text(topic)
    url = post_paid_to_note(title, article_text, price=DEFAULT_PRICE)

    if url:
        m = re.search(r"/n/([a-zA-Z0-9]+)$", url)
        if m:
            try:
                from pdca_tracker import record_posted_article
                record_posted_article(
                    note_key=m.group(1),
                    title=title,
                    source_news=[target_stock],
                    is_paid=True,
                    price=DEFAULT_PRICE,
                )
            except Exception as e:
                print(f"  [WARN] パフォーマンスDB登録失敗: {e}")

    result = {
        "target_stock": target_stock,
        "title": title,
        "url": url,
        "price": DEFAULT_PRICE,
        "status": "success" if url else "failed",
    }

    # output/paid_posted.json に保存（main.py が無料記事に追記するため）
    out_path = os.path.join(_BASE, "output", "paid_posted.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


# ─── メイン ─────────────────────────────────────────────────────

def main() -> dict:
    print("=== 有料記事生成・投稿（IR分析レポート） ===")

    topic = select_paid_topic()
    if not topic:
        print("  有料記事スキップ（対象銘柄なし）")
        return {}

    target_stock = topic["target_stock"]
    title = f"【IR分析】{target_stock} 5年財務分析と成長シナリオ"
    print(f"  有料記事タイトル: {title}")

    article_text = generate_paid_article_text(topic)

    url = post_paid_to_note(title, article_text, price=DEFAULT_PRICE)

    # パフォーマンスDBに登録
    if url:
        m = re.search(r"/n/([a-zA-Z0-9]+)$", url)
        if m:
            try:
                from pdca_tracker import record_posted_article
                record_posted_article(
                    note_key=m.group(1),
                    title=title,
                    source_news=[target_stock],
                    is_paid=True,
                    price=DEFAULT_PRICE,
                )
            except Exception:
                pass
            try:
                from pdca_tracker import load_strategy_state, save_strategy_state
                from datetime import datetime, timezone, timedelta
                JST = timezone(timedelta(hours=9))
                state = load_strategy_state()
                state.setdefault("paid_article_history", []).append({
                    "date": datetime.now(JST).strftime("%Y-%m-%d"),
                    "title": title,
                    "note_key": m.group(1),
                    "price": DEFAULT_PRICE,
                    "target_stock": target_stock,
                })
                save_strategy_state(state)
            except Exception:
                pass

    result = {
        "target_stock": target_stock,
        "title": title,
        "url": url,
        "price": DEFAULT_PRICE,
        "status": "success" if url else "failed",
    }
    out_path = os.path.join(_BASE, "output", "paid_posted.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'有料記事公開: ' + url if url else '有料記事投稿失敗'}")
    return result


if __name__ == "__main__":
    main()
