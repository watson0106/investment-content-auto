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

以下の観点で記事を改善してください（構成は変えずに磨く）：

1. **文体**
   - 口語体・ブログ調を維持。「〜なんです」「〜ですよね」「実は〜」を適度に使う
   - 一文を短く。長い文は分割する
   - 絵文字は使わない

2. **各ニュースの「私の見方と投資への活かし方」セクション**
   - 「私は〜と思う」「個人的には〜」の一人称で書く
   - 具体的なETF名・銘柄名・セクター名を必ず1つ以上挙げる
   - 「買い」「売り」の断言はせず、「〜に注目したい」「〜を意識したい」という表現にする

3. **ファクトチェック**
   - 数値・固有名詞が正確か確認
   - 不確かな情報は「〜と報じられています」「〜とされています」と表現

4. **文字数**
   - 全体で必ず5000文字以上。各ニュースのセクションを十分に掘り下げる

改善後の記事本文のみを出力してください（説明・コメント不要）。"""

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
            capture_output=True, text=True, timeout=300, env=env
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
        config=types.GenerateContentConfig(temperature=0.5, max_output_tokens=16000),
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
