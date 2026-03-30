"""
② Claude で記事執筆
収集したニュースを Claude CLI で直接記事に仕上げる。
"""

from __future__ import annotations

import json
import os
import re
import subprocess


def clean_article(text: str) -> str:
    """
    記事テキストの後処理:
    - 冒頭の謎の紹介文（## 見出しより前の地の文）を除去
    - 3行以上連続する空行を最大1行に圧縮
    """
    # 冒頭の謎テキスト除去: 最初の ## 見出しより前にある文章を削除
    first_heading = re.search(r'^#{1,3}\s', text, re.MULTILINE)
    if first_heading and first_heading.start() > 0:
        before = text[:first_heading.start()].strip()
        # 短い区切り線（---）だけなら消す、長い前置き文章なら消す
        if before and not re.fullmatch(r'[-\s]*', before):
            text = text[first_heading.start():]

    # 3行以上の連続空行 → 1行に圧縮
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 行末の余分なスペースを除去
    text = '\n'.join(line.rstrip() for line in text.split('\n'))

    return text.strip()


def load_strategy_state() -> dict:
    """data/strategy_state.json を読み込む（なければデフォルト値）"""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "strategy_state.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def build_strategy_block(state: dict) -> str:
    """strategy_state.json から記事執筆ヒントを生成"""
    if not state:
        return ""
    lines = ["\n【過去に読まれた記事の傾向（参考にすること）】"]
    if state.get("top_topics"):
        topics = "、".join(t["topic"] for t in state["top_topics"][:3])
        lines.append(f"- スキを集めたトピック：{topics}")
    if state.get("recommended_title_style"):
        lines.append(f"- 効果的なタイトルパターン：{state['recommended_title_style']}")
    if state.get("avoid_topics"):
        avoid = "、".join(state["avoid_topics"][:2])
        lines.append(f"- 反応が薄かったトピック（なるべく避ける）：{avoid}")
    return "\n".join(lines) + "\n"


def build_cta_block() -> str:
    """全記事末尾に挿入するCTA（有料記事・マガジンへの導線）"""
    return """

---

## 続きは有料記事で

この記事で触れた銘柄・テーマについて、**私が実際に取るポジションと具体的な売買タイミング**は有料記事で公開しています。

- 「どの価格で買うか」「損切りラインはどこか」「目標株価はいくらか」
- 楽観・中立・悲観の3シナリオと、各シナリオで私がどう動くか

▶ [今週の有料記事（¥500）を見る](https://note.com/kawasewatson0106)

毎週火・金曜日に更新中。購入者限定で、私のポートフォリオの現在地も公開しています。"""


def build_prompt(articles: list[dict], history_summary: str = "", strategy_state: dict = None) -> str:
    import datetime
    JST = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(JST)

    # 上位2本のニュースを選ぶ
    top2 = articles[:2]

    news_block = "\n\n".join(
        f"【ニュース{i+1}】\nソース: {a['source']}\nタイトル: {a['title']}\n概要: {a.get('summary','')[:400]}"
        for i, a in enumerate(top2)
    )

    cta_text = "情報を正確に理解することは、投資の第一歩に過ぎない。株価は常に「情報の一歩先」を織り込んで動いており、ニュースを読むだけでは勝てないのが相場の現実だ。毎週の注目銘柄・具体的な売買シナリオ・エントリー根拠まで踏み込んで解説する有料マガジンはこちら。「知っている」を「稼げる」に変えたい方はぜひ。"

    return f"""あなたは「私」として書く個人投資家ブロガーです。
本日（{today.strftime('%Y年%m月%d日')}）の2つのニュースについて、**投資家向けニュース速報記事**を書いてください。

{news_block}

---

【記事フォーマット（必ずこの通りに出力すること）】

今日のニュース速報｜10秒サマリー
① [ニュース1の要点を1行で。数字を含めること。「〜が〜した」と事実を断言する形で]
② [ニュース2の要点を1行で。数字を含めること。「〜が〜した」と事実を断言する形で]

---

# ①[ソース名]が報じたこと
[「[ソース名]によると、」で始める。具体的な数字・変動率・規模を含む300〜400字の事実段落。見出しなしで直接本文から始める]
## [このニュースを理解する構造的な視点1（例：「ドル買いを呼ぶメカニズム」「介入ハードルが高い理由」）]
[300〜400字で説明]
## [視点2（別の切り口、背景・構造・波及効果など）]
[300〜400字で説明]
## [視点3（もう1つの視点、必要に応じて。1つ目と2つ目とは異なる切り口で）]
[300〜400字で説明]
# [ニュース内容に即した社説タイトル（例：「160円は通過点に過ぎないと私は見ている」「JX金属の投資拡大は構造的成長の入り口だ」）。「私の意見」「社説」という言葉は使わない]
[「私はこう見ている」という一人称で500〜700字。断定形。具体的なシナリオ・数字で締める]
# このニュースで注目すべき銘柄
銘柄名：[銘柄名（ティッカーまたは証券コード）]
本日の株価：[直近株価と説明。例：3,193円（直近終値）]
__CHART_0__
[なぜこの銘柄が注目されるか300〜500字。短期値動きシナリオ（具体的な株価・出来高の数字）を含める]
---
# ②[ソース名]が報じたこと
[「[ソース名]によると、」で始める300〜400字の事実段落]
## [視点1]
[300〜400字]
## [視点2]
[300〜400字]
## [視点3]
[300〜400字]
# [ニュース2の社説タイトル]
[500〜700字]
# このニュースで注目すべき銘柄
銘柄名：[銘柄名（ティッカーまたは証券コード）]
本日の株価：[直近株価と説明]
__CHART_1__
[300〜500字。短期値動きシナリオ含む]

---

{cta_text}

__MAGAZINE_EMBED__

---

【絶対ルール（違反したら書き直し）】
- 絵文字は使用禁止
- 「おそらく」「推測される」「〜と思われる」「〜かもしれない」は使用禁止
- 「私はこう見ている」という一人称を判断の表明として使う（言い訳に使わない）
- 試算数字には必ず計算式か前提条件を1行添える
- 数字は具体的に（「大幅」ではなく「+3.5%」）
- 不確かな情報は「〜と報じられています」「〜とされています」と出典を明記する
- マークダウンの `#`（H1）と `##`（H2）は見出しのみ使用。インライン太字（**）は使用禁止
- 冒頭の前置き・末尾のまとめ不要。フォーマット通りに本文のみ出力すること
- 口語体かつ知的。「〜なんです」「実は〜」「ここが重要で」「正直〜」など
- H1の①②ソースセクション直下は見出しなしで本文から直接始めること（「## 数字で見る」などの固定見出しは使わない）
- H2のサブ見出しはそのニュースの内容に即した具体的なタイトルにすること"""


def run_deep_research(articles: list[dict], history_summary: str = "") -> dict:
    """Claude CLI で記事を執筆する"""
    prompt = build_prompt(articles, history_summary=history_summary)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    print("  Claude CLI で記事執筆中...")
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text", "--model", "claude-opus-4-6"],
        capture_output=True, text=True, timeout=600, env=env,
    )
    if result.returncode == 0 and result.stdout.strip():
        draft = result.stdout.strip()
        print(f"  Claude 執筆完了（{len(draft)} 文字）")
    else:
        raise RuntimeError(f"Claude CLI 失敗: {result.stderr[:300]}")

    draft = clean_article(draft)
    return {"draft": draft, "articles": articles}


def main():
    print("=== ② Claude 記事執筆 ===")

    with open("output/collected_news.json", encoding="utf-8") as f:
        articles = json.load(f)

    from article_history import load_history, build_history_summary
    history_summary = build_history_summary(load_history())
    result = run_deep_research(articles, history_summary=history_summary)

    os.makedirs("output", exist_ok=True)
    with open("output/draft.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("保存: output/draft.json")
    print("\n--- 記事冒頭 ---")
    print(result["draft"][:300])
    return result


if __name__ == "__main__":
    main()
