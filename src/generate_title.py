"""
⑤ クリックされるタイトル生成
記事内容をもとに note 向けの魅力的なタイトル候補を生成する
"""

import json
import os
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]


def generate_titles(article_text: str) -> list[str]:
    """Claude API でタイトル候補を生成"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""以下の投資解説記事に対して、note.com で多くの読者にクリックされるタイトルを10案生成してください。

【記事冒頭（参考）】
{article_text[:1500]}

【タイトル設計のルール】
- 25〜40字が理想（長すぎず短すぎず）
- 数字を含める（例：「3つの理由」「+8%上昇」「1000億円規模」）
- 疑問形・断言・驚き・緊急性のいずれかを使う
- 専門用語は避け、初心者にも伝わる言葉を選ぶ
- note の投資カテゴリで目立つキーワードを含める
  （例：米国株、日本株、ETF、FRB、AI、半導体、円安、配当など）
- 「〜してみた」「〜だった」のような体験談風は避ける
- 投資助言・推奨にならないよう「〜の可能性」「〜に注目」などの表現を使う

【出力形式】
1. タイトル案1
2. タイトル案2
...
10. タイトル案10

タイトル候補のみを出力してください。"""

    print("  Claude でタイトル生成中...")
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text
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


def main():
    print("=== ⑤ タイトル生成 ===")

    with open("output/article_with_images.json", encoding="utf-8") as f:
        data = json.load(f)

    titles = generate_titles(data["article"])

    best = select_best_title(titles)
    print(f"\n推奨タイトル: {best}")

    print("\n全候補:")
    for i, t in enumerate(titles, 1):
        marker = "★" if t == best else " "
        print(f"  {marker}{i}. {t}")

    result = {
        "title":        best,
        "title_options": titles,
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
