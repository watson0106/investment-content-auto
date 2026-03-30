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
    if strategy_state is None:
        strategy_state = load_strategy_state()

    news_block = "\n".join(
        f"- [{a['source']}] {a['title']}\n  {a['summary'][:200]}\n  URL: {a['url']}"
        for a in articles
    )
    history_block = (
        f"\n【過去に書いたテーマ（重複禁止）】\n{history_summary}\n"
        if history_summary and history_summary != "（過去記事なし）"
        else ""
    )
    strategy_block = build_strategy_block(strategy_state)

    return f"""あなたは「私」として書く個人投資家ブロガーです。
以下のニュース一覧から、**最も深掘りする価値がある1つのテーマ（銘柄・マクロ・セクター）**を選び、
note.com 向けの**保存版・深掘り分析記事**を一人称で書いてください。

「3つのニュースを並べて紹介する速報記事」ではなく、
「1つのテーマを徹底解剖し、読者が明日すぐ行動できるレベルの洞察を提供する記事」を書くこと。
{history_block}{strategy_block}
【本日のニュース一覧（この中から最も深掘り価値があるテーマを1つ選ぶ）】
{news_block}

【記事構成（必ずこの順番・形式で書くこと）】

## 結論：〔テーマ名〕は今、〔買い/売り/様子見〕だと私が考える理由
（200字程度。記事の結論を冒頭に置く。「なぜなら〜」「具体的には〜」で理由を2つ示す。
読者が最初の2秒でこの記事を読む価値があると判断できるレベルの密度で書く）

---

## そもそも何が起きているのか
（400字程度。今このテーマが動いている背景。数字を必ず入れる。
「この1週間で〇〇が〇%動いた」「〇〇社の決算で〇〇億円の〇〇」など具体的な事実から入る）

---

## なぜ今これが重要なのか──私が見ている「本質」
（600字程度。主流メディアとは異なる切り口を1つ以上含める。
「表向きは〇〇と報じられているが、私が本当に注目しているのは〇〇だ」という構造。
歴史的文脈・構造的背景・業界のインセンティブ構造などを使って深掘りする）

---

## チャートと数字で読む現在地
（400字程度。具体的な数値・比率・過去比較を使って現状を整理。
「現在のPERは〇倍で過去5年平均〇倍に対して〇%〇〇」
「〇年〇月以来の〇〇水準」などの表現を積極的に使う）

---

## 私の見立て：強気・中立・弱気の3シナリオ
（600字程度。3つのシナリオをそれぞれ箇条書きではなく文章で。
「もし〇〇が起きれば、私は〇〇を〇〇する。なぜなら〜」
各シナリオに発動条件（数値）を必ず入れる）

---

## 私が今週実際に確認すること
（200字程度。具体的なチェックポイントを3〜5個。
「〇〇の株価が〇〇円を割り込むかどうか」「〇〇日発表の〇〇指標」など行動レベルで）

---

## まとめ：この記事の3行要約
（箇条書き3行。保存して後で読み返せる密度で。
各行に必ず数字か固有名詞を入れる）

{build_cta_block()}

【執筆ルール】
- 全体で6000字以上
- 主語は必ず「私」。「投資家全般」「多くの人」という三人称NG
- 口語体かつ知的。「〜なんです」「正直〜」「実は〜」「ここが重要で」など
- 専門用語は必ず括弧で補足
- 数字は徹底的に具体的に（「大幅」ではなく「+3.5%」）
- タイムリーな数値は「〜と報じられています」「〜とされています」と表現
- 「保存版」「完全解説」「私の判断」が読者に伝わる密度を意識すること
- AI感・テンプレ感のある表現NG。「まず〜」「次に〜」「結論として〜」の機械的構成NG
- 絵文字NG

【出力ルール】
- 記事本文のみを出力すること
- 冒頭に前置き・紹介文を絶対に入れないこと
- 末尾に参照・ソース・出典セクションを入れないこと
- 最初の文字は必ず「## 結論：」で始めること"""


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
