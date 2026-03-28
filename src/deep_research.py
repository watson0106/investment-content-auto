"""
② 記事執筆（2本）
仕様: note自動投稿パイプライン 運用ルール に準拠
- 2本の記事を2つの独立したトピックで執筆
- 7セクション構成
- 有料マガジンへの誘導
"""

from __future__ import annotations

import json
import os
import re
import subprocess

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MAGAZINE_URL = "https://note.com/kawasewatson0106/m/me3bdb7d529fc"

FIXED_TAGS = ["投資", "株式投資", "資産運用", "米国株", "日本株"]
TOPIC_TAGS_OPTIONS = ["為替", "FRB", "金利", "決算", "マクロ経済", "エネルギー", "半導体", "日銀", "円安", "円高"]


def clean_article(text: str) -> str:
    first_heading = re.search(r'^#{1,3}\s', text, re.MULTILINE)
    if first_heading and first_heading.start() > 0:
        before = text[:first_heading.start()].strip()
        if before and not re.fullmatch(r'[-\s]*', before):
            text = text[first_heading.start():]
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = '\n'.join(line.rstrip() for line in text.split('\n'))
    return text.strip()


def run_claude(prompt: str, model: str = "claude-opus-4-6", timeout: int = 600) -> str:
    """Claude CLIを呼び出してテキストを返す"""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    claude_available = subprocess.run(["which", "claude"], capture_output=True).returncode == 0
    if not claude_available:
        return ""
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text", "--model", model],
        capture_output=True, text=True, timeout=timeout, env=env,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    print(f"  [WARN] Claude CLI 失敗: {result.stderr[:200]}")
    return ""


def run_gemini(prompt: str) -> str:
    """Geminiフォールバック"""
    if not GEMINI_API_KEY:
        return ""
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7, max_output_tokens=16000),
        )
        return response.text or ""
    except Exception as e:
        print(f"  [WARN] Gemini 失敗: {e}")
        return ""


def select_topics(articles: list[dict]) -> tuple[dict, dict]:
    """ニュース一覧から2つの独立したトピックを選定"""
    news_block = "\n".join(
        f"{i+1}. [{a['source']}] {a['title']}"
        for i, a in enumerate(articles[:20])
    )
    prompt = f"""以下のニュース一覧から、今日の日本の個人投資家にとって最も注目度の高い2つのトピックを選定してください。

【選定ルール（必ず守ること）】
- topic1とtopic2は全く異なるテーマ・地域・セクターから選ぶ
- 理想の組み合わせ例：「米国株/マクロ」×「日本株/為替」、「個別銘柄決算」×「地政学リスク」など
- 同じ地域（例：米国×米国）・同じセクター（例：半導体×半導体）の組み合わせは禁止
- 「日本の個人投資家が明日の売買に使える」視点で選ぶ
- タイトルが具体的で記事化しやすいものを優先（「〇〇が報じた」ではなく実際のニュース内容があるもの）

{news_block}

以下のJSON形式のみで回答してください（前置き不要）：
{{
  "topic1": {{"index": <番号>, "title": "<ニュースタイトル>"}},
  "topic2": {{"index": <番号>, "title": "<ニュースタイトル>"}}
}}"""

    text = run_claude(prompt, model="claude-sonnet-4-6", timeout=120)
    if text:
        m = re.search(r'\{[\s\S]+\}', text)
        if m:
            try:
                data = json.loads(m.group(0))
                idx1 = max(0, data["topic1"]["index"] - 1)
                idx2 = max(0, data["topic2"]["index"] - 1)
                return articles[idx1], articles[min(idx2, len(articles)-1)]
            except Exception as e:
                print(f"  [WARN] トピック選定パース失敗: {e}")

    # フォールバック
    return articles[0], articles[min(5, len(articles)-1)]


def build_article_prompt(news: dict) -> str:
    """記事執筆プロンプト"""
    source = news.get('source', 'メディア')
    title_en = news['title']
    summary = news.get('summary', '')[:400]

    return f"""note.com向けの投資解説記事を執筆してください。

【このnoteのコンセプト（執筆方針として内部的に参照すること。記事本文には書かない）】
スイング・デイトレーダーのための朝の必読ニュース。
世界の動きが日本株にどう波及するかを毎朝解説し、情報収集で終わらせず実際の売買に活かす視点を提供する。

【取り上げるニュース】
ソース: {source}
タイトル: {title_en}
概要: {summary}

---

【出力フォーマット（必ず守ること）】
1行目: TITLE: [選定したタイトル]
2行目以降: 記事本文（タイトルを本文中に繰り返さない）
最終行: TOPIC_TAGS: [タグ1],[タグ2]

---

【タイトル選定ルール】
候補を3本考え、以下の基準で1本を選ぶ：
1. 数字を含む（「〇〇円」「〇〇%」「3つの理由」など）
2. 読者の不安または好奇心を刺激するワードを含む
3. 30文字以内
禁止：「〜について」「〜を解説」「〜とは」で終わるタイトル

---

【記事本文構成（必ずこの順番・H2/H3の使い分けで書くこと）】

[リード文（100〜150字）]
冒頭3行で読者を引き込むフック。以下のいずれかのパターンを使うこと：
- 逆説型：「〜と思われているが、実は逆だ」
- 数字型：「〇〇円、〇〇%――この数字が示す本当の意味とは」
- 問い型：「あなたはこのニュースの本質を読めているか」

## {source}が報じたこと

「{source}によると、〜」という書き出しで始め、このニュースの概要を800〜1000字でわかりやすく解説する。
複数の切り口がある場合は以下のように H3 で区切る：

### [切り口1の見出し]
（本文を段落で展開）

### [切り口2の見出し]
（本文を段落で展開）

## [筆者の結論をそのままH2見出しにする。例：「この上昇は3ヶ月以内に反転すると考える理由」]

結論をH2見出しに入れ、その根拠を1200〜1500字で展開する。
複数の観点は H3 で区切る：

### [観点1の見出し]
### [観点2の見出し]

## 行動の考え方

600〜800字。断定推奨禁止。複数パターンは H3 で区切る。

## このニュースで注目すべき銘柄

このニュースの影響を最も受けるセクターを特定し、売買代金上位の代表銘柄を1〜2銘柄取り上げる。
銘柄ごとに以下の形式で書く：

### [銘柄名（証券コード or ティッカー）]

- 本日の株価（土日の場合は「週明けの注目水準：〇〇円前後」）
- このニュースとこの銘柄の因果関係を明確に記述する

【銘柄分析の質の基準】
「影響がありそう」という表面的な記述は禁止。
以下の問いに答える形で分析を書くこと：
1. 今日このニュースがこの銘柄に与える最も直接的な影響は何か？
2. その影響は株価にどう波及するか？（需給・業績・センチメントのいずれのルートか）
3. 短期的（当日〜1週間）に株価がどう動きやすいか、客観的なエビデンス（過去の類似相場・相関データ・空売り比率・オプションのPCRなど）を根拠として示す

【分析例の水準（参考）】
「三菱商事×原油高」の場合：「影響があります」ではなく——
「中東情勢の長期化観測が強まれば、原油の供給制約は構造的なものとなる。三菱商事の資源セグメント利益は原油1バレルあたりの単価と相関が高く、WTIが80ドル台から90ドルに上昇した場合の増益幅は過去のIR資料から試算できる。加えて、同社の空売り比率が直近で〇%程度と低水準にあることから、買い圧力に対する需給抵抗は小さい。週明けのギャップアップ後、〇〇円〜〇〇円ゾーンが上値の節目として意識されやすい」——このレベルの具体性を目指す。

この銘柄セクションの末尾に、以下の構成で有料マガジンへの誘導文を自然につなげる：

---

（記事の論旨に合わせた1〜2段落の誘導文。以下は構成の参考）

「この銘柄に注目できたとして、それだけでは利益にならない。同じ情報を見ている参加者は無数にいる。差がつくのはエントリータイミングと損切り・利確の設計だ。」

「そのための具体的な判断軸を毎週まとめているのが以下の有料マガジンだ。読み流す情報ではなく、明日の売買に使える視点だけを届けている。」

{MAGAZINE_URL}

（※URLは単独の行に置くこと。note の埋め込みカードとして表示される）

---

【トピックタグ選定】
以下のリストから最も関連する2つを選ぶ：
為替 / FRB / 金利 / 決算 / マクロ経済 / エネルギー / 半導体 / 日銀 / 円安 / 円高
→ 最終行に「TOPIC_TAGS: タグ1,タグ2」の形式で出力

---

【執筆ルール】
- 目標文字数：5000字程度
- 対象読者：スイング・デイトレーダー（売買に使える視点を求めている）
- 文体：ブロガー口調（断定的すぎず、読者と対話する感覚）
- 個人プロフィール（投資歴〇年・〇代など）は一切記載しない
- H2 はセクションの大見出し、H3 はセクション内の小見出しとして使い分ける
- 改行・空行は意味のまとまりで自然に入れる（1文ごとの機械的な改行は禁止）
- 段落は3〜5文を目安にまとめる
- 太字は重要なキーワードのみに限定する
- 絵文字は使用禁止（URLの前後も含めて）
- 数字は徹底的に具体的に（「大幅」ではなく「+3.5%」）
- タイムリーな数値は「〜と報じられています」「〜とされています」と表現
- 「おわりに」という見出しは使わない。銘柄セクション末尾から自然に誘導文につなげる
- 記事本文のみ出力（前置き・後記・加筆まとめ不要）"""


def write_article(news: dict, article_num: int) -> dict:
    """1本の記事を執筆して返す"""
    prompt = build_article_prompt(news)

    print(f"  Claude CLI で記事{article_num}執筆中...")
    draft = run_claude(prompt, model="claude-opus-4-6", timeout=600)

    if not draft:
        print(f"  Gemini で記事{article_num}執筆中（フォールバック）...")
        draft = run_gemini(prompt)

    if not draft:
        raise RuntimeError(f"記事{article_num}の執筆に失敗しました")

    print(f"  執筆完了（{len(draft)} 文字）")

    # TITLE: 抽出
    title = ""
    title_match = re.search(r'^TITLE:\s*(.+)$', draft, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
        draft = re.sub(r'^TITLE:\s*.+\n?', '', draft, count=1, flags=re.MULTILINE).strip()

    # TOPIC_TAGS: 抽出
    topic_tags = []
    tags_match = re.search(r'TOPIC_TAGS:\s*(.+)$', draft, re.MULTILINE)
    if tags_match:
        topic_tags = [t.strip() for t in tags_match.group(1).split(',')][:2]
        draft = re.sub(r'TOPIC_TAGS:\s*.+$', '', draft, flags=re.MULTILINE).strip()

    # 4000字未満なら補強
    if len(draft) < 4000:
        print(f"  [WARN] 記事{article_num}が{len(draft)}文字（4000字未満）→ 補強中...")
        source = news.get('source', 'メディア')

        if len(draft) >= 1500:
            # 既存の記事を展開（構成・主張は変えずに加筆）
            supplement_prompt = f"""以下の投資記事を加筆して5000字程度にしてください。

【加筆ルール】
- 現在の記事の内容・構成・主張は一切変えない
- 各セクションに根拠・データ・事例を追記して文字数を増やす
- 「このニュースで注目すべき銘柄」の銘柄分析に具体的な株価水準・過去の相関・需給データを追加
- 「おわりに」「今週の注目指標」見出し禁止
- コメント・まとめ・前置き不要。加筆後の記事全文のみ出力

【現在の記事（{len(draft)}文字）】
{draft}"""
            supplement = run_claude(supplement_prompt, model="claude-opus-4-6", timeout=300)
        else:
            # 極端に短い場合は完全再生成
            news_title = news.get('title', '')
            news_summary = news.get('summary', '')
            supplement_prompt = f"""以下のニュースを題材に、投資ブログ記事を5000字程度で執筆してください。

【ニュース】
ソース: {source}
タイトル: {news_title}
概要: {news_summary}

【出力ルール】
- 1行目: TITLE: [記事タイトル]（ニュースの核心を突いた逆説/数字/問い型の30字以内）
- 本文: リード文 → ## {source}が報じたこと → ## [結論をそのままH2見出しに] → ## 行動の考え方 → ## このニュースで注目すべき銘柄
- 「## {source}が報じたこと」は「{source}によると、」という書き出しで800〜1000字
- 銘柄セクション末尾に有料マガジン誘導文を入れ、最後の行に単独で次のURLを置く：
{MAGAZINE_URL}
- 末尾: TOPIC_TAGS: タグ1,タグ2（為替/FRB/金利/決算/マクロ経済/エネルギー/半導体/日銀/円安/円高 から2つ）
- 「おわりに」「今週の注目指標」見出し禁止・絵文字禁止
- コメント・まとめ・前置き不要。記事本文のみ出力"""
            supplement = run_claude(supplement_prompt, model="claude-opus-4-6", timeout=300)
            if supplement:
                s_title_match = re.search(r'^TITLE:\s*(.+)$', supplement, re.MULTILINE)
                if s_title_match and not title:
                    title = s_title_match.group(1).strip()
                    supplement = re.sub(r'^TITLE:\s*.+\n?', '', supplement, count=1, flags=re.MULTILINE).strip()
                s_tags_match = re.search(r'TOPIC_TAGS:\s*(.+)$', supplement, re.MULTILINE)
                if s_tags_match and not topic_tags:
                    topic_tags = [t.strip() for t in s_tags_match.group(1).split(',')][:2]
                    supplement = re.sub(r'TOPIC_TAGS:\s*.+$', '', supplement, flags=re.MULTILINE).strip()

        if supplement:
            expanded = clean_article(supplement)
            # 補強後が元より長い場合のみ採用
            if len(expanded) > len(draft):
                draft = expanded
            print(f"  補強後: {len(draft)} 文字")

    draft = clean_article(draft)

    # タイトルが抽出できなかった場合は本文H2から取得
    if not title:
        first_h2 = re.search(r'^##\s+(.+)$', draft, re.MULTILINE)
        if first_h2:
            title = first_h2.group(1).strip()
        else:
            title = news['title'][:30]

    all_tags = FIXED_TAGS + topic_tags

    return {
        "title": title,
        "article": draft,
        "tags": all_tags,
        "topic_tags": topic_tags,
        "source_news": news,
        "image_paths": [],
        "cover_path": None,
    }


def main():
    print("=== ② 記事執筆（2本） ===")

    with open("output/collected_news.json", encoding="utf-8") as f:
        articles = json.load(f)

    # 2トピック選定
    print("  トピック選定中...")
    news1, news2 = select_topics(articles)
    print(f"  記事1トピック: {news1['title']}")
    print(f"  記事2トピック: {news2['title']}")

    os.makedirs("output", exist_ok=True)

    # 記事1執筆
    print(f"\n  --- 記事1執筆 ---")
    article1 = write_article(news1, 1)
    with open("output/article_1.json", "w", encoding="utf-8") as f:
        json.dump(article1, f, ensure_ascii=False, indent=2)
    print(f"  保存: output/article_1.json  タイトル: {article1['title']}")

    # 記事2執筆
    print(f"\n  --- 記事2執筆 ---")
    article2 = write_article(news2, 2)
    with open("output/article_2.json", "w", encoding="utf-8") as f:
        json.dump(article2, f, ensure_ascii=False, indent=2)
    print(f"  保存: output/article_2.json  タイトル: {article2['title']}")

    # 後方互換: draft.json / final.json
    with open("output/draft.json", "w", encoding="utf-8") as f:
        json.dump({"draft": article1["article"], "articles": [news1]}, f, ensure_ascii=False, indent=2)
    with open("output/polished.json", "w", encoding="utf-8") as f:
        json.dump({"polished": article1["article"]}, f, ensure_ascii=False, indent=2)
    with open("output/final.json", "w", encoding="utf-8") as f:
        json.dump(article1, f, ensure_ascii=False, indent=2)

    return {"article_1": article1, "article_2": article2}


if __name__ == "__main__":
    main()
