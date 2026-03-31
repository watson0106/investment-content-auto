"""
② 記事執筆（1本・2ニュース構成）
仕様: note自動投稿パイプライン 運用ルール に準拠
- 2つのニューストピックをまとめた1本の記事を執筆
- タイトル固定：「新聞より早くてわかりやすい今日の投資ニュース速報｜M/D」
- 構成: 30秒サマリー → ニュース①（3パート） → ニュース②（3パート）
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import datetime
import urllib.request

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
    # cronはPATHが最小限のため /opt/homebrew/bin を先頭に追加（node等のため）
    homebrew_path = "/opt/homebrew/bin:/usr/local/bin"
    env["PATH"] = homebrew_path + ":" + env.get("PATH", "/usr/bin:/bin")
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
    try:
        result = subprocess.run(
            [claude_cmd, "-p", prompt, "--output-format", "text", "--model", model],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        print(f"  [WARN] Claude CLI 失敗: {result.stderr[:200]}")
        return ""
    except subprocess.TimeoutExpired:
        print(f"  [WARN] Claude CLI タイムアウト（{timeout}s）")
        return ""
    except Exception as e:
        print(f"  [WARN] Claude CLI エラー: {e}")
        return ""



def get_realtime_price(code: str, is_jp: bool = True) -> str | None:
    """yfinanceでリアルタイム株価を取得して文字列で返す"""
    try:
        import yfinance as yf
        ticker_str = f"{code}.T" if is_jp else code
        ticker = yf.Ticker(ticker_str)
        hist = ticker.history(period="5d")
        if hist.empty:
            return None
        close_series = hist["Close"].dropna()
        if close_series.empty:
            return None
        price = close_series.iloc[-1]
        if is_jp:
            return f"{price:,.0f}円"
        else:
            return f"${price:,.2f}"
    except Exception as e:
        print(f"  [WARN] 株価取得失敗 {code}: {e}")
        return None


def generate_stock_chart(code: str, is_jp: bool = True) -> str | None:
    """1ヶ月のローソク足チャートを生成してPNGパスを返す"""
    try:
        import yfinance as yf
        import mplfinance as mpf
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.rcParams['font.family'] = ['Hiragino Sans', 'Hiragino Maru Gothic Pro', 'sans-serif']

        ticker_str = f"{code}.T" if is_jp else code
        df = yf.Ticker(ticker_str).history(period="3mo")
        if df.empty:
            return None
        # NaN行を除去してからチェック
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        if len(df) < 5:
            return None
        # 直近1ヶ月分に絞る
        df = df.tail(22)

        # mplfinanceはtz-naiveなインデックスを要求
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        os.makedirs("output/charts", exist_ok=True)
        chart_path = f"output/charts/{code}_chart.png"

        label = f"{code}（東証）" if is_jp else code

        # 移動平均
        add_plots = []
        if len(df) >= 5:
            add_plots.append(mpf.make_addplot(df['Close'].rolling(5).mean(),
                                              color='#ffa500', width=1.2))
        if len(df) >= 20:
            add_plots.append(mpf.make_addplot(df['Close'].rolling(20).mean(),
                                              color='#ff69b4', width=1.2))

        mc = mpf.make_marketcolors(
            up='#44cc66', down='#ff4444',
            edge='inherit',
            wick={'up': '#44cc66', 'down': '#ff4444'},
            volume={'up': '#44cc66', 'down': '#ff4444'},
        )
        s = mpf.make_mpf_style(
            marketcolors=mc,
            facecolor='#1a1a2e',
            edgecolor='#333355',
            figcolor='#1a1a2e',
            gridcolor='#333355',
            gridstyle='--',
            rc={'font.family': ['Hiragino Sans', 'sans-serif'],
                'axes.labelcolor': '#aaaaaa',
                'xtick.color': '#aaaaaa',
                'ytick.color': '#aaaaaa',
                'text.color': 'white'},
        )

        fig, axes = mpf.plot(
            df,
            type='candle',
            style=s,
            title=f"\n{label}  直近1ヶ月",
            volume=True,
            addplot=add_plots if add_plots else None,
            figsize=(10, 5.5),
            returnfig=True,
            tight_layout=True,
        )
        axes[0].title.set_color('white')
        axes[0].title.set_fontsize(11)

        fig.savefig(chart_path, dpi=120, bbox_inches='tight', facecolor='#1a1a2e')
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

        # 銘柄コードを抽出（285Aなど英数混在も対応）
        jp_match = re.search(r'[（(](\d{3,4}[A-Z]?)[）)]', line)
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


def download_news_image(image_url: str, section_num: int) -> str | None:
    """ニュースソースの画像URLをダウンロードしてローカルに保存する"""
    if not image_url:
        return None
    try:
        os.makedirs("output/images", exist_ok=True)
        ext = "jpg" if image_url.lower().endswith((".jpg", ".jpeg")) else "png"
        path = f"output/images/news_{section_num}.{ext}"
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp, open(path, "wb") as f:
            f.write(resp.read())
        print(f"  ニュース引用画像ダウンロード: {path}")
        return path
    except Exception as e:
        print(f"  [WARN] ニュース画像ダウンロード失敗: {e}")
        return None


def inject_realtime_prices(draft: str) -> str:
    """記事内の銘柄コードをもとにリアルタイム株価を取得してClaudeで注入する"""
    # 日本株コード（4桁 or 285Aなど英数混在） 例：（8035）（285A）
    jp_codes = list(dict.fromkeys(re.findall(r'[（(](\d{3,4}[A-Z]?)[）)]', draft)))
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

    text = run_claude(prompt, model="claude-sonnet-4-6", timeout=180)
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

    # フォールバック：海外ソース × 日本ソースで異なるトピックを選ぶ
    jp_sources = {"Yahoo Finance Japan", "Yahoo Japan トップ", "NHK 経済", "日経新聞", "ロイター"}
    overseas = [a for a in articles if a.get("source") not in jp_sources]
    domestic = [a for a in articles if a.get("source") in jp_sources]
    topic1 = overseas[0] if overseas else articles[0]
    topic2 = domestic[0] if domestic else articles[min(1, len(articles)-1)]
    if topic1 is topic2:
        topic2 = articles[min(1, len(articles)-1)]
    print(f"  [INFO] フォールバックトピック: [{topic1['source']}] / [{topic2['source']}]")
    return topic1, topic2


def get_weekday_note() -> str:
    """曜日別の執筆注意文を返す"""
    today = datetime.datetime.now(JST)
    weekday = today.weekday()
    if weekday == 5:
        return "【執筆曜日：土曜日】読者が記事を読むのは日曜〜月曜の朝。「金曜引け後に〜する」など市場がすでに閉じた前提の行動指針は禁止。「週明け月曜の寄り付きで〜を確認する」「月曜の値動き次第で〜」など月曜を見越した視点で書くこと。"
    elif weekday == 6:
        return "【執筆曜日：日曜日】読者が記事を読むのは日曜〜月曜の朝。市場は閉じており週明けまで売買できない。「金曜引け後の水準でポジションを組む」など過去の市場動作を前提にした行動指針は禁止。「月曜の寄り付き値を確認してから〜」「週明けの動き次第で〜」など月曜に読者が取れる行動を軸に書くこと。"
    else:
        return f"【執筆曜日：{'月火水木金'[weekday]}曜日】当日〜翌日の市場動向を基準にした行動指針でOK。"


def build_news_section_prompt(news: dict, section_num: int = 1) -> str:
    """1ニュース分のセクション（3パート・合計2000字程度）の執筆プロンプト"""
    source = news.get('source', 'メディア')
    title_en = news['title']
    summary = news.get('summary', '')[:400]
    weekday_note = get_weekday_note()
    num_prefix = "①" if section_num == 1 else "②"

    return f"""note.com向けの投資解説セクションを執筆してください。対象読者はスイング・デイトレーダー。

{weekday_note}

【取り上げるニュース】
ソース: {source}
タイトル: {title_en}
概要: {summary}

【構成（この順番・このH2/H3で厳守）】

## {num_prefix}{source}が報じたこと

「{source}によると、〜」という書き出しで開始。
客観的・解説的な文体で、このニュースの概要・背景・意味合いを丁寧に解説する（1000字程度）。
専門用語は使ってもよいが、初めて出てくるときは一言で説明を加えること。
複数の切り口がある場合はH3で区切って展開する。

## [筆者の意見をH2見出しそのものに一言で書く。例：「この動きは○○の前兆だと私は見ている」]

上のH2見出しに意見を一言で入れて、本文でその根拠を展開（700字程度）。
ブロガー口調（「〜だと思う」「〜と私は見ている」など）で、なぜそう考えるか理由・根拠を具体的に書く。

## このニュースで注目すべき銘柄

このニュースの影響を最も受ける銘柄を1つだけ取り上げる。

### [銘柄名（証券コード or ティッカー）]

- 本日の株価（土日は「週明け注目水準（直近終値）：〇〇円前後」）
- このニュースとこの銘柄の直接的な関係を1文で
- 需給・業績・センチメントのどのルートで株価に波及するか
- 短期（当日〜1週間）の動き見立てを具体的な価格帯・数値で
（700字程度）

【執筆ルール】
- 目標文字数：合計2000字（絶対に2000字を下回らないこと。足りない場合は各パートをさらに掘り下げて補う）
- 「行動の考え方」「おわりに」見出し禁止
- 絵文字禁止・個人プロフィール禁止
- 数字は具体的に（「大幅」ではなく「+3.5%」）
- 1段落は最大3〜4文。それ以上になる場合は必ず段落を分けて改行を入れる（スマホ読者向け）
- 重要な結論・インパクトのある数字（例：4倍、750億円、+12%など）は必ず**太字**で強調する
- 各段落の冒頭か末尾に結論・数字を置き、斜め読みでも内容が伝わるようにする
- 記事本文のみ出力（前置き・後記・コメント不要）
- 有料マガジンへの誘導文・URLはこのセクション内に一切書かない（記事全体の末尾に別途追加される）
- 末尾: TOPIC_TAGS: タグ1,タグ2（為替/FRB/金利/決算/マクロ経済/エネルギー/半導体/日銀/円安/円高 から2つ）"""


def write_news_section(news: dict, section_num: int) -> dict:
    """1ニュース分のセクションを執筆して返す"""
    prompt = build_news_section_prompt(news, section_num)

    print(f"  Claude CLI でセクション{section_num}執筆中...")
    draft = run_claude(prompt, model="claude-opus-4-6", timeout=600)

    if not draft:
        raise RuntimeError(f"セクション{section_num}の執筆に失敗しました")

    print(f"  執筆完了（{len(draft)} 文字）")

    # TOPIC_TAGS: 抽出
    topic_tags = []
    tags_match = re.search(r'TOPIC_TAGS:\s*(.+)$', draft, re.MULTILINE)
    if tags_match:
        raw = [t.strip() for t in tags_match.group(1).split(',')]
        topic_tags = [t for t in raw if t in TOPIC_TAGS_OPTIONS][:2]
        draft = re.sub(r'TOPIC_TAGS:\s*.+$', '', draft, flags=re.MULTILINE).strip()

    draft = clean_article(draft)

    # リアルタイム株価を注入
    print(f"  リアルタイム株価を取得・注入中...")
    draft = inject_realtime_prices(draft)

    # 銘柄チャートを生成してマーカーを挿入
    print(f"  銘柄チャートを生成中...")
    draft, image_paths = inject_stock_charts(draft)

    # ニュースソース引用画像がある場合は先頭に挿入
    news_img_path = download_news_image(news.get("image_url", ""), section_num)
    if news_img_path:
        # 既存の __IMAGE_n__ インデックスを1つずつ繰り上げ
        draft = re.sub(r'__IMAGE_(\d+)__', lambda m: f'__IMAGE_{int(m.group(1)) + 1}__', draft)
        image_paths = [news_img_path] + image_paths
        # 最初のH1見出し行の直後に __IMAGE_0__ を挿入
        draft = re.sub(r'(^# .+$)', r'\1\n\n__IMAGE_0__', draft, count=1, flags=re.MULTILINE)
        print(f"  ニュース引用画像を先頭に挿入（計{len(image_paths)}枚）")

    return {
        "text": draft,
        "image_paths": image_paths,
        "topic_tags": topic_tags,
    }


def generate_summary(sec1_text: str, sec2_text: str) -> str:
    """2セクションから10秒サマリー（①②番号付き2行）を生成する"""
    prompt = f"""以下の2つの投資ニュースセクションを読んで、読者が「続きを読みたい」と思うサマリーを2行で書いてください。

要件：
- 1行目は「① 」で始める、2行目は「② 」で始める
- 各行は60字以内
- 単なる事実の要約ではなく「疑問・緊張感・注目点」で読者を引き込む形にする
  例：「① ドル円が160円台まで円安進行、約1年8カ月ぶり」→ NG（事実の列挙）
  例：「① ドル円が160円台まで円安進行、政府の為替介入はいつくるのか？」→ OK（続きが読みたくなる）
- 「この動きで○○はどうなる？」「○○の決断が注目される」「本当の勝者は誰か」など疑問・興味を引く表現を使う
- 専門用語なし
- 「* 」は絶対に使わない
- 2行のみ出力（説明・前置き不要）

【セクション1（抜粋）】
{sec1_text[:600]}

【セクション2（抜粋）】
{sec2_text[:600]}"""

    result = run_claude(prompt, model="claude-sonnet-4-6", timeout=120)
    if result:
        lines = [l.strip() for l in result.strip().split('\n')
                 if l.strip().startswith('①') or l.strip().startswith('②')]
        if len(lines) >= 2:
            return '\n'.join(lines[:2])

    # フォールバック：各セクションの最初の文を使う
    def first_sentence(text: str) -> str:
        clean = re.sub(r'^#{1,3}\s+.+$', '', text, flags=re.MULTILINE).strip()
        m = re.search(r'[。！？]', clean[:200])
        return clean[:m.end()] if m else clean[:80]

    return f"① {first_sentence(sec1_text)}\n② {first_sentence(sec2_text)}"


def get_random_cover_image() -> str | None:
    """~/Desktop/投資画像/ からランダムに画像を返す"""
    import glob
    import random
    folder = os.path.expanduser("~/Desktop/投資画像")
    if not os.path.isdir(folder):
        return None
    images = (
        glob.glob(os.path.join(folder, "*.png")) +
        glob.glob(os.path.join(folder, "*.jpg")) +
        glob.glob(os.path.join(folder, "*.jpeg"))
    )
    return random.choice(images) if images else None


def main():
    print("=== ② 記事執筆（1本・2ニュース構成） ===")

    with open("output/collected_news.json", encoding="utf-8") as f:
        articles = json.load(f)

    # 2トピック選定
    print("  トピック選定中...")
    news1, news2 = select_topics(articles)
    print(f"  セクション1トピック: {news1['title']}")
    print(f"  セクション2トピック: {news2['title']}")

    os.makedirs("output", exist_ok=True)

    # セクション1執筆
    print(f"\n  --- セクション1執筆 ---")
    sec1 = write_news_section(news1, 1)

    # セクション2執筆
    print(f"\n  --- セクション2執筆 ---")
    sec2 = write_news_section(news2, 2)

    # 30秒サマリー生成
    print(f"  30秒サマリー生成中...")
    summary = generate_summary(sec1["text"], sec2["text"])

    # セクション2の画像インデックスをセクション1の枚数分ずらす
    offset = len(sec1["image_paths"])
    sec2_text = re.sub(
        r'__IMAGE_(\d+)__',
        lambda m: f'__IMAGE_{int(m.group(1)) + offset}__',
        sec2["text"]
    )

    # 記事タイトル（固定形式・日付入り）
    today = datetime.datetime.now(JST)
    title = f"新聞より早くてわかりやすい今日の投資ニュース速報｜{today.month}/{today.day}"

    # カバー画像（~/Desktop/投資画像/ からランダム）
    cover_path = get_random_cover_image()

    # 記事本文を組み立て
    magazine_text = (
        "情報を正確に理解することは、投資の第一歩に過ぎない。"
        "株価は常に「情報の一歩先」を織り込んで動いており、"
        "ニュースを読むだけでは勝てないのが相場の現実だ。"
        "毎週の注目銘柄・具体的な売買シナリオ・エントリー根拠まで踏み込んで解説する有料マガジンはこちら。"
        "「知っている」を「稼げる」に変えたい方はぜひ。"
    )
    body = (
        f"## 今日のニュース速報｜10秒サマリー\n\n"
        f"{summary}\n\n"
        f"{sec1['text']}\n\n"
        f"{sec2_text}\n\n"
        f"{magazine_text}\n\n"
        f"{MAGAZINE_URL}"
    )

    # タグ（両セクションのTOPIC_TAGSを合算、重複排除）
    all_topic_tags = list(dict.fromkeys(sec1["topic_tags"] + sec2["topic_tags"]))[:2]
    all_tags = FIXED_TAGS + [t for t in all_topic_tags if t not in FIXED_TAGS]

    article = {
        "title": title,
        "article": body,
        "tags": all_tags,
        "topic_tags": all_topic_tags,
        "source_news": {"news1": news1, "news2": news2},
        "image_paths": sec1["image_paths"] + sec2["image_paths"],
        "cover_path": cover_path,
    }

    with open("output/article_1.json", "w", encoding="utf-8") as f:
        json.dump(article, f, ensure_ascii=False, indent=2)
    print(f"  保存: output/article_1.json  タイトル: {title}")

    # 後方互換
    with open("output/final.json", "w", encoding="utf-8") as f:
        json.dump(article, f, ensure_ascii=False, indent=2)

    return {"article_1": article}


if __name__ == "__main__":
    main()
