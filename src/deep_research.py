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

    # 上位3本のニュースを選ぶ
    top3 = articles[:3]

    news_block = "\n\n".join(
        f"【ニュース{i+1}】\nソース: {a['source']}\nタイトル: {a['title']}\n概要: {a.get('summary','')[:300]}"
        for i, a in enumerate(top3)
    )

    return f"""あなたは「私」として書く個人投資家ブロガーです。
本日（{today.strftime('%Y年%m月%d日')}）の3つのニュースについて、**投資家向けニュース速報記事**を書いてください。

{news_block}

---

【記事フォーマット（必ずこの通りに出力すること）】

今日のニュース速報｜10秒サマリー
① [ニュース1の要点を1行で。数字を含めること]
② [ニュース2の要点を1行で。数字を含めること]
③ [ニュース3の要点を1行で。数字を含めること]

---

ニュース① [ニュース1の見出し（日本語・30字以内）]

**どんなニュース？**
[400〜600字。「〜によると、」で始める。5W1Hを押さえ、中学生でも分かる言葉で事実を説明する]

**なぜ投資家に重要なの？**
[400〜600字。このニュースが株価・為替・金利・業績にどう波及するか。具体的な銘柄名・ETF名・セクター名を入れる]

**私の見方と投資への活かし方**
[400〜600字。断定推奨は避けつつ、「私なら〜する」「〜を確認してから動く」など具体的行動レベルで]

---

ニュース② [ニュース2の見出し（日本語・30字以内）]

**どんなニュース？**
[400〜600字]

**なぜ投資家に重要なの？**
[400〜600字]

**私の見方と投資への活かし方**
[400〜600字]

---

ニュース③ [ニュース3の見出し（日本語・30字以内）]

**どんなニュース？**
[400〜600字]

**なぜ投資家に重要なの？**
[400〜600字]

**私の見方と投資への活かし方**
[400〜600字]

---

【執筆ルール】
- 口語体かつ知的。「〜なんです」「実は〜」「ここが重要で」「正直〜」など
- 数字は具体的に（「大幅」ではなく「+3.5%」）
- 不確かな情報は「〜と報じられています」「〜とされています」
- 絵文字NG・マークダウン太字（**）は見出しのみ使用
- 「どんなニュース？」「なぜ投資家に重要なの？」「私の見方と投資への活かし方」の見出しは必ず**太字**にすること
- 冒頭の前置き・末尾のまとめ不要。フォーマット通りに本文のみ出力すること"""


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
