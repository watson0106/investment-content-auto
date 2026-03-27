"""
有料記事生成モジュール

無料記事の内容をもとに、具体的な投資アクションプランを提供する有料記事を生成する。
- ペルソナ: GS出身シニアアナリスト級の分析力、ブロガー口調
- 構成: 結論→理由
- 画像なし、100円
"""

from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]


def generate_paid_article(free_article: str, free_title: str) -> dict:
    """無料記事をもとに有料記事を生成する"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""あなたはゴールドマン・サックスで20年以上のキャリアを持つシニアアナリストであり、ウォーレン・バフェットを超えるリターンを出し続けてきた投資家です。ただし、記事は「私」一人称の個人投資家ブロガーとして書きます。

以下の無料記事を読んだ読者向けに、「で、具体的にどうすればいいの？」に答える有料記事を書いてください。

【無料記事タイトル】
{free_title}

【絶対守るルール】

1. 構成は「結論→理由」の順。最初に答えを言い切ってから、根拠を積み上げる
2. 口語体で書く。「なんです」「正直なところ」「ここがミソで」「で、結論なんですが」みたいな口調
3. 箇条書きには「*」を絶対に使わない。「-」も最小限。基本は文章で語る
4. 小タイトル（セクション見出し）は ## で統一し、読者がスクロールしやすくする
5. 「みんなが思いつく一手先の予測」は書かない。「その発想はなかった」と思わせる視点を入れる
   - NG例: 「原油が上がればエネルギー株が上がる」→ 当たり前すぎる
   - OK例: 「この危機の本当の受益者は実は○○で、その理由は...」
6. エビデンスと数値に基づくが、語り口は知的な雑談のように読みやすく
7. AI感のある表現は絶対NG。「まとめると」「以下の通りです」「それでは見ていきましょう」禁止
8. 投資助言ではなく「私個人の分析と判断」として書く
9. 末尾に免責事項を1行で

【記事構成】

## 結論：この局面で私が実際に動かすポジション
（最初の300字で「何を買って何を売るか」を言い切る。理由は後回し。読者が一番知りたいことを最初に）

---

## なぜ「みんなが売ってるとき」に私はこう動くのか
（逆張りの根拠。過去の類似局面のデータ。具体的な数字で裏付ける）

---

## 市場が見落としている「本当の受益者」
（ここが記事の核。誰も言ってないけど論理的に正しい視点。二次的・三次的効果から導き出される意外な恩恵セクターや銘柄）

---

## 具体的なトリガー価格と行動プラン
（「もし○○が○○ドル/円を超えたら→私は○○を○○%売って○○に振り替える。なぜなら...」をセットで。文章で語る）

---

## 今週の私のウォッチリスト
（5つの指標と「この数字がこうなったら動く」という具体的なライン。文章で語る）

---

本記事は筆者個人の分析・見解であり、特定の金融商品の売買を推奨するものではありません。投資判断はご自身の責任で行ってください。

【執筆ルール】
- 全体で8000字以上
- 絵文字NG
- 記事本文のみを出力（前置き不要）
- 最初の文字は「##」で始めること

【無料記事全文（参考）】
{free_article[:8000]}"""

    print("  Gemini で有料記事を執筆中...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.6, max_output_tokens=30000),
    )
    article = response.text.strip()
    print(f"  有料記事生成完了（{len(article)} 文字）")

    title = generate_paid_title(free_title, article[:500])

    return {
        "article": article,
        "title": title,
    }


def generate_paid_title(free_title: str, article_summary: str) -> str:
    """有料記事のタイトルを生成"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""以下の無料記事のタイトルに対応する「有料記事」のタイトルを1つだけ生成してください。

【無料記事タイトル】
{free_title}

【有料記事の内容（冒頭）】
{article_summary}

【ルール】
- 無料記事の読者が「これも読みたい」と思うタイトル
- 「具体的なアクション」「私のポジション」が含まれていることが伝わる
- 40字以内
- タイトルのみ出力（説明不要）"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=100),
        )
        title = response.text.strip().strip('"').strip("'")
        if title and len(title) >= 5:
            print(f"  有料記事タイトル: {title}")
            return title
    except Exception as e:
        print(f"  [WARN] タイトル生成失敗: {e}")

    return f"{free_title}｜私の具体的な投資判断を公開"


def build_free_article_cta(paid_url: str) -> str:
    """無料記事末尾に追加する有料記事への導線テキスト"""
    return f"""

---

## 最後に

本記事では「何が起きているか」を解説しましたが、「じゃあ具体的にどう動くか」は別記事にまとめています。
トリガー価格、セクター別の勝ち負け、私が実際に動かすポジションまで踏み込んでいます。

{paid_url}
"""


def main():
    """有料記事生成のスタンドアロン実行"""
    print("=== 有料記事生成 ===")

    with open("output/polished.json", encoding="utf-8") as f:
        polished = json.load(f)
    with open("output/final.json", encoding="utf-8") as f:
        final = json.load(f)

    free_article = polished.get("polished", "")
    free_title = final.get("title", "")

    result = generate_paid_article(free_article, free_title)

    with open("output/paid_draft.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"保存: output/paid_draft.json")
    return result


if __name__ == "__main__":
    main()
