"""
⑤ クリックされるタイトル生成
記事内容をもとに note 向けの魅力的なタイトル候補を生成する（Claude CLI 使用・APIキー不要）
"""

from __future__ import annotations


import json
import os
import subprocess


def generate_titles(article_text: str) -> list[str]:
    """Claude CLI でタイトル候補を生成"""
    prompt = f"""以下の投資解説記事に対して、note.com で多くの読者にクリックされるタイトルを10案生成してください。

【記事冒頭（参考）】
{article_text[:1500]}

【タイトル設計のルール】
- 「このニュースを見た読者が抱く素朴な疑問」をそのままタイトルにする
- 例：「なぜ日経が700円も上がったの？」「FRBが動かないと株はどうなる？」「円安で得するのは誰？」
- 疑問形（〜の？/〜なの？/〜するの？）を基本とする
- 具体的な数字・固有名詞を入れるとなお良い（例：「700円高」「5.5%」「FRB」）
- 20〜35字以内。長すぎNG
- 難しい専門用語NG。誰でも読めるひらがな・カタカナ中心
- 煽り・誇大表現NG

【出力形式】
1. タイトル案1
2. タイトル案2
...
10. タイトル案10

タイトル候補のみを出力してください。"""

    # Claude CLI が使えるか確認
    claude_available = subprocess.run(["which", "claude"], capture_output=True).returncode == 0

    text = ""
    if claude_available:
        print("  Claude CLI でタイトル生成中...")
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=60, env=env
        )
        text = result.stdout.strip() if result.returncode == 0 else ""

    if not text:
        # Gemini フォールバック
        from google import genai
        from google.genai import types
        print("  Gemini でタイトル生成中...")
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.8, max_output_tokens=1024),
        )
        text = response.text.strip()
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]

    # 番号付きリストをパース
    titles = []
    for line in lines:
        # "1. タイトル" 形式
        import re
        m = re.match(r"^\d+[\.\)]\s*(.+)$", line)
        if m:
            titles.append(m.group(1).strip())
        elif line and not line.startswith("#"):
            titles.append(line)

    print(f"  {len(titles)} 案のタイトルを生成")
    return titles[:10]


def select_best_title(titles: list[str]) -> str:
    """スコアリングで最良タイトルを自動選択"""
    def score(title: str) -> float:
        s = 0.0
        import re
        if re.search(r"\d", title):     s += 2.0   # 数字あり
        if "？" in title or "!" in title: s += 1.0  # 疑問・感嘆
        if len(title) <= 40:            s += 1.0   # 適切な長さ
        keywords = ["米国株", "日本株", "FRB", "AI", "半導体", "ETF", "円", "株", "市場", "Fed"]
        for kw in keywords:
            if kw in title:
                s += 0.5
        return s

    return max(titles, key=score)


FIXED_TITLE = "新聞よりわかりやすくて早い今日の投資ニュース速報"


def main():
    print("=== ⑤ タイトル生成 ===")

    with open("output/article_with_images.json", encoding="utf-8") as f:
        data = json.load(f)

    print(f"  タイトル固定: {FIXED_TITLE}")

    result = {
        "title":        FIXED_TITLE,
        "title_options": [FIXED_TITLE],
        "article":      data["article"],
        "image_paths":  data.get("image_paths", []),
        "articles":     data["articles"],
    }

    out_path = "output/final.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n保存: {out_path}")
    return result


if __name__ == "__main__":
    main()
