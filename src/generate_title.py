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
    # strategy_state から直近の高スキタイトルを取得してプロンプトに反映
    high_like_examples = ""
    if strategy_state:
        # パフォーマンスデータから直近スキ3以上のタイトルを取得
        try:
            import json as _json
            perf_path = os.path.join(os.path.dirname(__file__), "..", "data", "article_performance.json")
            with open(perf_path, encoding="utf-8") as _f:
                perf_data = _json.load(_f)
            top_titles = [
                d["title"] for d in sorted(perf_data, key=lambda x: x.get("latest_likes",0), reverse=True)
                if d.get("latest_likes",0) >= 3
            ][:5]
            if top_titles:
                high_like_examples = "
".join(f"- {t}" for t in top_titles)
        except Exception:
            pass

    prompt = f"""以下の投資記事に対して、note.com でクリック・保存されるタイトルを10案生成してください。
記事ごとにタイプを変えることが重要です（同じパターンを繰り返さない）。

【記事冒頭（参考）】
{article_text[:1500]}

【過去に実際に多くのスキを獲得したタイトル（この感覚を参考にする）】
{high_like_examples if high_like_examples else "- サンリオ株が4年で6倍になった理由と、次に来る爆上げ材料
- 【保存版】エントリーしてはいけない水準
- Googleは次の10年も覇権を握れるか？"}

【今回生成する10案の内訳（必ずこの比率で）】

■ A型「長期ストーリー・大きな問い」（3案）
- 「〇〇は次の10年も覇権を握れるか？」
- 「〇〇が5年で化ける、たった1つの理由」
- 「なぜ誰も言わないのか──〇〇の本当の実力」

■ B型「保存版・手法・教訓」（2案）
- 「【保存版】〇〇を買う前に知っておくべきこと」
- 「私が〇〇で失敗した理由と、今なら絶対やること」

■ C型「逆張り・意外性・否定」（2案）
- 「〇〇は終わった、と言う人に反論する」
- 「〇〇が急落しても、私が売らない理由」
- 「〇〇の逆襲──本当の上昇はこれからだ」

■ D型「数字・具体的根拠」（2案）
- 「〇〇が6倍になった4つの条件、今の株価に全部揃っている」
- 「〇〇は2週間以内に動く、その根拠を示す」

■ E型「疑問形＋数字」（1案）
- 「〇〇、今が買い時？──3つの指標で判断する」

【禁止パターン（使わないこと）】
- 「なぜ〇〇株は急伸/急落したのか？」→ このパターンは使い古されているため禁止
- 「〇〇株が急騰した裏事情」→ 同様に禁止
- 「今日の投資ニュース速報」系
- 40字超え

【重要】銘柄名・企業名・固有名詞を必ず入れること。「投資」だけの汎用タイトルは禁止。

【出力形式】
1. タイトル案1
2. タイトル案2
...
10. タイトル案10

タイトル候補のみを出力してください。"""

    # Claude CLI が使えるか確認
    import shutil
    claude_path = shutil.which("claude")

    text = ""
    if claude_path:
        print("  Claude CLI でタイトル生成中...")
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            [claude_path, "-p", prompt, "--output-format", "text", "--allowedTools", "none"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, env=env
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

    # 番号付きリスト or テーブル形式をパース
    import re
    titles = []
    for line in lines:
        title = None
        # "1. タイトル" 形式
        m = re.match(r"^\d+[\.\)]\s*(.+)$", line)
        if m:
            title = m.group(1).strip()
        # "| 1 | タイトル | 説明 |" テーブル形式
        elif "|" in line:
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= 2 and re.match(r"^\d+$", cells[0]):
                title = cells[1]  # 2番目のセルがタイトル
            elif len(cells) >= 2 and re.match(r"^-+$", cells[0]):
                continue  # テーブルヘッダー区切り行をスキップ
        # ヘッダー行・説明行・区切り線はスキップ
        if title:
            # Markdown太字(**...**)を除去
            title = re.sub(r"\*\*(.+?)\*\*", r"\1", title)
            # 先頭の【】日付タグはそのまま残す
            title = title.strip()
            if title and len(title) >= 5 and not title.startswith("#") and not re.match(r"^[-=|]+$", title):
                titles.append(title)

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
        if "私" in title:                    s += 2.0   # 一人称（強い）
        keywords = ["米国株", "日本株", "FRB", "AI", "半導体", "ETF", "円", "株", "市場", "Fed",
                    "NVIDIA", "任天堂", "NISA", "利下げ", "利上げ", "円安", "円高"]
        for kw in keywords:
            if kw in title:
                s += 0.5
        # 高スキパターンにボーナス
        high_like_patterns = ["保存版", "本当の理由", "たった1つ", "卒業", "逆襲", "正体", "治す", "結論"]
        for pat in high_like_patterns:
            if pat in title:
                s += 2.0
        # 「急伸」「急騰」「急落」パターンはペナルティ（使い古されている）
        stale_patterns = ["急伸したのか", "急騰したのか", "急落したのか", "急伸した理由", "急騰した理由"]
        for pat in stale_patterns:
            if pat in title:
                s -= 3.0
        # 過去に高スキだったパターンにボーナス
        for pattern in top_patterns:
            if "疑問形" in pattern and "？" in title: s += 1.0
            if "数字" in pattern and re.search(r"\d", title): s += 0.5
            if "逆張り" in pattern and ("なぜ" in title or "実は" in title): s += 1.0
        return s

    return max(titles, key=score)


def main():
    print("=== ⑤ タイトル生成 ===")

    # polished.json を読む（画像生成ステップは廃止）
    with open("output/polished.json", encoding="utf-8") as f:
        data = json.load(f)
    # polished.json は "polished" キーに本文がある
    if "polished" in data and "article" not in data:
        data["article"] = data["polished"]

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
        "image_paths":  [],
        "cover_path":   None,
        "articles":     data.get("articles", []),
    }

    out_path = "output/final.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n保存: {out_path}")
    return result


if __name__ == "__main__":
    main()
