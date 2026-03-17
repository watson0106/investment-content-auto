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


def build_research_prompt(articles: list[dict]) -> str:
    news_block = "\n".join(
        f"- [{a['source']}] {a['title']}\n  {a['summary'][:200]}\n  URL: {a['url']}"
        for a in articles
    )
    return f"""あなたはプロの投資ジャーナリストです。
以下の投資ニュースを分析し、note.com 向けの詳細な投資解説記事のドラフトを日本語で作成してください。

【本日のニュース一覧】
{news_block}

【記事要件】
1. 最も市場インパクトが大きいニュースを1〜2本メインテーマとして選ぶ
2. 構成：
   - リード文（300字）：今日の最重要ポイントを一言でつかむ
   - 背景・文脈（500字）：なぜ今これが重要か
   - 詳細分析（800字）：数値・固有名詞を含む具体的分析
   - 関連銘柄・市場への影響（400字）：具体的な銘柄・指数名を挙げる
   - 投資家へのインプリケーション（400字）：何をすべきか・何に注目すべきか
   - まとめ（200字）
3. 全体で2500〜3500字を目標とする
4. 専門用語には簡単な補足を付ける
5. 参照したニュースのURLを末尾に列挙する

記事のみを出力してください（前置きや説明は不要）。"""


def run_deep_research(articles: list[dict]) -> dict:
    """Gemini API で記事ドラフトを生成"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = build_research_prompt(articles)

    print("  Gemini で深掘り分析中...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=4096,
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

    result = run_deep_research(articles)

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
