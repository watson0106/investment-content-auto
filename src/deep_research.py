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
import datetime

MAGAZINE_URL = "https://note.com/kawasewatson0106/m/me3bdb7d529fc"
JST = datetime.timezone(datetime.timedelta(hours=9))

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
    # cronはPATHが最小限のため絶対パスを優先して探す
    claude_cmd = None
    for candidate in ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"]:
        if os.path.exists(candidate):
            claude_cmd = candidate
            break
    if claude_cmd is None:
        result = subprocess.run(["which", "claude"], capture_output=True, text=True)
        claude_cmd = result.stdout.strip() if result.returncode == 0 else None
    if not claude_cmd:
        print("  [WARN] Claude CLI が見つかりません")
        return ""
    result = subprocess.run(
        [claude_cmd, "-p", prompt, "--output-format", "text", "--model", model],
        capture_output=True, text=True, timeout=timeout, env=env,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    print(f"  [WARN] Claude CLI 失敗: {result.stderr[:200]}")
    return ""



def get_realtime_price(code: str, is_jp: bool = True) -> str | None:
    """yfinanceでリアルタイム株価を取得して文字列で返す"""
    try:
        import yfinance as yf
        ticker_str = f"{code}.T" if is_jp else code
        ticker = yf.Ticker(ticker_str)
        hist = ticker.history(period="2d")
        if hist.empty:
            return None
        price = hist["Close"].iloc[-1]
        if is_jp:
            return f"{price:,.0f}円"
        else:
            return f"${price:,.2f}"
    except Exception as e:
        print(f"  [WARN] 株価取得失敗 {code}: {e}")
        return None


def generate_stock_chart(code: str, is_jp: bool = True) -> str | None:
    """1ヶ月の株価チャートを生成してPNGパスを返す"""
    try:
        import yfinance as yf
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        plt.rcParams['font.family'] = ['Hiragino Sans', 'Hiragino Maru Gothic Pro', 'sans-serif']

        ticker_str = f"{code}.T" if is_jp else code
        df = yf.Ticker(ticker_str).history(period="1mo")
        if df.empty or len(df) < 5:
            return None

        os.makedirs("output/charts", exist_ok=True)

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(10, 5.5),
            gridspec_kw={'height_ratios': [3, 1]},
            facecolor='#1a1a2e'
        )

        ax1.plot(df.index, df['Close'], color='#00d4ff', linewidth=2, label='終値')
        if len(df) >= 5:
            ax1.plot(df.index, df['Close'].rolling(5).mean(),
                     color='#ffa500', linewidth=1, linestyle='--', label='MA5', alpha=0.8)
        if len(df) >= 20:
            ax1.plot(df.index, df['Close'].rolling(20).mean(),
                     color='#ff69b4', linewidth=1, linestyle='--', label='MA20', alpha=0.8)

        ax1.set_facecolor('#1a1a2e')
        ax1.tick_params(colors='#aaaaaa', labelsize=8)
        for spine in ax1.spines.values():
            spine.set_color('#333355')
        ax1.legend(loc='upper left', fontsize=7, facecolor='#1a1a2e', labelcolor='white', framealpha=0.5)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=0)

        bar_colors = ['#ff4444' if c < o else '#44cc66'
                      for c, o in zip(df['Close'], df['Open'])]
        ax2.bar(df.index, df['Volume'], color=bar_colors, alpha=0.7)
        ax2.set_facecolor('#1a1a2e')
        ax2.tick_params(colors='#aaaaaa', labelsize=7)
        for spine in ax2.spines.values():
            spine.set_color('#333355')
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))

        label = f"{code}（東証）" if is_jp else code
        fig.suptitle(f"{label}  直近1ヶ月", color='white', fontsize=11, y=1.01)
        plt.tight_layout()

        chart_path = f"output/charts/{code}_chart.png"
        plt.savefig(chart_path, dpi=120, bbox_inches='tight', facecolor='#1a1a2e')
        plt.close(fig)
        print(f"  チャート生成: {chart_path}")
        return chart_path
    except Exception as e:
        print(f"  [WARN] チャート生成失敗 {code}: {e}")
        return None


def inject_stock_charts(draft: str) -> tuple[str, list[str]]:
    """銘柄セクションのH3直下に株価チャートの__IMAGE_X__マーカーを挿入する"""
    # 「## このニュースで注目すべき銘柄」以降だけを対象にする
    section_match = re.search(r'(## このニュースで注目すべき銘柄.*)', draft, re.DOTALL)
    if not section_match:
        return draft, []

    image_paths = []
    lines = draft.split('\n')
    new_lines = []
    img_idx = 0

    for i, line in enumerate(lines):
        new_lines.append(line)
        # H3の銘柄見出しを検出（例：### トヨタ自動車（7203）/ ### NVDA）
        h3_match = re.match(r'^###\s+.+', line)
        if not h3_match:
            continue

        # 銘柄コードを抽出
        jp_match = re.search(r'[（(](\d{4})[）)]', line)
        us_match = re.search(r'\b([A-Z]{2,5})\b', line)
        noise = {"AI", "FRB", "SOX", "ETF", "ADR", "CEO", "GDP", "USD", "JPY", "BOJ", "FED"}

        code, is_jp = None, True
        if jp_match:
            code, is_jp = jp_match.group(1), True
        elif us_match and us_match.group(1) not in noise:
            code, is_jp = us_match.group(1), False

        if not code:
            continue

        chart_path = generate_stock_chart(code, is_jp)
        if chart_path:
            # 株価行（直近終値：の行）の直後にマーカーを挿入
            new_lines.append(f'__IMAGE_{img_idx}__')
            image_paths.append(chart_path)
            img_idx += 1

    return '\n'.join(new_lines), image_paths


def inject_realtime_prices(draft: str) -> str:
    """記事内の銘柄コードをもとにリアルタイム株価を取得してClaudeで注入する"""
    # 日本株コード（4桁数字） 例：（8035）
    jp_codes = list(dict.fromkeys(re.findall(r'[（(](\d{4})[）)]', draft)))
    # 米国株ティッカー（大文字2〜5字） 例：NVDA、META、AAPL
    us_tickers = list(dict.fromkeys(re.findall(r'\b([A-Z]{2,5})\b', draft)))
    # 一般的な英単語を除外
    noise = {"AI", "FRB", "SOX", "ETF", "ADR", "GDP", "CPI", "BOJ", "USD", "JPY",
             "WTI", "PER", "PBR", "CFD", "ROE", "HBM", "DMA", "EV", "VIX", "PCR",
             "HBA", "PBR", "EPS", "M2", "PE", "QE", "US", "EU", "UK", "JP"}
    us_tickers = [t for t in us_tickers if t not in noise][:5]

    price_lines = []
    today = datetime.datetime.now(JST)
    is_weekend = today.weekday() >= 5

    for code in jp_codes[:3]:
        price = get_realtime_price(code, is_jp=True)
        if price:
            label = f"週明け注目水準（直近終値）：{price}" if is_weekend else f"直近終値：{price}"
            price_lines.append(f"  {code}（東証）: {label}")

    for ticker in us_tickers:
        price = get_realtime_price(ticker, is_jp=False)
        if price:
            price_lines.append(f"  {ticker}（米国）: 直近終値 {price}")

    if not price_lines:
        print("  [INFO] リアルタイム株価取得なし（銘柄コード未検出 or 取得失敗）")
        return draft

    price_block = "\n".join(price_lines)
    print(f"  リアルタイム株価取得:\n{price_block}")

    update_prompt = f"""以下の投資記事の株価表記を、提供したリアルタイム株価データに更新してください。

【リアルタイム株価データ（{today.strftime('%Y年%m月%d日')}時点の直近終値）】
{price_block}

【更新ルール】
- 「本日の株価：〇〇円前後」「週明けの注目水準：〇〇円前後」などの株価表記を実際の数値に更新
- 株価以外の内容・構成・主張は一切変えない
- コメント・前置き不要。更新後の記事本文のみ出力

【記事】
{draft}"""

    updated = run_claude(update_prompt, model="claude-sonnet-4-6", timeout=120)
    if updated and len(updated) >= len(draft) * 0.7:
        print(f"  株価注入完了（{len(draft)} → {len(updated)} 文字）")
        return clean_article(updated)
    print("  [WARN] 株価注入失敗、元の記事を使用")
    return draft


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

    today = datetime.datetime.now(JST)
    weekday = today.weekday()  # 0=月, 5=土, 6=日
    if weekday == 5:
        weekday_note = "【執筆曜日：土曜日】読者が記事を読むのは日曜〜月曜の朝。「金曜引け後に〜する」など市場がすでに閉じた前提の行動指針は禁止。「週明け月曜の寄り付きで〜を確認する」「月曜の値動き次第で〜」など月曜を見越した視点で書くこと。"
    elif weekday == 6:
        weekday_note = "【執筆曜日：日曜日】読者が記事を読むのは日曜〜月曜の朝。市場は閉じており週明けまで売買できない。「金曜引け後の水準でポジションを組む」など過去の市場動作を前提にした行動指針は禁止。「月曜の寄り付き値を確認してから〜」「週明けの動き次第で〜」など月曜に読者が取れる行動を軸に書くこと。"
    else:
        weekday_note = f"【執筆曜日：{'月火水木金'[weekday]}曜日】当日〜翌日の市場動向を基準にした行動指針でOK。"

    return f"""note.com向けの投資解説記事を執筆してください。

【このnoteのコンセプト（執筆方針として内部的に参照すること。記事本文には書かない）】
スイング・デイトレーダーのための朝の必読ニュース。
世界の動きが日本株にどう波及するかを毎朝解説し、情報収集で終わらせず実際の売買に活かす視点を提供する。

{weekday_note}

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
1. 数字を含む（「〇〇円」「〇〇%」「3つの」など）
2. 読者の不安または好奇心を刺激するが、答え・結論はタイトルで明かさない
   良い例：「PS5値上げで最も恩恵を受ける『半導体銘柄』の正体」「ダウ800ドル暴落――5週連続安が示す3つの危険信号」
   悪い例：「PS5値上げでソニー株は買いか――答えはノーだ」（タイトルで結論を出してしまっている）
3. 30文字以内
禁止：「〜について」「〜を解説」「〜とは」で終わるタイトル、タイトルで結論・答えを明かすもの

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

（※URLは必ず単独の行に置くこと。誘導文テキスト内にURLを埋め込まない）

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
        raw = [t.strip() for t in tags_match.group(1).split(',')]
        topic_tags = [t for t in raw if t in TOPIC_TAGS_OPTIONS][:2]
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
- 本文: リード文 → ## {source}が報じたこと → ## [結論H2見出し] → ## 行動の考え方 → ## このニュースで注目すべき銘柄
- 「## {source}が報じたこと」は「{source}によると、」という書き出しで800〜1000字
- タイトルで結論・答えを明かさない（好奇心を引くが答えは本文で明かす）
- 銘柄セクション末尾に誘導文を入れ、最後の行に単独で次のURLを置く（埋め込みカード用）：
{MAGAZINE_URL}
- 末尾: TOPIC_TAGS: タグ1,タグ2（為替/FRB/金利/決算/マクロ経済/エネルギー/半導体/日銀/円安/円高 から2つ）
- 「おわりに」「今週の注目指標」見出し禁止・絵文字禁止
- コメント・まとめ・前置き不要。記事本文のみ出力"""
            supplement = run_claude(supplement_prompt, model="claude-opus-4-6", timeout=600)
            if supplement:
                s_title_match = re.search(r'^TITLE:\s*(.+)$', supplement, re.MULTILINE)
                if s_title_match and not title:
                    title = s_title_match.group(1).strip()
                    supplement = re.sub(r'^TITLE:\s*.+\n?', '', supplement, count=1, flags=re.MULTILINE).strip()
                s_tags_match = re.search(r'TOPIC_TAGS:\s*(.+)$', supplement, re.MULTILINE)
                if s_tags_match and not topic_tags:
                    s_raw = [t.strip() for t in s_tags_match.group(1).split(',')]
                    topic_tags = [t for t in s_raw if t in TOPIC_TAGS_OPTIONS][:2]
                    supplement = re.sub(r'TOPIC_TAGS:\s*.+$', '', supplement, flags=re.MULTILINE).strip()

        if supplement:
            expanded = clean_article(supplement)
            # 補強後が元より長い場合のみ採用
            if len(expanded) > len(draft):
                draft = expanded
            print(f"  補強後: {len(draft)} 文字")

    draft = clean_article(draft)

    # リアルタイム株価を注入
    print(f"  リアルタイム株価を取得・注入中...")
    draft = inject_realtime_prices(draft)

    # 銘柄チャートを生成してマーカーを挿入
    print(f"  銘柄チャートを生成中...")
    draft, image_paths = inject_stock_charts(draft)

    # タイトルが抽出できなかった場合は本文H2から取得
    if not title:
        first_h2 = re.search(r'^##\s+(.+)$', draft, re.MULTILINE)
        if first_h2:
            title = first_h2.group(1).strip()
        else:
            title = news['title'][:30]

    all_tags = FIXED_TAGS + [t for t in topic_tags if t not in FIXED_TAGS]

    return {
        "title": title,
        "article": draft,
        "tags": all_tags,
        "topic_tags": topic_tags,
        "source_news": news,
        "image_paths": image_paths,
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
