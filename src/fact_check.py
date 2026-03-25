"""
③ Claude CLI で添削・肉付け
Gemini ドラフトを Claude CLI 経由でファクトチェック・文体調整する（APIキー不要）
"""

from __future__ import annotations


import json
import os
import subprocess
import tempfile


import re


def strip_reference_section(text: str) -> str:
    """末尾の参照ソースセクションを除去する"""
    patterns = [
        r"\n+#{1,3}\s*(参照|ソース|出典|References?|Sources?|参考文献|参考ソース)[^\n]*\n.*$",
        r"\n+\*{0,2}(参照|ソース|出典|References?|Sources?)\*{0,2}[：:][^\n]*\n.*$",
        r"\n+---+\s*\n(参照|ソース|出典).*$",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.rstrip()


def fact_check_and_polish(draft: str, articles: list[dict]) -> str:
    """
    Claude が執筆した記事の最終クリーンアップ。
    ・冒頭の謎テキスト除去
    ・過剰な空行圧縮
    ・参照セクション除去
    記事の内容は変えない（Claudeがすでに書いているため全文書き直し不要）。
    """
    # deep_research.py と同じ clean_article を適用
    from deep_research import clean_article
    text = strip_reference_section(draft)
    text = clean_article(text)
    print(f"  クリーンアップ完了（{len(text)} 文字）")
    return text


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
