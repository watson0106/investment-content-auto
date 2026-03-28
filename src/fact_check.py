"""
③ 添削・自動校正
・冒頭テキスト除去・空行圧縮・参照セクション除去
・Geminiによる自動校正（年数ミス・時制ミス・AI感のある表現を修正）
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone, timedelta


JST = timezone(timedelta(hours=9))


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


def auto_proofread(text: str) -> str:
    """Geminiで記事を自動校正（年数ミス・時制矛盾・AI感のある定型表現を修正）"""
    try:
        from google import genai
        from google.genai import types
        GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    except Exception as e:
        print(f"  [WARN] 自動校正スキップ（Gemini未設定）: {e}")
        return text

    today = datetime.now(JST)
    current_year = today.year
    current_month = today.month

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""以下の投資ブログ記事を校正してください。

【現在日時】{today.strftime('%Y年%m月%d日')}（これを基準に全ての時制・年数を判断すること）

【修正すべき典型的な誤り（優先順）】

1. 年数の矛盾
   - 「昨年（{current_year-3}年）」「昨年（{current_year-4}年）」など → 「昨年」は{current_year-1}年のはず。「〇年前（XXXX年）」に修正
   - 「今年（XXXX年）」でXXXXが{current_year}以外 → 「XXXX年に」などに修正
   - 「〇年前」の計算が現在年{current_year}から見て間違っている場合

2. 時制の矛盾
   - 「〇〇年〇月に予定されている」「〇月に発表される」などで、その日付が既に過去になっている場合 → 「〜された」に修正
   - 「現在」「最近」の記述が実際の{current_year}年と矛盾している場合

3. AI感のある定型表現（自然な口語に言い換え）
   - 「〜することが重要です」「〜に注意が必要です」→「〜が大事だと思う」「〜には気をつけたい」
   - 「〜と言えるでしょう」→「〜だと思う」「〜じゃないかな」
   - 「〜が求められます」「〜が必要となります」→「〜しないといけない」「〜が要る」
   - 「〜を踏まえると」「〜を鑑みると」→「〜を考えると」「〜を見ると」
   - 「総じて」「概して」「つまるところ」→自然な口語に

【記事本文】
{text[:9000]}

【出力ルール】
- 修正箇所以外は一切変えないこと（内容・主張・構成・数値は変更禁止）
- 修正が不要な場合は原文をそのまま返す
- 記事本文のみを出力（説明・コメント・前置き一切不要）
- 出力の最初の文字は必ず記事の最初の文字から始めること"""

    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=12000),
        )
        result = resp.text.strip()
        # 極端に短くなった場合は元を使う（安全弁）
        if result and len(result) >= len(text) * 0.7:
            print(f"  自動校正完了（{len(text)} → {len(result)} 文字）")
            return result
        else:
            print(f"  [WARN] 自動校正の出力が短すぎるため原文を使用")
    except Exception as e:
        print(f"  [WARN] 自動校正エラー: {e}")

    return text


def fact_check_and_polish(draft: str, articles: list[dict]) -> str:
    """
    記事の最終クリーンアップ＋自動校正。
    ・冒頭の謎テキスト除去
    ・過剰な空行圧縮
    ・参照セクション除去
    ・年数ミス・時制矛盾・AI定型表現の自動校正
    """
    from deep_research import clean_article
    text = strip_reference_section(draft)
    text = clean_article(text)
    print(f"  クリーンアップ完了（{len(text)} 文字）")

    # 自動校正
    print("  自動校正中（年数ミス・時制矛盾・AI表現チェック）...")
    text = auto_proofread(text)

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
