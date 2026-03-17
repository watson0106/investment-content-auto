"""
③ Claude CLI で添削・肉付け
Gemini ドラフトを Claude CLI 経由でファクトチェック・文体調整する（APIキー不要）
"""

from __future__ import annotations


import json
import os
import subprocess
import tempfile


def fact_check_and_polish(draft: str, articles: list[dict]) -> str:
    """Claude CLI でファクトチェック・添削"""
    sources_text = "\n".join(f"- {a['url']}" for a in articles if a.get("url"))

    prompt = f"""以下はAIが生成した投資解説記事のドラフトです。

【ドラフト】
{draft}

【参照ソース】
{sources_text}

以下の観点で記事を改善してください：

1. **ファクトチェック**
   - 数値・パーセンテージ・固有名詞が正確か確認
   - 不確かな情報には「〜とされる」「〜と報じられている」などの表現を使う
   - 明らかに誤っている情報は削除または修正する

2. **論理整合性**
   - 前後の矛盾を修正する
   - 因果関係が不明確な箇所を補強する

3. **文体・読みやすさ（note読者向け）**
   - 難しい専門用語には括弧で補足を加える
   - 段落を適切に区切り、読みやすくする
   - 投資初心者〜中級者が読んで理解できる文体にする
   - 「です・ます」調で統一する

4. **構成の補完**
   - 不足している視点（リスク・反対意見・代替シナリオ）を追加する
   - 読者が「次に何をすべきか」が分かるよう具体的なアクションを含める

改善後の記事本文のみを出力してください（コメントや説明は不要）。"""

    # Claude CLI が使えるか確認
    claude_available = subprocess.run(
        ["which", "claude"], capture_output=True
    ).returncode == 0

    if claude_available:
        print("  Claude CLI で添削・肉付け中...")
        # CLAUDECODE 環境変数を unset してネスト起動エラーを回避
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=120, env=env
        )
        if result.returncode == 0 and result.stdout.strip():
            polished = result.stdout.strip()
            print(f"  添削完了（{len(polished)} 文字）")
            return polished
        print("  [WARN] Claude CLI 失敗。Gemini にフォールバック")

    # Gemini フォールバック
    from google import genai
    from google.genai import types
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    print("  Gemini で添削・肉付け中...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.5, max_output_tokens=4096),
    )
    polished = response.text
    print(f"  添削完了（{len(polished)} 文字）")
    return polished


def main():
    print("=== ③ Claude API 添削 ===")

    with open("output/draft.json", encoding="utf-8") as f:
        data = json.load(f)

    polished = fact_check_and_polish(data["draft"], data["articles"])

    result = {
        "polished": polished,
        "articles": data["articles"],
    }

    out_path = "output/polished.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"保存: {out_path}")
    print("\n--- 添削後冒頭 ---")
    print(polished[:300])
    return result


if __name__ == "__main__":
    main()
