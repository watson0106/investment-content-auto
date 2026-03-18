"""
記事履歴管理
- 投稿済み記事のテーマ・キーワードを蓄積
- ニュース選定・記事生成時に重複を避けるための情報を提供
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "history", "article_history.json")


def load_history() -> list[dict]:
    """履歴を読み込む（なければ空リスト）"""
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history: list[dict]) -> None:
    """履歴を保存（最新100件まで保持）"""
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    history = history[-100:]
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def build_history_summary(history: list[dict], max_entries: int = 30) -> str:
    """ニュース選定・記事生成プロンプト用の履歴サマリーを生成"""
    if not history:
        return "（過去記事なし）"
    recent = history[-max_entries:]
    lines = []
    for h in reversed(recent):
        date = h.get("date", "")
        topics = h.get("topics", [])
        keywords = h.get("keywords", [])
        lines.append(f"- {date}：{', '.join(topics)}（キーワード：{', '.join(keywords[:5])}）")
    return "\n".join(lines)


def add_article(article_text: str, news_titles: list[str]) -> None:
    """投稿後に記事の要約を履歴に追加"""
    from google import genai
    from google.genai import types

    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    date_str = datetime.now(JST).strftime("%Y-%m-%d")

    # Geminiで記事のトピックとキーワードを抽出
    topics = []
    keywords = []
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""以下の投資記事を読み、扱ったトピックとキーワードを抽出してください。

【記事冒頭】
{article_text[:2000]}

【ニュースタイトル】
{chr(10).join(news_titles[:5])}

以下のJSONのみ出力（説明不要）：
{{
  "topics": ["トピック1（20字以内）", "トピック2", "トピック3"],
  "keywords": ["キーワード1", "キーワード2", "キーワード3", "キーワード4", "キーワード5"]
}}"""
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=256),
        )
        import re
        text = resp.text.strip()
        # ```json ... ``` ブロックを除去
        text = re.sub(r'```(?:json)?\s*', '', text).strip('`').strip()
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            parsed = json.loads(m.group())
            topics = parsed.get("topics", [])
            keywords = parsed.get("keywords", [])
    except Exception as e:
        print(f"  [WARN] 履歴抽出エラー: {e}")
        # フォールバック：ニュースタイトルから生成
        topics = [t[:30] for t in news_titles[:3]]
        keywords = []

    history = load_history()
    history.append({
        "date": date_str,
        "topics": topics,
        "keywords": keywords,
        "news_titles": news_titles[:5],
    })
    save_history(history)
    print(f"  履歴保存: {date_str} | {', '.join(topics)}")
