"""
② Gemini Deep Research で深掘り分析
収集したニュースを Gemini でまとめて記事ドラフトを生成する
"""

from __future__ import annotations


import json
import os
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]


def build_research_prompt(articles: list[dict], history_summary: str = "") -> str:
    news_block = "\n".join(
        f"- [{a['source']}] {a['title']}\n  {a['summary'][:200]}\n  URL: {a['url']}"
        for a in articles
    )
    history_block = f"\n【過去に書いたテーマ（重複禁止）】\n{history_summary}\n" if history_summary and history_summary != "（過去記事なし）" else ""

    return f"""あなたはプロの投資ジャーナリスト兼ブロガーです。
以下のニュース一覧から、本日最も投資家が知るべきニュースを**3本**選んで、
note.com 向けの投資解説記事を日本語で作成してください。
{history_block}
【本日のニュース一覧】
{news_block}

【記事構成（必ずこの順番・形式で書くこと）】

## 今日のポイント
（3つのニュースを箇条書きで一言ずつ。各30字以内）

---

## ニュース① 〔タイトル〕

### どんなニュース？
（200字程度。小学生でもわかる平易な言葉で事実を説明）

### なぜ投資家に重要なの？
（400字程度。このニュースが株・為替・金利などにどう影響するか具体的に）

### 私の見方と投資への活かし方
（400字程度。書き手の個人的な見解・考察。「私は〜と思う」「個人的には〜」の口調。
具体的にどのETF・銘柄・セクターに注目すべきか、あるいは待つべき理由も含める）

---

## ニュース② 〔タイトル〕
（同じ構成で）

---

## ニュース③ 〔タイトル〕
（同じ構成で）

---

## まとめ
（200字程度。3つのニュースを踏まえた今日の総括と読者へのメッセージ）

【執筆ルール】
- 全体で6000字以上
- ブログ口語体。「〜なんです」「〜ですよね」「実は〜」など親しみやすい表現
- 専門用語は必ず括弧で補足（例：ETF（上場投資信託））
- 数字は具体的に（「大幅」ではなく「+3.5%」など）
- タイムリーな株価・為替の数値は「〜とされています」「〜と報じられています」と表現
- **「〜円高/安」「〜指数が〜ポイント」など日々変わる相場数値をタイトルや本文の主語にしない**
- 各ニュースは「なぜ今これが重要か」の構造的背景・業界文脈・歴史的経緯を必ず掘り下げる
- 表面的な事実だけでなく、その裏にある「なぜ」「どうなる」「何に注目」を深く書く

記事本文のみ出力（前置き・説明不要）。"""


def run_deep_research(articles: list[dict], history_summary: str = "") -> dict:
    """Gemini API で記事ドラフトを生成"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = build_research_prompt(articles, history_summary=history_summary)

    print("  Gemini で深掘り分析中...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=16000,
        ),
    )

    draft = response.text
    print(f"  ドラフト生成完了（{len(draft)} 文字）")

    return {
        "draft":    draft,
        "articles": articles,
    }


def main():
    print("=== ② Gemini Deep Research ===")

    with open("output/collected_news.json", encoding="utf-8") as f:
        articles = json.load(f)

    from article_history import load_history, build_history_summary
    history_summary = build_history_summary(load_history())
    result = run_deep_research(articles, history_summary=history_summary)

    os.makedirs("output", exist_ok=True)
    out_path = "output/draft.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"保存: {out_path}")
    print("\n--- ドラフト冒頭 ---")
    print(result["draft"][:300])
    return result


if __name__ == "__main__":
    main()
