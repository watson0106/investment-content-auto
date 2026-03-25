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
    prompt = f"""以下の投資深掘り記事に対して、note.com で多くの読者にクリック・保存されるタイトルを10案生成してください。

【記事冒頭（参考）】
{article_text[:1500]}

【タイトル設計のルール（重要度順）】

1. **銘柄名・固有名詞を必ず入れる**
   - 銘柄名・人名・企業名・指数名が入っているタイトルは3〜4倍クリックされる
   - 例：「サンリオ」「NVIDIA」「FRB」「NISA」「日経平均」

2. **「逆張り」「意外性」「否定」型が最も強い**
   - 「〇〇は終わった」「なぜ誰も言わないのか」「実は〇〇だった」
   - 「〇〇の逆襲」「〇〇が6倍になった本当の理由」
   - 例：「レーザーテックは終わった、と言う人に反論する」

3. **保存したくなる「完全解説」型**
   - 「【保存版】〇〇完全解説」「〇〇を完全予測」「〇〇の全真相」

4. **読者の行動を促す「今すぐ知るべき」型**
   - 「〇〇が動く前に知っておくべきこと」「今週〇〇を買うか判断した理由」

5. **数字を入れると信頼感UP**
   - 「4年で6倍」「-5%の真相」「+30%の根拠」

【禁止タイトル】
- 「今日の投資ニュース速報」系（汎用的すぎてクリックされない）
- 「〜まとめ」「〜解説」だけのシンプルすぎるもの
- 40字超え

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


def select_best_title(titles: list[str], strategy_state: dict = None) -> str:
    """スコアリングで最良タイトルを自動選択（strategy_stateがあれば傾向を反映）"""
    import re

    # strategy_state から高スキパターンを取得
    top_patterns = []
    if strategy_state and strategy_state.get("top_title_patterns"):
        top_patterns = [p.get("pattern", "") for p in strategy_state["top_title_patterns"][:3]]

    def score(title: str) -> float:
        s = 0.0
        if re.search(r"\d", title):          s += 2.0   # 数字あり
        if "？" in title or "?" in title:    s += 1.5   # 疑問形
        if len(title) <= 35:                 s += 1.0   # 適切な長さ
        if "私" in title or "なぜ" in title: s += 1.0   # 一人称・疑問
        keywords = ["米国株", "日本株", "FRB", "AI", "半導体", "ETF", "円", "株", "市場", "Fed",
                    "NVIDIA", "任天堂", "NISA", "利下げ", "利上げ", "円安", "円高"]
        for kw in keywords:
            if kw in title:
                s += 0.5
        # 過去に高スキだったパターンにボーナス
        for pattern in top_patterns:
            if "疑問形" in pattern and "？" in title: s += 1.0
            if "数字" in pattern and re.search(r"\d", title): s += 0.5
            if "逆張り" in pattern and ("なぜ" in title or "実は" in title): s += 1.0
        return s

    return max(titles, key=score)


def main():
    print("=== ⑤ タイトル生成 ===")

    with open("output/article_with_images.json", encoding="utf-8") as f:
        data = json.load(f)

    # strategy_state を読み込んでタイトル選択に活用
    strategy_state = {}
    try:
        state_path = os.path.join(os.path.dirname(__file__), "..", "data", "strategy_state.json")
        with open(state_path, encoding="utf-8") as f:
            strategy_state = json.load(f)
    except Exception:
        pass

    titles = generate_titles(data["article"])
    best_title = select_best_title(titles, strategy_state) if titles else "今日の投資ニュース解説"
    print(f"  選択タイトル: {best_title}")

    result = {
        "title":        best_title,
        "title_options": titles,
        "article":      data["article"],
        "image_paths":  data.get("image_paths", []),
        "cover_path":   data.get("cover_path"),
        "articles":     data["articles"],
    }

    out_path = "output/final.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n保存: {out_path}")
    return result


if __name__ == "__main__":
    main()
