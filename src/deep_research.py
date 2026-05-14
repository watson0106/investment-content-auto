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
TOPIC_TAGS_OPTIONS = ["為替", "FRB", "金利", "決算", "マクロ経済", "エネルギー", "半導体", "日銀", "円安", "円高",
                      "個別株", "銘柄分析", "テクニカル分析", "ファンダメンタルズ", "NISA", "投資信託"]


def clean_article(text: str) -> str:
    first_heading = re.search(r'^#{1,3}\s', text, re.MULTILINE)
    if first_heading and first_heading.start() > 0:
        before = text[:first_heading.start()].strip()
        if before and not re.fullmatch(r'[-\s]*', before):
            text = text[first_heading.start():]
    # [CHART: ...] プレースホルダーが記事内に残っている場合は除去（チャート生成済みのもの）
    text = re.sub(r'\[CHART:[^\]]*\]', '', text)
    # 「---」区切り線を空行に置換（本文中・末尾どちらも除去。AI感排除・記事切り捨て防止）
    text = re.sub(r'\n-{3,}\n', '\n\n', text)
    # メタコメント行を除去（「記事は〜に保存済みです」「合計約〜字」などの行）
    meta_line_patterns = [
        r'^記事は.+に保存済みです.*$',
        r'^合計約.+字.*$',
        r'^CHART[プレー]*スホルダー.*$',
        r'^H[123]見出し.*適合.*$',
        r'^口調ルール.*$',
    ]
    for pat in meta_line_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE)
    # TOPIC_TAGS行を確実に除去（Geminiが再挿入することがあるため）
    text = re.sub(r'^TOPIC_TAGS:.*$', '', text, flags=re.MULTILINE)
    # 「noteがすでに〜というタイトルで記事を公開しています。」系の文を除去
    # （Geminiが前回記事タイトルをニュースとして受け取り、参照文を生成してしまうケースへの対処）
    text = re.sub(r'noteがすでに.{0,300}というタイトルで記事を公開しています。\s*', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = '\n'.join(line.rstrip() for line in text.split('\n'))
    # 高頻度AI語の後処理（3回以上出現する特定語を言い換えてAI感を削減）
    text = _reduce_repetitive_words(text)
    return text.strip()


def _reduce_repetitive_words(text: str) -> str:
    """同じカタカナ語が3回以上出現する場合、3回目以降を言い換える（AI感の削減）"""
    from collections import Counter
    import random

    # 言い換えテーブル（3回目以降に使う代替表現）
    replacements = {
        "リスク": ["危うさ", "落とし穴", "怖いところ", "注意点", "危険性"],
        "ポートフォリオ": ["持ち株の組み合わせ", "保有銘柄の配分", "保有構成"],
        "バランス": ["偏りのない配分", "分散された構成"],
        "シナリオ": ["展開", "可能性", "パターン"],
        "インパクト": ["影響", "打撃", "波及"],
        "コンセンサス": ["市場の見方", "大方の予想"],
        "モメンタム": ["勢い", "流れ"],
        "センチメント": ["市場心理", "投資家心理"],
        "ボラティリティ": ["値動きの荒さ", "相場の激しさ"],
    }

    for word, alts in replacements.items():
        count = text.count(word)
        if count < 3:
            continue
        # 3回目以降の出現を順番に置き換える
        occurrences = []
        start = 0
        while True:
            idx = text.find(word, start)
            if idx == -1:
                break
            occurrences.append(idx)
            start = idx + 1
        # 3回目以降のみ置き換え（逆順でインデックスがずれないように）
        for i, pos in enumerate(reversed(occurrences)):
            if len(occurrences) - 1 - i < 2:  # 0,1番目（3回目以降）はそのまま
                continue
            replacement = alts[(i) % len(alts)]
            text = text[:pos] + replacement + text[pos + len(word):]

    return text


def run_claude(prompt: str, model: str = "claude-opus-4-6", timeout: int = 600) -> str:
    """Claude CLIを呼び出してテキストを返す（最大3回リトライ）"""
    import time as _time
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
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
        result = subprocess.run(["which", "claude"], capture_output=True, text=True, env=env)
        claude_cmd = result.stdout.strip() if result.returncode == 0 else None
    if not claude_cmd:
        print("  [WARN] Claude CLI が見つかりません")
        return ""

    for attempt in range(1, 4):
        proc = None
        try:
            if attempt > 1:
                wait = 30 * attempt  # 60秒・90秒と待機（短縮）
                print(f"  [INFO] Claude CLI リトライ {attempt}/3 （{wait}秒待機）...")
                _time.sleep(wait)
            proc = subprocess.Popen(
                [claude_cmd, "-p", prompt, "--output-format", "text", "--model", model,
                 "--allowedTools", "none", "--dangerously-skip-permissions"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,  # インタラクティブプロンプトをブロック
                text=True, env=env,
                cwd="/tmp",  # CLAUDE.md読み込み防止（プロジェクトディレクトリのペルソナ汚染対策）
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f"  [WARN] Claude CLI タイムアウト（{timeout}s） attempt={attempt} - プロセスを強制終了します")
                proc.kill()
                proc.wait()  # killが確実に完了するまで待つ
                continue
            if proc.returncode == 0 and stdout.strip():
                output = stdout.strip()
                # メタ応答検知：Claude CLIがアドバイザーモードで応答した場合は失敗扱い
                meta_patterns = [
                    "記事の全文が抜粋されておらず", "出力しました", "記事概要：",
                    "各セクション文字数", "出力先：", "記事を出力", "抜粋されておらず",
                    "概要のみの情報", "文字数：", "全セクション基準を満たしています",
                    "に保存済みです", "合計約", "CHARTプレースホルダー", "H2見出し",
                    "口調ルール", "保存先：", "文字数チェック", "適合しています",
                    "というタイトルで記事を公開しています",
                ]
                if any(p in output for p in meta_patterns):
                    print(f"  [WARN] Claude CLI メタ応答検知 attempt={attempt}/5（CLAUDE.md汚染の可能性）")
                    continue
                return output
            print(f"  [WARN] Claude CLI 失敗 attempt={attempt}/5: rc={proc.returncode} stderr={stderr[:200]!r} stdout={stdout[:200]!r}")
        except Exception as e:
            print(f"  [WARN] Claude CLI エラー attempt={attempt}: {e}")
            if proc is not None:
                try:
                    proc.kill()
                    proc.communicate(timeout=5)
                except Exception:
                    pass

    return ""


def run_gemini(prompt: str, model: str = "gemini-2.5-flash", timeout: int = 300) -> str:
    """Gemini APIを呼び出してテキストを返す（Claude CLIの代替・認証不要）"""
    import time as _time
    api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_IMAGEN_API_KEY", "")
    if not api_key:
        # .envから直接読む（cron環境でload_dotenv未実行の場合）
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY=") or line.startswith("GEMINI_IMAGEN_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        if api_key:
                            break
    if not api_key:
        print("  [WARN] GEMINI_API_KEY が設定されていません")
        return ""

    meta_patterns = [
        "記事の全文が抜粋されておらず", "出力しました", "記事概要：",
        "各セクション文字数", "出力先：", "記事を出力", "抜粋されておらず",
        "概要のみの情報", "文字数：", "全セクション基準を満たしています",
        "に保存済みです", "合計約", "CHARTプレースホルダー", "H2見出し",
        "口調ルール", "保存先：", "文字数チェック", "適合しています",
        "というタイトルで記事を公開しています",  # 前回記事タイトルを参照する誤生成
    ]

    models = [model, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    models = list(dict.fromkeys(models))  # 重複除去

    for attempt in range(1, 4):
        if attempt > 1:
            wait = 30 * attempt
            print(f"  [INFO] Gemini リトライ {attempt}/3 （{wait}秒待機）...")
            _time.sleep(wait)
        for model_name in models:
            try:
                import google.genai as genai
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                output = response.text.strip() if response.text else ""
                if output and not any(p in output for p in meta_patterns):
                    return output
                if output:
                    print(f"  [WARN] Gemini メタ応答検知 attempt={attempt} model={model_name}")
            except Exception as e:
                print(f"  [WARN] Gemini エラー attempt={attempt} model={model_name}: {e}")
                continue
            break

    return ""


def parse_jst(published_str: str) -> datetime.datetime | None:
    """発表時刻文字列をJSTのdatetimeに変換する"""
    if not published_str:
        return None
    try:
        # ISO 8601 (+09:00 等のタイムゾーン付き)
        # Python 3.9 は fromisoformat でタイムゾーンオフセットを扱えないため手動処理
        import re as _re
        s = published_str.strip()
        m = _re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-])(\d{2}):(\d{2})$', s)
        if m:
            dt_part, sign, hh, mm = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
            base = datetime.datetime.strptime(dt_part, '%Y-%m-%dT%H:%M:%S')
            offset = datetime.timedelta(hours=hh, minutes=mm)
            tz = datetime.timezone(offset if sign == '+' else -offset)
            return base.replace(tzinfo=tz).astimezone(JST)
        # タイムゾーンなし → JST と仮定
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                base = datetime.datetime.strptime(s, fmt)
                return base.replace(tzinfo=JST)
            except ValueError:
                continue
    except Exception:
        pass
    return None


def get_market_snapshot() -> str:
    """USD/JPY・日経平均・S&P500などをyfinanceで取得してプロンプト用テキストを返す"""
    import yfinance as yf
    today = datetime.datetime.now(JST)
    pairs = [
        ("USDJPY=X", "ドル円（USD/JPY）", ".2f"),
        ("^N225",    "日経平均",           ",.0f"),
        ("^SPX",     "S&P500",             ",.0f"),
        ("CL=F",     "WTI原油（$/バレル）", ".2f"),
    ]
    lines = []
    for ticker, label, fmt in pairs:
        try:
            hist = yf.Ticker(ticker).history(period="2d").dropna(subset=["Close"])
            if not hist.empty:
                price = hist["Close"].iloc[-1]
                lines.append(f"  {label}：{price:{fmt}}")
        except Exception:
            pass
    if not lines:
        return ""
    snap_time = today.strftime('%m月%d日 %H:%M')
    return f"【主要市場データ（{snap_time} JST時点・リアルタイム取得）】\n" + "\n".join(lines)


def get_news_timing_context(news: dict) -> str:
    """ニュースの発表タイミングを分析して執筆プロンプト用の文字列を返す。
    例：「引け後発表→PTSへの影響あり」「場中発表→既に株価に折り込み済み」等。
    """
    pub_dt = parse_jst(news.get('published', ''))
    if pub_dt is None:
        return ""

    formatted = pub_dt.strftime('%m月%d日 %H:%M JST')
    total_min = pub_dt.hour * 60 + pub_dt.minute

    # ── 東証取引時間帯の分類 ──────────────────────────────────
    # 前場PTS    : 08:00-09:00
    # 東証前場    : 09:00-11:30
    # 東証後場    : 12:30-15:30
    # 引け後PTS  : 16:30-23:59
    if total_min < 8 * 60:
        label = "深夜〜早朝"
        desc = ("東証が開く前（午前9時開場）に発表されたニュース。"
                "本日の寄り付きからダイレクトに株価に影響する可能性が高い。")
    elif total_min < 9 * 60:
        label = "前場PTS時間帯"
        desc = ("東証開場前のPTS（私設取引所での時間外取引、8:00-9:00）時間帯に発表。"
                "PTSで既に値動きしている可能性があり、東証寄り付きに直接波及しやすい。")
    elif total_min < 15 * 60 + 30:
        label = "東証場中"
        desc = ("東証の通常取引時間中（9:00-15:30）に発表されたニュース。"
                "発表後しばらく経っているため、株価にはすでにかなり織り込まれている可能性がある。"
                "記事執筆時点のリアルタイム株価でその反応を確認すること。")
    elif total_min < 16 * 60 + 30:
        label = "引け直後（夜間PTS開始前）"
        desc = ("東証引け後（15:30以降）・夜間PTS開始（16:30）前に発表。"
                "東証の株価には未反映。夜間PTS（16:30-23:59）で最初の値動きが出る。"
                "翌日の東証寄り付きに注目。")
    elif total_min < 24 * 60:
        label = "夜間PTS時間帯"
        desc = ("夜間PTS（16:30-23:59）の取引時間中に発表。"
                "PTSでの値動きがあれば翌日の東証寄り付きの方向感を示している可能性がある。"
                "東証引け後なので、本日の株価チャートには反映されていないが、翌朝の動きに直結する。")
    else:
        label = "東証場外"
        desc = "東証の通常取引時間外に発表されたニュース。"

    return (
        f"【情報発表タイミング：{formatted}（{label}）】\n"
        f"{desc}\n"
        "→ 記事の冒頭で「いつ発表された情報か」「その時点で既に株価に織り込まれているか否か」を必ず1〜2文で明示すること。"
    )


def get_pts_price_note(code: str, is_jp: bool, pub_dt: datetime.datetime | None) -> str:
    """引け後に発表されたニュースについてPTS/時間外株価を取得してコメント文を返す。
    日本株：yfinanceはPTSデータ非対応のため取得不可（その旨を記述）。
    米国株：yfinanceのpostMarketPrice/preMarketPriceを取得。
    """
    if pub_dt is None:
        return ""
    total_min = pub_dt.hour * 60 + pub_dt.minute
    after_close = total_min >= 15 * 60 + 30  # 15:30以降

    if not after_close:
        return ""

    try:
        import yfinance as yf
        if is_jp:
            # 日本株はPTSデータ取得不可
            return "（日本株のPTS価格はリアルタイム取得不可。証券会社のPTS板で確認推奨）"
        else:
            ticker = yf.Ticker(code)
            info = ticker.info
            post_price = info.get('postMarketPrice') or info.get('preMarketPrice')
            regular_price = info.get('regularMarketPrice') or info.get('previousClose')
            if post_price and regular_price:
                change = (post_price - regular_price) / regular_price * 100
                sign = "+" if change >= 0 else ""
                return f"時間外取引（AH）: ${post_price:,.2f}（通常終値比 {sign}{change:.1f}%）"
            elif post_price:
                return f"時間外取引（AH）: ${post_price:,.2f}"
    except Exception as e:
        pass
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

        fig.savefig(chart_path, dpi=120, bbox_inches='tight', facecolor='#1a1a2e', edgecolor='none')
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
        # 括弧内のティッカー優先（例：（F）（NVDA））→ 1文字も許容
        us_bracket_match = re.search(r'[（(]([A-Z]{1,5})[）)]', line)
        us_match = re.search(r'\b([A-Z]{2,5})\b', line)
        noise = {"AI", "FRB", "SOX", "ETF", "ADR", "CEO", "GDP", "USD", "JPY", "BOJ", "FED"}

        code, is_jp = None, True
        if jp_match:
            code, is_jp = jp_match.group(1), True
        elif us_bracket_match and us_bracket_match.group(1) not in noise:
            code, is_jp = us_bracket_match.group(1), False
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


def _call_gemini(prompt: str) -> str:
    """Gemini APIを呼び出してテキストを返す（google.genai 新SDK対応）"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return ""
    try:
        import google.genai as genai
        client = genai.Client(api_key=api_key)
        # 新しいモデルから順に試す
        for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                return response.text or ""
            except Exception:
                continue
    except Exception as e:
        print(f"  [WARN] Gemini API エラー: {e}")
    return ""


def _set_xticklabels_auto(ax, labels: list):
    """ラベル数に応じて間引き・回転を自動調整してx軸ラベルを設定する"""
    n = len(labels)
    if n <= 7:
        ax.set_xticklabels(labels, rotation=0, ha='center')
    elif n <= 12:
        ax.set_xticklabels(labels, rotation=35, ha='right')
    else:
        # 8個以上は2個おきに間引き
        step = max(1, n // 8)
        ticks = list(range(0, n, step))
        ax.set_xticks(ticks)
        ax.set_xticklabels([labels[i] for i in ticks], rotation=35, ha='right')


def _render_data_chart(chart_data: dict, idx: int) -> str | None:
    """chart_dataに基づいてmatplotlibでデータチャートを生成しパスを返す"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.rcParams['font.family'] = ['Hiragino Sans', 'Hiragino Maru Gothic Pro', 'sans-serif']

        data = chart_data.get("data", [])
        series_list_check = chart_data.get("series", [])
        # series がある場合は data が空でも続行
        if len(data) < 2 and not series_list_check:
            return None

        # 全chart_typeでゼロ値・プレースホルダ行チェック
        chart_type_check = chart_data.get("chart_type", "bar")
        y_vals_check = []
        for d in data:
            try:
                y_vals_check.append(float(d.get("y", 0)))
            except (TypeError, ValueError):
                y_vals_check.append(0.0)
        x_vals_check = [str(d.get("x", "")).strip() for d in data]
        placeholder_x = {"項目", "item", "指標", "label", ""}
        valid_rows = [
            (x, y) for x, y in zip(x_vals_check, y_vals_check)
            if x.lower() not in {p.lower() for p in placeholder_x}
        ]
        if len(valid_rows) < 2:
            print(f"  [SKIP] データ行不足（行数={len(valid_rows)}）: {chart_data.get('title','')}")
            return None
        # ゼロ値のみ、またはほぼゼロ（絶対値が0.5未満）のデータはスキップ
        # ただし単位が%・率・bps・円・ドルなら小さい値でも有効
        unit_str = (chart_data.get("unit", "") + chart_data.get("y_label", "")).lower()
        small_ok = any(kw in unit_str for kw in ["%", "率", "bps", "bp", "円", "ドル", "usd", "jpy", "兆", "億", "万"])
        max_abs = max(abs(y) for _, y in valid_rows) if valid_rows else 0
        if not small_ok and max_abs < 0.5:
            print(f"  [SKIP] データが実質ゼロ（max_abs={max_abs:.3f}）: {chart_data.get('title','')}")
            return None
        if all(y == 0.0 for _, y in valid_rows):
            print(f"  [SKIP] テーブルデータ無効（ゼロ値のみ）: {chart_data.get('title','')}")
            return None

        x_vals = [str(d.get("x", "")) for d in data]
        y_vals = [float(d.get("y", 0)) for d in data]
        chart_type = chart_data.get("chart_type", "bar")
        title = chart_data.get("title", "")
        x_label = chart_data.get("x_label", "")
        y_label = chart_data.get("y_label", "")
        unit = chart_data.get("unit", "")
        source = chart_data.get("source", "")

        fig, ax = plt.subplots(figsize=(10, 5), facecolor='#1a1a2e')
        ax.set_facecolor('#1a1a2e')

        _BG = '#1a1a2e'
        _BG2 = '#16213e'
        _GRID = '#333355'
        _ACCENT = '#e94560'
        _MUTED = '#0f3460'
        _SUBTEXT = '#aaaaaa'

        # 複数系列（series フィールドがある場合）
        series_list = chart_data.get("series", [])

        if chart_type == "pie":
            # 円グラフ（pie）
            plt.close(fig)
            fig, ax = plt.subplots(figsize=(10, 6), facecolor=_BG)
            ax.set_facecolor(_BG)
            pie_colors = ['#4488ff', '#44cc66', '#ff6644', '#ffcc00', '#cc44ff',
                          '#44ccff', '#ff4488', '#88cc44'][:len(y_vals)]
            wedges, texts, autotexts = ax.pie(
                y_vals, labels=x_vals, autopct='%1.1f%%', startangle=90,
                colors=pie_colors, pctdistance=0.82,
                wedgeprops=dict(edgecolor=_BG2, linewidth=1.5),
            )
            for txt in texts:
                txt.set_color('white')
                txt.set_fontsize(10)
            for at in autotexts:
                at.set_color('white')
                at.set_fontsize(9)
                at.set_fontweight('bold')
            ax.set_title(title, color='white', fontsize=13, pad=14, fontweight='bold')
        elif chart_type == "table":
            # 表（table）— テーブルサイズにぴったり合わせる
            plt.close(fig)
            n_rows = len(x_vals)
            row_h = 0.55          # 1行の高さ（inch）
            title_h = 0.55        # タイトル行
            fig_h = row_h * (n_rows + 1) + title_h   # ヘッダー1行 + データ行 + タイトル
            fig_w = 9
            fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor=_BG2)
            ax.set_facecolor(_BG2)
            ax.axis('off')
            # タイトル
            fig.text(0.5, 1.0 - title_h / fig_h * 0.5,
                     title, ha='center', va='center',
                     color='white', fontsize=15, fontweight='bold')
            unit_str = f"（{unit}）" if unit else ""
            table_data = [[lbl, f"{val:,.1f}{unit}"] for lbl, val in zip(x_vals, y_vals)]
            tbl = ax.table(
                cellText=table_data,
                colLabels=[x_label or '指標', f"{y_label}{unit_str}" if y_label else '値'],
                cellLoc='center', loc='center',
                bbox=[0, 0, 1, 1],  # ax全体にテーブルを展開
            )
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(14)          # 大きめフォント
            for (row, col), cell in tbl.get_celld().items():
                cell.set_linewidth(0.5)
                cell.set_edgecolor(_GRID)
                if row == 0:
                    cell.set_facecolor(_MUTED)
                    cell.set_text_props(color='white', fontweight='bold', fontsize=14)
                elif row % 2 == 0:
                    cell.set_facecolor('#1a1a4e')
                    cell.set_text_props(color='white', fontweight='bold', fontsize=14)
                else:
                    cell.set_facecolor(_BG2)
                    cell.set_text_props(color='#eeeeee', fontweight='bold', fontsize=14)
                cell.set_height(1.0 / (n_rows + 1))  # 均等な行高さ
        elif chart_type == "line":
            line_colors = ['#44cc66', '#4488ff', '#ff6644', '#ffcc00', '#cc44ff']
            if series_list:
                # 複数系列
                for s_idx, s in enumerate(series_list):
                    s_x = [str(d.get("x", "")) for d in s.get("data", [])]
                    s_y = [float(d.get("y", 0)) for d in s.get("data", [])]
                    col = line_colors[s_idx % len(line_colors)]
                    ax.plot(range(len(s_x)), s_y, color=col, linewidth=2.5,
                            marker='o', markersize=5, label=s.get("name", f"系列{s_idx+1}"))
                    ax.fill_between(range(len(s_x)), s_y, alpha=0.06, color=col)
                # x軸は最初の系列の x_vals を使用
                first_x = [str(d.get("x", "")) for d in series_list[0].get("data", [])]
                ax.set_xticks(range(len(first_x)))
                _set_xticklabels_auto(ax, first_x)
                ax.legend(facecolor='#16213e', edgecolor=_GRID, labelcolor='white', fontsize=9)
            else:
                # 単一系列
                ax.plot(range(len(x_vals)), y_vals, color='#44cc66', linewidth=2.5,
                        marker='o', markersize=6)
                ax.fill_between(range(len(x_vals)), y_vals, alpha=0.12, color='#44cc66')
                ax.set_xticks(range(len(x_vals)))
                _set_xticklabels_auto(ax, x_vals)
            y_axis_label = f"{y_label}（{unit}）" if unit else y_label
            ax.set_title(title, color='white', fontsize=13, pad=10, fontweight='bold')
            ax.set_xlabel(x_label, color=_SUBTEXT, fontsize=10)
            ax.set_ylabel(y_axis_label, color=_SUBTEXT, fontsize=10)
            ax.tick_params(colors=_SUBTEXT, labelsize=9)
            for spine in ax.spines.values():
                spine.set_edgecolor(_GRID)
            ax.grid(axis='y', color=_GRID, linestyle='--', alpha=0.5)
        elif chart_type == "horizontal_bar":
            colors_h = ['#4488ff' if y >= 0 else '#ff4444' for y in y_vals]
            bars = ax.barh(x_vals, y_vals, color=colors_h, edgecolor='none', height=0.55)
            for bar, val in zip(bars, y_vals):
                ax.text(bar.get_width() * 1.01, bar.get_y() + bar.get_height() / 2,
                        f"{val:,.1f}", va='center', ha='left', color='white', fontsize=9)
            y_axis_label = f"{y_label}（{unit}）" if unit else y_label
            ax.set_title(title, color='white', fontsize=13, pad=10, fontweight='bold')
            ax.set_xlabel(x_label, color=_SUBTEXT, fontsize=10)
            ax.set_ylabel(y_axis_label, color=_SUBTEXT, fontsize=10)
            ax.tick_params(colors=_SUBTEXT, labelsize=9)
            for spine in ax.spines.values():
                spine.set_edgecolor(_GRID)
            ax.grid(axis='x', color=_GRID, linestyle='--', alpha=0.5)
        else:  # bar
            colors_b = ['#44cc66' if y >= 0 else '#ff4444' for y in y_vals]
            bars = ax.bar(range(len(x_vals)), y_vals, color=colors_b, edgecolor='none', width=0.6)
            for bar, val in zip(bars, y_vals):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.01,
                        f"{val:,.1f}", ha='center', va='bottom', color='white', fontsize=9)
            ax.set_xticks(range(len(x_vals)))
            _set_xticklabels_auto(ax, x_vals)
            y_axis_label = f"{y_label}（{unit}）" if unit else y_label
            ax.set_title(title, color='white', fontsize=13, pad=10, fontweight='bold')
            ax.set_xlabel(x_label, color=_SUBTEXT, fontsize=10)
            ax.set_ylabel(y_axis_label, color=_SUBTEXT, fontsize=10)
            ax.tick_params(colors=_SUBTEXT, labelsize=9)
            for spine in ax.spines.values():
                spine.set_edgecolor(_GRID)
            ax.grid(axis='y', color=_GRID, linestyle='--', alpha=0.5)

        if source and chart_type not in ('pie', 'table'):
            fig.text(0.98, 0.01, f"出典: {source}", ha='right', va='bottom',
                     color='#666688', fontsize=7)
        elif source:
            fig.text(0.99, 0.01, f"出典: {source}", ha='right', va='bottom',
                     color='#666688', fontsize=7)

        os.makedirs("output/charts", exist_ok=True)
        path = f"output/charts/data_chart_{idx}.png"
        fig.savefig(path, dpi=120, bbox_inches='tight',
                    facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        print(f"  データチャート生成: {path}（{title}）")
        return path
    except Exception as e:
        print(f"  [WARN] データチャートレンダリング失敗: {e}")
        return None


def _get_imagen_api_key() -> str:
    """Gemini API キーを取得する（複数の場所を順に確認）"""
    # 1. 環境変数（優先）
    key = os.environ.get("GEMINI_IMAGEN_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    # 2. 自プロジェクトの .env
    for env_path in [
        os.path.join(os.path.dirname(__file__), '..', '.env'),
        os.path.expanduser("~/investment-content-auto-1/.env"),
    ]:
        env_path = os.path.normpath(env_path)
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY=") or line.startswith("GEMINI_IMAGEN_API_KEY="):
                        key = line.split("=", 1)[1].strip()
                        if key:
                            return key
    return ""


def _insert_after_opinion_heading(draft: str, marker: str) -> tuple[str, bool]:
    """「## どんなニュース？」見出し直下にマーカーを挿入する（インフォグラフィック用）。
    見つからない場合は最初のH2にフォールバック。"""
    # 「## どんなニュース？」直下に挿入
    m_donnan = re.search(r'(?:^|\n)(## どんなニュース？)\n', draft)
    if m_donnan:
        insert_pos = m_donnan.end()
        new_draft = draft[:insert_pos] + marker + '\n' + draft[insert_pos:]
        return new_draft, True

    # フォールバック：最初のH2直下
    lines = draft.split('\n')
    new_lines = []
    inserted = False
    SKIP_PATTERNS = ('報じたこと', '注目すべき銘柄', 'ニュース速報', 'で、結局', '結局どう')
    for line in lines:
        new_lines.append(line)
        if not inserted and re.match(r'^##\s+[^#]', line):
            heading_text = re.sub(r'^##\s+', '', line).strip()
            if not any(p in heading_text for p in SKIP_PATTERNS):
                new_lines.append(marker)
                inserted = True
    return '\n'.join(new_lines), inserted


def generate_opinion_infographic(draft: str, section_num: int) -> str | None:
    """
    意見セクションの見出し・本文を読み取り、Gemini Imagen 4 でインフォグラフィックを生成する。
    """
    api_key = _get_imagen_api_key()
    if not api_key:
        print(f"  [SKIP] Imagen API キー未設定のためインフォグラフィックをスキップ")
        return None

    # 意見セクション（「が報じたこと」「注目すべき銘柄」以外の最初のH2）を抽出
    # ※ DOTALL時に .* が行を越えるため [^\n]* で行内のみチェック
    m = re.search(
        r'^(##\s+(?![^\n]*報じたこと)(?![^\n]*注目すべき銘柄)(?![^\n]*ニュース速報)[^\n]+)\n(.*?)(?=\n##\s|\Z)',
        draft, re.MULTILINE | re.DOTALL
    )
    if not m:
        print(f"  [SKIP] 意見セクションが見つからずインフォグラフィックをスキップ")
        return None

    opinion_heading = re.sub(r'^##\s+', '', m.group(1)).strip()
    opinion_text = m.group(2)[:1000]

    # 日本語プロンプトを直接生成（generate_images.pyのgenerate_image()を使用）
    # ※ Imagen経由の英語プロンプト方式は中国語文字化けが発生するため廃止
    prompt = f"""日本の投資ブログ（note.com）用インフォグラフィックを作成してください。

【見出し】{opinion_heading}

【記事の要点】
{opinion_text[:800]}

【デザイン要件】
- 横長16:9、プロフェッショナルな金融インフォグラフィック
- 上部に見出しタイトルを大きく配置
- 記事中の数値・データを3〜4点、色分けされたボックスに表示
- 矢印・アイコンで因果関係を視覚化
- テキスト・ラベル・数値はすべて日本語（ひらがな・カタカナ・漢字）で正確に記載
- 中国語・韓国語は使用しない。必ず日本語のみ
- テーマに合わせた配色（金利上昇=オレンジ/赤、AI=青/紫、景気後退=暗色）
- 新聞インフォグラフィック風レイアウト、白または薄グレー背景
- 具体的な数値・パーセントを必ず含める
"""

    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from generate_images import generate_image

        os.makedirs("output/images", exist_ok=True)
        today = datetime.datetime.now(JST).strftime("%Y%m%d")
        img_path = f"output/images/infographic_{today}_sec{section_num}.png"
        result = generate_image(prompt, img_path)
        if result:
            print(f"  インフォグラフィック生成完了: {img_path}")
            return result
        else:
            print(f"  [SKIP] インフォグラフィック生成失敗")
            return None
    except Exception as e:
        print(f"  [SKIP] インフォグラフィック生成エラー: {e}")
        return None


def generate_action_image(draft: str, section_num: int) -> str | None:
    """
    「## で、結局どう動けばいいの？」セクションの内容を読み取り、
    Gemini Imagen 4 で投資アクションを示す概念図を生成する。
    """
    api_key = _get_imagen_api_key()
    if not api_key:
        return None

    # 「で、結局どう動けばいいの？」セクションを抽出
    m = re.search(
        r'^(## で、結局どう動けばいいの？)\n(.*?)(?=\n##\s|\Z)',
        draft, re.MULTILINE | re.DOTALL
    )
    if not m:
        return None

    action_text = m.group(2)[:800]

    prompt = f"""日本の投資ブログ（note.com）用の「投資アクション提案」イメージ画像を作成してください。

【記事内容】
{action_text[:600]}

【デザイン要件】
- 横長16:9、プロフェッショナルな金融インフォグラフィック
- 「買い増し」「静観」「空売り検討」など、具体的な投資スタンスを大きく中央に表示
- 上昇/下落を示す矢印・チャートのシルエット・市場アイコンで方向性を視覚化
- テキスト・ラベルはすべて日本語（ひらがな・カタカナ・漢字）のみ
- 中国語・韓国語は使用しない
- 配色：買いスタンス=青/緑系、空売り=赤/オレンジ系、静観=グレー系
- スッキリとしたモダンなデザイン、文字は大きく読みやすく
"""

    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from generate_images import generate_image

        os.makedirs("output/images", exist_ok=True)
        today = datetime.datetime.now(JST).strftime("%Y%m%d")
        img_path = f"output/images/action_{today}_sec{section_num}.png"
        result = generate_image(prompt, img_path)
        if result:
            print(f"  アクション画像生成完了: {img_path}")
            return result
        return None
    except Exception as e:
        print(f"  [SKIP] アクション画像生成エラー: {e}")
        return None


def generate_data_charts(article_text: str, section_idx: int = 0) -> list[dict]:
    """
    記事内の [CHART: 説明] プレースホルダーを元にチャートを生成する。
    プレースホルダーがない場合はClaudeが自動抽出（最大4件）。
    戻り値: [{"path": str, "insert_after_keyword": str, "placeholder": str}, ...]
    """
    # [CHART: ...] プレースホルダーを記事から抽出
    chart_placeholders = re.findall(r'\[CHART:\s*([^\]]+)\]', article_text)

    if chart_placeholders:
        # プレースホルダーが存在する場合：それぞれについてデータを生成
        items_block = "\n".join(f"{i+1}. {desc}" for i, desc in enumerate(chart_placeholders[:4]))
        prompt = f"""以下の投資記事に挿入するグラフを{len(chart_placeholders[:4])}つ生成してください。

【グラフの指定】
{items_block}

【データ生成ルール】
- 公知データで構成できるものに限る（日銀・財務省・Bloomberg等の公開統計）
- 数値は実際に存在する概算値を使う（架空データ不可）
- chart_typeの選び方：推移・成長はline、比較・ランキングはbar、シェアはpie
- insert_after_keywordは記事中に実際に登場するキーワードを選ぶ
- **現在は2026年。2025年以前のデータはすべて確定値として扱い、「（予）」「（見込）」「（est）」等のマーク禁止。予測値として表記できるのは2027年以降のデータのみ。**

【出力形式】JSON配列のみ（前置き不要）:
[
  {{
    "placeholder": "元のCHARTプレースホルダー文字列（完全一致）",
    "chart_type": "line" | "bar" | "horizontal_bar" | "pie" | "table",
    "title": "グラフタイトル（日本語・20字以内）",
    "x_label": "横軸ラベル",
    "y_label": "縦軸ラベル",
    "unit": "単位",
    "data": [{{"x": "値", "y": 数値}}, ...],
    "series": [{{"name": "系列名", "data": [{{"x": "値", "y": 数値}}]}}],
    "source": "データ出典",
    "insert_after_keyword": "記事中のキーワード",
    "explanation": "このグラフから読み取れること・投資家への示唆を2〜3文で（ブロガー口調）"
  }}
]
※ 複数企業・複数指標を1つのグラフに重ねる場合は data の代わりに series を使うこと（例：トヨタとホンダの推移を1グラフに）。単一系列は data を使う。
※ explanation は必ず記入すること。「このグラフを見ると〜」「注目したいのは〜」など自然なブロガー口調で。

【記事】
{article_text[:3000]}"""
    else:
        # プレースホルダーなし：Claude が自動判断（最大4件）
        prompt = f"""以下の投資記事を読んで、グラフ・表で視覚化すると読者の理解が深まる数値データを**最大4つ**特定してください。

【条件】
- 企業・指標・市場の「規模の推移」「成長率」「シェア比較」「複数企業の比較」などを優先する
- 公知データで構成できるものに限る
- 時系列データは5〜15年の長期を使う。企業比較は5社以上を含める
- データが存在しない場合は空配列 [] を返す
- **現在は2026年。2025年以前のデータはすべて確定値として扱い、「（予）」「（見込）」「（est）」等のマーク禁止。予測値として表記できるのは2027年以降のデータのみ。**

【出力形式】JSON配列のみ（前置き不要）:
[
  {{
    "placeholder": "",
    "chart_type": "line" | "bar" | "horizontal_bar" | "pie" | "table",
    "title": "グラフタイトル（日本語・20字以内）",
    "x_label": "横軸ラベル",
    "y_label": "縦軸ラベル",
    "unit": "単位",
    "data": [{{"x": "値", "y": 数値}}, ...],
    "series": [{{"name": "系列名", "data": [{{"x": "値", "y": 数値}}]}}],
    "source": "データ出典",
    "insert_after_keyword": "記事中のキーワード",
    "explanation": "このグラフから読み取れること・投資家への示唆を2〜3文で（ブロガー口調）"
  }}
]
※ 複数企業・複数指標を1つのグラフに重ねる場合は data の代わりに series を使うこと（例：トヨタとホンダの推移を1グラフに）。単一系列は data を使う。
※ explanation は必ず記入すること。「このグラフを見ると〜」「注目したいのは〜」など自然なブロガー口調で。

【記事】
{article_text[:2500]}"""

    text = run_gemini(prompt)
    if not text:
        return []

    try:
        m = re.search(r'\[[\s\S]*\]', text)
        if not m:
            return []
        charts_spec = json.loads(m.group(0))
        if not isinstance(charts_spec, list):
            return []
    except Exception:
        return []

    results = []
    for i, spec in enumerate(charts_spec[:4]):
        path = _render_data_chart(spec, section_idx * 10 + i)
        if path:
            results.append({
                "path": path,
                "insert_after_keyword": spec.get("insert_after_keyword", ""),
                "placeholder": spec.get("placeholder", ""),
            })
    return results


def insert_data_charts_into_draft(draft: str, chart_infos: list[dict],
                                   existing_img_count: int) -> tuple[str, list[str]]:
    """データチャートを記事の適切な位置に __IMAGE_X__ として挿入する"""
    new_paths = []
    used_positions: list[int] = []
    MIN_GAP = 300

    def _is_too_close(pos: int) -> bool:
        return any(abs(pos - p) < MIN_GAP for p in used_positions)

    def _next_h2_after(pos: int) -> int:
        """pos以降の最初のH2見出しを探して返す（なければ末尾）"""
        m = re.search(r'\n## .+\n', draft[pos:])
        if m:
            return pos + m.end()
        return len(draft)

    for chart_idx, info in enumerate(chart_infos):
        path = info["path"]
        keyword = info.get("insert_after_keyword", "")
        placeholder = info.get("placeholder", "")
        img_idx = existing_img_count + len(new_paths)
        marker = f"__IMAGE_{img_idx}__"

        explanation = info.get("explanation", "").strip()
        # チャート挿入ブロック：マーカー + 解説文
        chart_block = f"\n\n{marker}\n\n{explanation}\n\n" if explanation else f"\n\n{marker}\n\n"

        # 最初の1枚は必ず「## 投資家はどこに注目すべきか？」見出し直下に配置する
        if chart_idx == 0:
            m_toushi = re.search(r'(?:^|\n)(## 投資家はどこに注目すべきか？)\n', draft)
            if m_toushi:
                # プレースホルダーがあれば除去してから挿入
                if placeholder:
                    full_tag = f"[CHART: {placeholder}]"
                    draft = re.sub(re.escape(full_tag), '', draft)
                insert_pos = m_toushi.end()
                draft = draft[:insert_pos] + chart_block + draft[insert_pos:]
                used_positions.append(insert_pos)
                new_paths.append(path)
                continue

        # [CHART: ...] プレースホルダーがある場合はその位置を特定
        ph_match = None
        if placeholder:
            full_tag = f"[CHART: {placeholder}]"
            m_exact = re.search(re.escape(full_tag), draft)
            if m_exact:
                ph_match = m_exact
            else:
                for ph_pattern in [re.escape(placeholder[:20]), re.escape(placeholder.split('（')[0])]:
                    m_partial = re.search(r'\[CHART:[^\]]*' + ph_pattern + r'[^\]]*\]', draft)
                    if m_partial:
                        ph_match = m_partial
                        break

        if ph_match and not _is_too_close(ph_match.start()):
            draft = draft[:ph_match.start()] + chart_block + draft[ph_match.end():]
            used_positions.append(ph_match.start())
            new_paths.append(path)
            continue
        elif ph_match:
            draft = draft[:ph_match.start()] + draft[ph_match.end():]

        # キーワードを含む段落末尾を探す
        insert_pos = None
        if keyword:
            kw_pos = draft.find(keyword)
            if kw_pos != -1:
                next_double_nl = draft.find('\n\n', kw_pos)
                candidate = next_double_nl if next_double_nl != -1 else kw_pos + len(keyword)
                if _is_too_close(candidate):
                    candidate = _next_h2_after(candidate)
                insert_pos = candidate

        if insert_pos is None:
            h2_matches = list(re.finditer(r'\n## .+\n', draft))
            for m2 in h2_matches:
                end_pos = m2.end()
                if not _is_too_close(end_pos):
                    insert_pos = end_pos
                    break
            if insert_pos is None:
                fallback = len(draft) * 2 // 3
                insert_pos = fallback if not _is_too_close(fallback) else len(draft)

        draft = draft[:insert_pos] + chart_block + draft[insert_pos:]
        used_positions.append(insert_pos)
        new_paths.append(path)

    return draft, new_paths


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


def inject_realtime_prices(draft: str, news: dict | None = None) -> str:
    """記事内の銘柄コードをもとにリアルタイム株価（+引け後はPTS/AH価格）を取得してClaudeで注入する"""
    # 日本株コード（4桁 or 285Aなど英数混在） 例：（8035）（285A）
    jp_codes = list(dict.fromkeys(re.findall(r'[（(](\d{3,4}[A-Z]?)[）)]', draft)))
    # 米国株ティッカー（大文字2〜5字） 例：NVDA、META、AAPL
    us_tickers = list(dict.fromkeys(re.findall(r'\b([A-Z]{2,5})\b', draft)))
    # 一般的な英単語を除外
    noise = {"AI", "FRB", "SOX", "ETF", "ADR", "GDP", "CPI", "BOJ", "USD", "JPY",
             "WTI", "PER", "PBR", "CFD", "ROE", "HBM", "DMA", "EV", "VIX", "PCR",
             "HBA", "PBR", "EPS", "M2", "PE", "QE", "US", "EU", "UK", "JP",
             "CHART", "DATA", "SKIP", "NOTE", "OK", "NG", "H2", "H3", "TOB",
             "YCC", "JST", "CEO", "CFO", "COO", "API", "PDF", "CSV", "URL"}
    us_tickers = [t for t in us_tickers if t not in noise][:5]

    price_lines = []
    today = datetime.datetime.now(JST)
    is_weekend = today.weekday() >= 5

    # ニュース発表タイミング（引け後かどうか）
    pub_dt = parse_jst(news.get('published', '')) if news else None
    total_min_now = today.hour * 60 + today.minute
    after_close = total_min_now >= 15 * 60 + 30  # 現在が引け後かどうか

    for code in jp_codes[:3]:
        price = get_realtime_price(code, is_jp=True)
        if price:
            label = f"週明け注目水準（直近終値）：{price}" if is_weekend else f"直近終値：{price}"
            # 引け後なら PTS 注記を追加
            pts_note = get_pts_price_note(code, is_jp=True, pub_dt=pub_dt) if after_close else ""
            if pts_note:
                price_lines.append(f"  {code}（東証）: {label} / {pts_note}")
            else:
                price_lines.append(f"  {code}（東証）: {label}")

    for ticker in us_tickers:
        price = get_realtime_price(ticker, is_jp=False)
        if price:
            pts_note = get_pts_price_note(ticker, is_jp=False, pub_dt=pub_dt) if after_close else ""
            if pts_note:
                price_lines.append(f"  {ticker}（米国）: 直近終値 {price} / {pts_note}")
            else:
                price_lines.append(f"  {ticker}（米国）: 直近終値 {price}")

    # 主要為替レートも取得してprice_linesに追加
    import yfinance as yf
    for fx_ticker, fx_label in [("USDJPY=X", "ドル円（USD/JPY）")]:
        try:
            hist = yf.Ticker(fx_ticker).history(period="2d").dropna(subset=["Close"])
            if not hist.empty:
                rate = hist["Close"].iloc[-1]
                price_lines.append(f"  {fx_label}：{rate:.2f}円")
        except Exception:
            pass

    if not price_lines:
        print("  [INFO] リアルタイム株価取得なし（銘柄コード未検出 or 取得失敗）")
        return draft

    price_block = "\n".join(price_lines)
    print(f"  リアルタイム株価取得:\n{price_block}")

    update_prompt = f"""以下の投資記事の株価・為替レートの数値を、提供したリアルタイムデータに更新してください。

【リアルタイム市場データ（{today.strftime('%Y年%m月%d日 %H:%M')} JST時点）】
{price_block}

【更新ルール】
- 「本日の株価：〇〇円前後」「週明けの注目水準：〇〇円前後」などの株価表記を実際の数値に更新
- ドル円・ユーロ円など為替レートが記事内に登場する場合は上記データの数値に更新する
- PTS/時間外取引（AH）データがある場合は、引け後の動きとして銘柄セクションに1文追加する
- 株価・為替以外の内容・構成・主張は一切変えない
- コメント・前置き不要。更新後の記事本文のみ出力

【記事】
{draft}"""

    updated = run_gemini(update_prompt)
    if updated and len(updated) >= len(draft) * 0.7:
        print(f"  株価注入完了（{len(draft)} → {len(updated)} 文字）")
        return clean_article(updated)
    print("  [WARN] 株価注入失敗、元の記事を使用")
    return draft


def select_topic(articles: list[dict]) -> dict:
    """ニュース一覧から最も注目度の高い1つのトピックを選定"""
    news_block = "\n".join(
        f"{i+1}. [{a['source']}] {a['title']}"
        for i, a in enumerate(articles[:20])
    )
    prompt = f"""以下のニュース一覧から、今日の日本の個人投資家に向けて記事にする1つのトピックを選定してください。

【選定ルール（優先度順）】
1. **市場インパクト最優先**：株急騰・急落・停戦・利上げ転換・関税・原油急変など相場の方向を変えるイベントは必ず最優先
2. **ニッチ性・バズりやすさを重視**：市場インパクトが同程度なら以下の条件でニッチ・バズり度が高い方を選ぶ
   - 「え、これって投資に関係あるの？」という意外な切り口があるニュース
   - 一般メディアがスルーしているが実は株価に直結するニュース
   - 「知らなかった」「なるほど」と思わせる業界・企業の裏側が見えるニュース
   - 「○○が××した結果、△△株が動く」という連鎖が読めるニュース
3. **具体性**：数値・銘柄・セクターへの影響が読み取れるニュースを優先
4. **除外**：単なる企業PRリリース・人事・無風な決算・マクロ総論のみのニュースは後回し

{news_block}

以下のJSON形式のみで回答してください（前置き不要）：
{{"index": <番号>, "title": "<ニュースタイトル>"}}"""

    text = run_gemini(prompt)
    if text:
        m = re.search(r'\{[^{}]+\}', text)
        if m:
            try:
                data = json.loads(m.group(0))
                idx = max(0, data["index"] - 1)
                return articles[min(idx, len(articles)-1)]
            except Exception as e:
                print(f"  [WARN] トピック選定パース失敗: {e}")

    # フォールバック：キーワードスコアリングで最重要ニュースを選定
    print("  [INFO] Claude CLI失敗のためキーワードスコアリングでフォールバック選定")
    high_impact = [
        # 地政学・停戦・戦争（最高優先）
        ("停戦", 60), ("ceasefire", 60), ("cease-fire", 60),
        # 相場急変
        ("急騰", 55), ("急落", 55), ("暴落", 55), ("暴騰", 55),
        ("plunge", 50), ("surge", 50), ("soar", 50), ("crash", 50), ("rally", 50),
        ("1400ドル", 55), ("1000ドル", 50), ("2000ドル", 55),
        # 金融政策
        ("利上げ", 50), ("利下げ", 50), ("rate hike", 50), ("rate cut", 50),
        ("FRB", 45), ("Fed ", 45), ("FOMC", 45), ("日銀", 45), ("BOJ", 45),
        # 地政学・資源
        ("原油", 45), ("oil", 40), ("イラン", 50), ("Iran", 50),
        ("ホルムズ", 55), ("Hormuz", 55),
        ("関税", 45), ("tariff", 45), ("制裁", 40),
        # 主要指数・市場
        ("NY株", 40), ("S&P", 35), ("Nasdaq", 35), ("ダウ", 35),
        ("停戦合意", 65),
    ]
    scored = []
    for art in articles:
        title = (art.get("title") or "") + " " + (art.get("summary") or "")
        score = 0
        for kw, pts in high_impact:
            if kw.lower() in title.lower():
                score += pts
        scored.append((score, art))
    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top_art = scored[0]
    print(f"  [INFO] フォールバック選定: スコア{top_score} → {top_art['title'][:60]}")
    return top_art


def select_multiple_topics(articles: list[dict], max_topics: int = 5) -> list[dict]:
    """ニュース一覧から「記事にする価値がある」トピックを必要な本数だけ選定する。
    AIニュース・トランプ関連を優先し、異なるカテゴリから選ぶ。"""
    news_block = "\n".join(
        f"{i+1}. [{a['source']}] {a['title']}"
        for i, a in enumerate(articles[:25])
    )
    # 直近7日間の記事タイトルを取得して重複を避ける
    recent_titles_block = ""
    try:
        import json as _json
        _perf_path = BASE_DIR / "data" / "article_performance.json"
        if _perf_path.exists():
            _data = _json.loads(_perf_path.read_text(encoding="utf-8"))
            _arts = _data if isinstance(_data, list) else _data.get("articles", [])
            _recent = [a.get("title", "") for a in _arts[-7:] if isinstance(a, dict) and a.get("title")]
            if _recent:
                recent_titles_block = "\n【過去7日間に執筆済み（重複禁止）】\n" + "\n".join(f"- {t}" for t in _recent) + "\n"
    except Exception:
        pass
    prompt = f"""以下のニュース一覧から、今日の日本の個人投資家が「読む価値がある」記事を執筆すべきトピックを選定してください。
{recent_titles_block}
【選定ルール（必ず守ること）】
- **必ず1本だけ選ぶ**。最も市場インパクトが大きいトピックを1つだけ選定する
- **過去7日間の記事と同じ企業・銘柄・テーマは絶対に選ばない**（読者が飽きる）
- 市場インパクト最優先：株急騰・急落・停戦・利上げ転換・原油急変・関税変更は必ず優先
- AI・トランプ・FRBのニュースは高優先だが、直近と同じ企業（NVIDIA・Intel等）は避ける
- 「それで何の銘柄が動くか」が明確なニュースを優先する
- 日本株・為替・原油・不動産など、AIと異なるジャンルも積極的に選ぶ
- 単なる企業IR・人事・軽微な決算は除外

{news_block}

以下のJSON形式のみで回答してください（前置き不要）：
{{"topics": [{{"index": <番号>, "title": "<ニュースタイトル>", "category": "AI|Trump|FRB|地政学|日本株|その他", "reason": "<選んだ理由1行>"}}]}}"""

    text = run_gemini(prompt)
    if text:
        m = re.search(r'\{[^{}]*"topics"[^{}]*\[.*?\]\s*\}', text, re.DOTALL)
        if not m:
            m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                topics_raw = data.get("topics", [])
                result = []
                seen_categories = set()
                for t in topics_raw[:max_topics]:
                    idx = max(0, int(t["index"]) - 1)
                    art = articles[min(idx, len(articles) - 1)]
                    cat = t.get("category", "その他")
                    if cat not in seen_categories:
                        result.append(art)
                        seen_categories.add(cat)
                if result:
                    print(f"  Claude選定: {len(result)}件（Claude判断）")
                    for r in result:
                        print(f"    - {r['title'][:60]}")
                    return result
            except Exception as e:
                print(f"  [WARN] 複数トピック選定パース失敗: {e}")

    # フォールバック：キーワードスコアリングで上位max_topics件（異なるカテゴリ）
    print("  [INFO] フォールバック: キーワードスコアリングで複数トピック選定")
    ai_kw = ["AI", "人工知能", "半導体", "NVIDIA", "エヌビディア", "OpenAI", "ChatGPT",
             "Meta", "Google", "Microsoft", "chip", "Gemini", "LLM", "GPU"]
    trump_kw = ["トランプ", "Trump", "関税", "tariff", "貿易", "trade war", "MAGA",
                "ホワイトハウス", "White House", "制裁", "sanction"]
    high_impact = [
        ("停戦", 60), ("ceasefire", 60), ("急騰", 55), ("急落", 55),
        ("暴落", 55), ("surge", 50), ("plunge", 50), ("crash", 50),
        ("利上げ", 50), ("利下げ", 50), ("FRB", 45), ("日銀", 45),
        ("原油", 45), ("関税", 45), ("tariff", 45), ("NY株", 40),
    ]
    scored = []
    for art in articles:
        title = (art.get("title") or "") + " " + (art.get("summary") or "")
        score = sum(pts for kw, pts in high_impact if kw.lower() in title.lower())
        is_ai = any(k.lower() in title.lower() for k in ai_kw)
        is_trump = any(k.lower() in title.lower() for k in trump_kw)
        cat = "AI" if is_ai else ("Trump" if is_trump else "その他")
        if is_ai:
            score += 60
        if is_trump:
            score += 60
        scored.append((score, cat, art))
    scored.sort(key=lambda x: x[0], reverse=True)

    # スコア閾値：60点以上 or AI/Trumpは無条件で選ぶ
    SCORE_THRESHOLD = 60
    result = []
    seen_cats: dict[str, int] = {}
    for score, cat, art in scored:
        effective_cat = cat if cat in ("AI", "Trump") else "その他"
        count = seen_cats.get(effective_cat, 0)
        limit = 1 if effective_cat in ("AI", "Trump") else max(1, max_topics - 2)
        # AI/Trumpは必ず1本、その他は閾値以上のみ
        if effective_cat in ("AI", "Trump") and count == 0:
            result.append(art)
            seen_cats[effective_cat] = 1
        elif effective_cat == "その他" and score >= SCORE_THRESHOLD and count < limit:
            result.append(art)
            seen_cats[effective_cat] = count + 1
        if len(result) >= max_topics:
            break
    if not result:
        result = [scored[0][2]] if scored else [articles[0]]
    print(f"  フォールバック選定: {len(result)}件")
    return result


def select_topics(articles: list[dict]) -> tuple[dict, dict]:
    """後方互換のため残存。内部でselect_topicを2回呼ぶ"""
    news1 = select_topic(articles)
    remaining = [a for a in articles if a is not news1]
    news2 = select_topic(remaining) if remaining else articles[min(1, len(articles)-1)]
    return news1, news2


def get_weekday_note() -> str:
    """曜日別の執筆注意文を返す"""
    today = datetime.datetime.now(JST)
    weekday = today.weekday()
    if weekday == 5:
        return "【執筆曜日：土曜日】「金曜引け後に〜する」など市場がすでに閉じた前提の短期行動指針は禁止。中長期の視点（数ヶ月〜数年単位）で書くこと。"
    elif weekday == 6:
        return "【執筆曜日：日曜日】市場は閉じており短期売買の話題は不適切。中長期の視点（数ヶ月〜数年単位）で書くこと。"
    else:
        return f"【執筆曜日：{'月火水木金'[weekday]}曜日】「今日の寄り付き」「今週中に〜」など短期・デイトレ目線の行動指針は禁止。中長期の視点（数ヶ月〜数年単位）で書くこと。"


def build_news_section_prompt(news: dict, section_num: int = 1, timing_context: str = "") -> str:
    """1ニュース分のセクション（3パート・合計2000字程度）の執筆プロンプト"""
    source = news.get('source', 'メディア')
    title_en = news['title']
    summary = news.get('summary', '')[:400]
    weekday_note = get_weekday_note()

    timing_block = f"\n{timing_context}\n" if timing_context else ""

    # 発表タイミング情報を抽出（文中に自然に溶け込ませるため）
    pub_hint = ""
    if timing_context:
        m = re.search(r'【情報発表タイミング：([^】]+)】', timing_context)
        if m:
            pub_hint = m.group(1).strip()

    timing_note = ""
    if pub_hint:
        timing_note = f"発表は{pub_hint}。市場への織り込み度合いにも触れること。ただし「〇〇が{pub_hint}に報じた内容によると」という形式的な書き出しは禁止。ブロガーの口調で自然に盛り込む。"

    today_str = datetime.datetime.now(JST).strftime('%m月%d日 %H:%M')

    # リアルタイム市場データ取得（為替・指数の誤数値防止）
    market_snapshot = get_market_snapshot()
    market_block = f"\n{market_snapshot}\n" if market_snapshot else ""

    return f"""note.com向けの投資解説記事を執筆してください。対象読者は個人投資家（中長期目線）。

{weekday_note}
{timing_block}
【記事執筆時刻】{today_str} JST（この時刻を基準に時間軸を書くこと）

【時間軸の表現ルール（必須）】
- 「〇月〇日にも発表」「〇月〇日に予定」などの表現は、その日付が執筆時刻より**未来**の場合のみ使う
- 執筆時刻より**過去・当日**の出来事は「本日〇時に発表された」「すでに〇日に明らかになった」など確定形で書く
- 執筆時刻と同日のイベントは「本日〇月〇日〇〇時頃に発表予定」「本日中に明らかになる見通し」など具体的な時刻・時間帯を添える

【取り上げるニュース】
ソース: {source}
タイトル: {title_en}
概要: {summary}
{timing_note}
{market_block}
【市場データの使い方（厳守）】
- 上記「主要市場データ」が取得できている場合：為替レート（ドル円など）・株価指数を記事内で数値で書く場合は、必ずその数値を使うこと。学習データに含まれる古いレートや指数値を使うことは厳禁。
- 上記データが空欄の場合：具体的な数値は書かず「最近のドル円は〜」などの表現も禁止。数値が必要な箇所は「現在のドル円水準」のような定性表現に留める。

【事実確認（最重要・必ず守ること）】
- 製品の発売状況・企業イベント・経済指標など、すでに起きた出来事は必ず過去形・現在完了形で書く
- 「発売される」「発売予定」など未来形は、執筆時点（{today_str}）より後の出来事にのみ使う
- 例：Nintendo Switch 2は2025年6月発売済み → 「発売されたのに」が正しく「発売されるのに」は誤り
- タイトルも本文も、現在の現実に即した時制を使うこと

【人物・役職の最新情報（絶対厳守）】
- ドナルド・トランプは2025年1月20日に第47代米国大統領として就任した現職大統領（2期目）である。「前大統領」「元大統領」と書くことは絶対禁止。「トランプ大統領」と書くこと。記事内に「現職」「元」などの注釈を付ける必要はない。
- トランプ政権は2期目（2025〜2029年）。3選禁止のため次の大統領選には出馬しない。「大統領選を意識した動き」など選挙目的の文脈は不適切なため使用禁止。
- カマラ・ハリスは現在「元副大統領」。バイデン氏は「元大統領」。この2人を現職と書くことは絶対禁止。

【論調・文体（最重要）】
- **全文を通じて個人ブロガーが友人に話すように書く**。「〜が報じた内容によると」などの形式的な書き出しは禁止
- 事実の説明も「AがBを発表した。これ、何が問題かというと〜」という展開にする
- 「これ、他人事じゃないんですよ」という接続で読者自身の資産・生活と結びつける一文を入れる
- 断言する。「〜の可能性があります」「〜かもしれません」は書かない
- 体言止め・短文を混ぜてリズムを作る（「これが怖い。」「本当に、そうなのか。」）

**【AI口調の徹底排除（最重要・全セクションに適用）】**
以下のような「報告書・教科書・ニュース記事調」の文体は**絶対禁止**。これが1文でもあればAI感が全開になる。

NG文体パターン（これらが出てきたら即書き直し）：
- 「〜においては」「〜に関連して」「〜の観点から」「〜を踏まえると」
- 「〜をもたらします」「〜に懸念をもたらします」「〜が明らかです」
- 「〜という点に着目する必要があります」「〜と言えるでしょう」「〜において重要です」
- 「この構造的な変化を理解することが〜上で最も重要です」← 典型的AI文
- 「地政学的なリスクを高めるだけでなく、グローバルなサプライチェーンの安定性にも〜」← 典型的AI文
- 「〜の一途を辿っており」「〜に至るまで」「〜を担っております」
- 「〜について解説します」「〜を見ていきましょう」「まとめると以下の通りです」
- 読点が4個以上ある長い複文（必ず2〜3文に分割する）

**【同じ言葉の繰り返し禁止（最重要・AI感の最大原因）】**
同じ単語を記事全体で3回以上使うことは禁止。特に以下の言葉は繰り返しやすいので積極的に言い換える：
- 「リスク」→ 「危うさ」「落とし穴」「怖いところ」「注意点」（3回目以降は言い換え必須）
- 「ポートフォリオ」→ 「持ち株の組み合わせ」「保有銘柄の配分」「どの株を何割持つか」
- 「バランス」→ 「偏りをなくす」「配分を整える」「分散する」
- 「〜という観点」「〜という側面」「〜という意味で」→ 使用禁止
- 「〜することが重要です」「〜することが大切です」→ 使用禁止（断言するか別の言い回しに）
- 「〜を考慮すると」「〜を勘案すると」→ 使用禁止

OK文体パターン（これを参考に書く）：
- 「実は〜なんですよ。」「どういうことかというと〜です。」「ざっくり言うと〜です。」「早い話が〜です。」
- 「なんでこれが問題かって言うと〜」「市場が気づいてないのは〜です。」
- 「〜なんですよね。」「〜なんですが、これが重要で。」「〜というか、要は〜です。」
- 「私はこう見ています。」「正直に言います。」「これは他人事ではありません。」

**【冒頭の決まり文句 絶対禁止】**
以下はくさい・使い古された表現として禁止する：
- NG：「このニュース、正直驚きました。」（毎回同じ出だし・くさい）
- NG：「これ、ヤバくないですか？」（安易な煽り）
- NG：「正直、驚きました。」
- 冒頭は事実・問い・結論のいずれかで始める。感情的な「驚き」表現は使わない

【口調（厳守）】
- **H2・H3見出し・本文すべて**：「です・ます」調で統一する
  - 本文良い例：「これは他人事ではありません。住宅ローンを組んでいる人なら〜」
  - 本文NG：「これは他人事ではない。」「〜だ。」「〜である。」（断言形は絶対禁止）
  - 見出し良い例：「## 日銀が動きました、その先に何があるのか」「## 不動産株が売られている本当の理由」
  - 見出しもNG：「## 日銀が動いた」「## 本当の理由はこれだ」（体言止め・断言形は禁止）
- **「ーー」などのダッシュ記号（―、—、ー）を2つ以上連続して使うことは絶対禁止**

【絶対ルール：H2見出しは以下の4つに完全固定。独自の見出しに変えることは厳禁】
- 1つ目のH2見出し：必ず「## どんなニュース？」（この文字列のみ）
- 2つ目のH2見出し：必ず「## 投資家はどこに注目すべきか？」（この文字列のみ）
- 3つ目のH2見出し：必ず「## で、結局どう動けばいいの？」（この文字列のみ）
- 4つ目のH2見出し（条件付き）：必ず「## このニュースで注目すべき銘柄」（この文字列のみ）
NG例：「## 黒字回復の裏で〜」「## ○○が動いた理由」など。見出しは上記4つ以外使用禁止。

【構成（この順番・このH2/H3で厳守）】

## どんなニュース？

**【絶対禁止・最重要】このセクションを空欄・省略してはならない。画像プレースホルダー(__IMAGE_N__)のみにすることも禁止。必ず300字程度の本文テキストを書くこと。このセクションに1文字も本文がない場合は執筆失敗とみなす。**
ブロガー口調で300字程度。「何が起きたか」を簡潔明瞭に伝える。
事実の報告のみに徹し、見立て・意見は「投資家はどこに注目すべきか？」に持ち越す。
H3小見出しは使わない。段落は1〜2つ。
**【必須・最初の文に以下を両方盛り込む】**
1. **情報源**：「{source}が」のように、どのメディアが報じたかを書く
2. **発表日時**：{pub_hint if pub_hint else "いつのニュースかを具体的に"}を自然に盛り込む
形式的な書き出し（「〜が報じた内容によると」）は禁止。ブロガー口調で一言で状況を伝える。
専門用語はカッコで即解説。このセクションだけ読んで「何が起きたか」が30秒でわかるようにする。

## 投資家はどこに注目すべきか？

**このセクションが記事の核心。要点を絞って端的に書く（700〜800字目安）。**
ブロガー口調（「〜だと思う」「〜と私は見ている」「正直に言う」）で、なぜそう考えるか理由・根拠を展開する。

【このセクションの執筆ルール】
- **700〜800字**。長々と書かず、要点だけを鋭く絞り込む。読者が離脱しないよう冗長な説明は省く
- **必ず2〜3個のH3（小見出し）で要点を分けて解説する**（ずらっと文章が続くと読者が離脱するため）
  - H3の例：「### 市場がまだ気づいていないポイント」「### なぜ今が重要なのか」「### 歴史はこう語っています」「### 反対意見への私の答え」
  - H3タイトルはニュース内容・文脈に合わせてその都度変えること（上記はあくまで例）
  - H3は「です・ます」調で、見出しを読むだけで内容が想像できるものにする
- **具体的な数値・データを必ず1〜2個含める**（例：「雇用者数が前月比+22.7万人」「市場予想+13.5万人を大幅上回った」）。これによりGeminiがグラフ・表を自動生成する
- 「なぜそうなるのか」の因果を1〜2ステップで簡潔に示し、結論を断言する
- 市場が見落としている視点・反対意見への反論も1〜2段落で掘り下げる
- 歴史的アナロジー（「リーマン前の〜」「あの時も〜」）を使って緊張感を演出する

## で、結局どう動けばいいの？

このニュースを踏まえて、筆者が「自分ならこう動く」という中長期的な視点でのアクションを書く。

【このセクションの執筆ルール】
- **400〜500字程度**。「自分ならこう動く」という一人称・ブロガー口調で書く
- **中長期目線（数ヶ月〜数年単位）で語ること。「月曜の寄り付き」「今週の値動き」「短期のトレード」など短期・デイトレ目線の表現は絶対禁止**
- 「このトレンドが続く間は保有を続ける」「数ヶ月単位で見れば〜」「長期的な構造変化として〜」など中長期の視点で断言する
- 根拠（数値・過去事例・ファンダメンタルズ・業界構造）を1〜2個添える
- テクニカル（エントリーポイント・損切りライン・チャートパターン）への言及は禁止（有料noteの内容）
- 末尾は読者が「自分も考えてみよう」と思えるような問いかけか、力強い一言で締める

## このニュースで注目すべき銘柄

**【重要】このセクションは原則として必ず作成する。`SKIP_STOCK_SECTION` を出力するのは、以下の「作成しない例」に明確に該当する場合のみとする。迷ったら必ず作成すること。**

【例外的にスキップする条件（これに明確に該当する場合のみ SKIP_STOCK_SECTION を出力する）】
- 単発の企業TOB・合併発表（すでに株価に全部織り込まれる）
- 決算の上振れ・下振れのみ（翌日に全部織り込まれる）
- 一過性の政治家スピーチ・発言（政策転換を伴わない）
- 株式市場と直接リンクしない話題（暗号資産のみ・スポーツ・芸能など）

【必ず作成する例（以下はすべて銘柄セクション対象）】
- 金利政策の大転換（FRB・日銀）→ 銀行・不動産セクター全体に波及
- FRBのバランスシート操作・QT・T-bill削減など流動性に関わる政策変化 → 銀行株に影響
- 関税・規制変更でサプライチェーン再編が始まる
- AI・EV・エネルギーなど構造転換を伴うトレンドの勃興
- 原油・資源価格の趨勢的な変化
- 大手企業の業績見通し変更でセクター全体のバリュエーションが変わる場合
- **大手テック企業への規制強化・独禁法適用・データ開放命令**（GOOGL・META・AMZNなど）→ 当該株に直接影響
- 為替の趨勢的な動き（介入警戒・政策変更を伴うもの）→ 輸出入企業に影響
- 地政学リスクの高まり（制裁・関税・戦争）→ エネルギー・防衛・資源株に影響

【作成条件（ガイドライン・参考程度）】
- 関連する実在の上場銘柄が1つでも存在すれば作成する（米国株は買い推奨のみ。空売り推奨は日本株に限る）
- 「まだ市場が完全に織り込んでいない可能性がある」と少しでも思えば作成する

---

このニュースで最も利益を大きく取れる銘柄を1つだけ取り上げる。

【銘柄選定の基準】
- **米国株（ティッカー）は買い（ロング）推奨のみ**。米国株で下落が見込まれる場合は、代わりに日本株の買い銘柄を探すか、銘柄セクション自体をスキップする
- **日本株（4桁コード）は買い・空売りどちらでも可**。相場環境・ニュースの性質に応じてケースバイケースで判断する
- 「このニュースで最も利益を大きく取れる銘柄」を選ぶ
- 空売りを取り上げる場合は「空売り狙い」と明記し、下落シナリオと根拠を説明する

### [銘柄名（証券コード or ティッカー）]

**【絶対禁止】架空・存在しない銘柄・証券コードを使うことは厳禁。「グローステック」「テックホールディングス」など実在しない企業名・9999など架空コードを書いてはならない。実在しない銘柄を選ぶくらいなら SKIP_STOCK_SECTION を出力すること。**

【銘柄セクションの書き方（必ず守ること）】
以下の6行だけを書くこと。それ以外の文章・説明・数値は一切追加しない。

▼ 出力すべき6行のテンプレート（〇〇は銘柄名に置き換える）
本日終値は〇〇円、前日比〇〇円（〇〇%）でした。
〇〇株は買い優勢でみています。（日本株のみ：空売り狙いの場合は「〇〇株は売り優勢でみています。」）
（空行）
◼︎なぜ今〇〇なのか？
◼︎具体的な利益目標水準
◼︎ポートフォリオへの組入れ比率
▲ テンプレートここまで（この6行のみ。追記一切禁止）

✅ 正しい出力例（任天堂・売り推奨の場合）：
本日終値は7,597円、前日比-241円（-2.82%）でした。
任天堂株は売り優勢でみています。

◼︎なぜ今任天堂なのか？
◼︎具体的な利益目標水準
◼︎ポートフォリオへの組入れ比率

❌ 絶対禁止：
- 4〜6行目（◼︎なぜ今〜／◼︎具体的な〜／◼︎ポートフォリオの〜）の後に説明・数値・内容を続けること
- 「---」区切り線（絶対禁止）
- 「などはこちらの記事で解説しているので是非参考にしてください。」（自動追加のため書かない）
- ファンダメンタルズ解説・チャート分析・テクニカル指標・目標株価の記述
- 米国株（ティッカー）で「売り優勢」と書くこと（米国株は買い推奨のみ）

【執筆ルール】
- 目標文字数：合計2000字以上（「どんなニュース？」は**300字程度**で簡潔に。「投資家はどこに注目すべきか？」は**700〜800字**で要点を絞って端的に。「で、結局どう動けばいいの？」は400字以上）
- 「行動の考え方」「おわりに」見出し禁止
- 絵文字禁止・個人プロフィール禁止
- 数字は具体的に（「大幅」ではなく「+3.5%」）
- **段落スペース（最重要）**：約200文字ごとに必ず1行分の空行（空の改行）を入れること。1段落の目安は150〜250文字。500文字以上を空行なしで続けるのは絶対禁止
- 1段落は最大3〜4文。それ以上になる場合は必ず段落を分けて空行を入れる（スマホ読者向け）
- 重要な結論・インパクトのある数字（例：4倍、750億円、+12%など）は必ず**太字**で強調する
- 各段落の冒頭か末尾に結論・数字を置き、斜め読みでも内容が伝わるようにする
- 記事本文のみ出力（前置き・後記・コメント不要）
- **「---」区切り線は絶対に使わない**
- **出力の末尾に「記事は〜に保存済みです」「合計〜字」「CHARTプレースホルダー〜箇所」などのメタコメントを一切付けない**
- 有料マガジンへの誘導文・URLは記事内に一切書かない
- 有料noteへの誘導文（「より詳しい売買シナリオは有料noteで」など）は記事内に一切書かない

【画像プレースホルダー（重要・必ず使うこと）】
- 文章で説明するより図解1枚の方が理解度が上がる箇所には、本文中に必ず `[CHART: 説明]` プレースホルダーを置く
- 最低2箇所以上、できれば3〜4箇所に挿入すること（これは必須。0個は執筆失敗と同義）
- プレースホルダーの書き方例：
  - `[CHART: 日銀の利上げ局面と不動産株の株価推移（2000年〜現在）]`
  - `[CHART: 長期金利2.4%突破後のセクター別株価変動シミュレーション]`
  - `[CHART: 不動産大手5社の有利子負債額と金利感応度比較]`
- 数値の比較・推移・因果構造・業界比較など、グラフや表で示せるものはすべてプレースホルダーにする

- 末尾: TOPIC_TAGS: タグ1,タグ2（為替/FRB/金利/決算/マクロ経済/エネルギー/半導体/日銀/円安/円高 から2つ）"""


def _validate_article(draft: str, skip_stock: bool) -> list[str]:
    """
    記事の全要件をチェックしてNG項目をログ出力する。
    修正を加えるたびに他が崩れないよう、ここで一括管理する。
    新ルールを追加したらこの関数にも必ず追加すること。
    """
    errors = []

    # ── 構造チェック ──
    if not re.search(r'^## どんなニュース？\s*$', draft, re.MULTILINE):
        errors.append("「## どんなニュース？」が存在しない")
    if not re.search(r'^## 投資家はどこに注目すべきか？\s*$', draft, re.MULTILINE):
        errors.append("「## 投資家はどこに注目すべきか？」が存在しない")
    if not re.search(r'^## で、結局どう動けばいいの？\s*$', draft, re.MULTILINE):
        errors.append("「## で、結局どう動けばいいの？」が存在しない")
    if not skip_stock and not re.search(r'^## このニュースで注目すべき銘柄\s*$', draft, re.MULTILINE):
        errors.append("「## このニュースで注目すべき銘柄」が存在しない（skip_stock=Falseなのに欠落）")

    # ── 「どんなニュース？」セクションの本文空欄チェック ──
    m_donnan = re.search(r'## どんなニュース？(.+?)(?=## 投資家はどこに注目すべきか？|$)', draft, re.DOTALL)
    if m_donnan:
        donnan_text = re.sub(r'__IMAGE_\d+__', '', m_donnan.group(1)).strip()
        if len(donnan_text) < 100:
            errors.append(f"「どんなニュース？」セクションの本文が空または極端に短い（{len(donnan_text)}字）。300字程度の本文を必ず書くこと")

    # ── 文字数チェック ──
    body_len = len(draft)
    if body_len < 2000:
        errors.append(f"文字数不足: {body_len}文字（最低2000文字必要）")

    # ── 段落スペースチェック（200文字ごとに空行） ──
    paragraphs = [p for p in draft.split('\n\n') if p.strip() and not p.startswith('#') and not p.startswith('__')]
    long_paras = [p for p in paragraphs if len(p) > 300]
    if len(long_paras) > 3:
        errors.append(f"300文字超の段落が{len(long_paras)}件（目安3件以下）: 改行スペースを増やすこと")

    # ── 禁止表現チェック ──
    if re.search(r'ーー|――|──', draft):
        errors.append("ダッシュ2連続（ーー/――/──）が含まれている")
    if re.search(r'---', draft):
        errors.append("区切り線「---」が含まれている")
    if re.search(r'解説します|見ていきましょう|まとめると以下', draft):
        errors.append("AI感のある定型表現が含まれている")
    if re.search(r'有料マガジン|me3bdb7d529fc', draft):
        errors.append("廃止済みの有料マガジン誘導文・URLが含まれている")

    # ── 架空銘柄チェック ──
    fake_codes = re.findall(r'[（(](?:証券コード[：:]?\s*)?(\d{4})[）)]', draft)
    known_fake = {'9999', '0000', '1234', '0001'}
    for code in fake_codes:
        if code in known_fake:
            errors.append(f"架空の証券コード「{code}」が含まれている → SKIP_STOCK_SECTIONに変更すること")
    fake_names = ['グローステック', 'テックホールディングス', 'ファイナンシャルテック', 'グローバルテック']
    for name in fake_names:
        if name in draft:
            errors.append(f"架空企業名「{name}」が含まれている → 実在銘柄か SKIP_STOCK_SECTION に変更すること")

    # ── 結果出力 ──
    if errors:
        print(f"\n  ⚠️  バリデーション: {len(errors)}件のNG")
        for e in errors:
            print(f"    ❌ {e}")
    else:
        print(f"  ✅ バリデーション: 全項目OK")

    return errors


def _align_stock_direction_with_title(draft: str, title: str) -> str:
    """タイトルの買い/売り方向と銘柄セクションの「買い優勢/売り優勢」が矛盾していれば修正する"""
    # タイトルの方向性を判定
    sell_keywords = ('空売り', '急落', '下落', '売られ', '売り圧')
    buy_keywords  = ('急伸', '急騰', '急浮上', '上昇', '浮上')

    title_direction = None
    for kw in sell_keywords:
        if kw in title:
            title_direction = 'sell'
            break
    if title_direction is None:
        for kw in buy_keywords:
            if kw in title:
                title_direction = 'buy'
                break

    if title_direction is None:
        return draft  # タイトルから方向性が読み取れない場合は変更しない

    # 銘柄が日本株か米国株かを判定（4桁数字コード → 日本株）
    h3_match = re.search(r'###\s+.+?[（(]([A-Z0-9]{1,6})[）)]', draft)
    stock_code = h3_match.group(1) if h3_match else ''
    is_jp_stock = stock_code.isdigit()

    # 銘柄セクション内の「買い優勢/売り優勢」行を検出
    buy_pattern  = re.compile(r'([^\n]+株は)買い優勢でみています。')
    sell_pattern = re.compile(r'([^\n]+株は)売り優勢でみています。')

    stock_has_buy  = bool(buy_pattern.search(draft))
    stock_has_sell = bool(sell_pattern.search(draft))

    if title_direction == 'sell' and stock_has_buy:
        if is_jp_stock:
            draft = buy_pattern.sub(r'\1売り優勢でみています。', draft)
            print(f"  [FIX] タイトルが売り方向のため銘柄セクションを「売り優勢」に統一しました")
        else:
            print(f"  [INFO] 米国株（{stock_code}）は売り推奨不可のため「買い優勢」を維持します")
    elif title_direction == 'buy' and stock_has_sell:
        draft = sell_pattern.sub(r'\1買い優勢でみています。', draft)
        print(f"  [FIX] タイトルが買い方向のため銘柄セクションを「買い優勢」に統一しました")

    return draft


def _sanitize_stock_section(draft: str) -> str:
    """銘柄セクションのフォーマットを強制修正する後処理。
    - 「なぜ今〜」「具体的な利益目標水準」「ポートフォリオへの組入れ比率」の各行直後の余分な説明文を除去
    - 銘柄セクション内の「---」区切り線を除去
    """
    m_sec = re.search(r'(## このニュースで注目すべき銘柄.*?)(\n## |\Z)', draft, re.DOTALL)
    if not m_sec:
        return draft

    section = m_sec.group(1)
    original = section

    # ---区切り線を除去
    section = re.sub(r'\n-{3,}\n?', '\n', section)

    # ◼︎なし版の古いテンプレート行があれば◼︎付きに統一
    section = re.sub(r'^(なぜ今)', r'◼︎\1', section, flags=re.MULTILINE)
    section = re.sub(r'^(具体的な利益目標水準)$', r'◼︎\1', section, flags=re.MULTILINE)
    section = re.sub(r'^(ポートフォリオへの組入れ比率)$', r'◼︎\1', section, flags=re.MULTILINE)

    # テンプレート行の直後にある余分な説明文をライン単位で除去
    TEMPLATE_MARKERS = ('◼︎なぜ今', '◼︎具体的な利益目標水準', '◼︎ポートフォリオへの組入れ比率')
    STRUCTURAL = ('##', '###', '__IMAGE', 'などはこちら')

    lines = section.split('\n')
    result = []
    skip_explanations = False

    for line in lines:
        is_template = any(line.startswith(m) for m in TEMPLATE_MARKERS)
        is_structural = any(line.startswith(s) for s in STRUCTURAL)

        if is_template:
            result.append(line)
            skip_explanations = True  # この行の後の説明文をスキップ開始
        elif skip_explanations:
            if line.strip() == '' or is_structural:
                # 空行または構造的な行でスキップ終了
                skip_explanations = False
                result.append(line)
            # else: 説明文行なのでスキップ
        else:
            result.append(line)

    new_section = '\n'.join(result)
    if new_section != section:
        print(f"  [FIX] 銘柄セクションの余分な説明文・区切り線を除去しました")
        draft = draft[:m_sec.start(1)] + new_section + draft[m_sec.start(2):]

    return draft


def self_review_article(draft: str, news: dict) -> str:
    """記事の自己添削：重要な視点の欠落・論理の一面性を検出して「投資家はどこに注目すべきか？」に追記する"""
    text_only = re.sub(r'__IMAGE_\d+__', '', draft).strip()
    news_summary = news.get("summary", "") or news.get("text", "")
    news_title = news.get("title", "")

    prompt = f"""あなたは投資記事の編集者です。以下の記事を添削してください。

【元のニュース・背景情報】
タイトル: {news_title}
概要: {news_summary[:800]}

【記事本文】
{text_only[:3500]}

【添削の観点】
この記事で示されている買い・売り方向と、その論理について：
1. 業界コスト構造（原材料費・部品コスト・製造コスト）で見落とされているリスクはないか？
2. マクロ要因（為替・関税・規制・金利・インフレ）で言及されていない重要な点はないか？
3. 企業固有の問題（利益率・在庫・ガイダンス・経営方針）で触れられていない点はないか？
4. 「好材料だから買い」「悪材料だから売り」という表面的な因果に留まっていないか？
   （例：Switch 2が売れていても、ハードウェアを原価割れで売っていれば売上≠利益）

以下の形式で厳密に出力してください（他の文章は一切出力しない）：

VERDICT: OK
または
VERDICT: NEEDS_REVISION

MISSING_POINTS:
（見落とされている重要な視点を1行ずつ列挙。なければ「なし」）

ADD_TO_INVESTORS_SECTION:
（「投資家はどこに注目すべきか？」セクション末尾に追記すべき内容を150〜250字・ブロガー口調・です・ます調で書く。追記不要なら「不要」）

REVISE_ACTION_SECTION:
（「で、結局どう動けばいいの？」の修正が必要な場合のみ修正後テキスト全体を書く。不要なら「不要」）"""

    result = run_claude(prompt, timeout=300)
    if not result:
        print("  [自己添削] タイムアウトまたはエラー → スキップ")
        return draft

    # VERDICT チェック
    if re.search(r'VERDICT:\s*OK', result):
        print("  [自己添削] 問題なし（修正不要）")
        return draft

    print("  [自己添削] 修正が必要な点を検出 → 追記します")

    # MISSING_POINTS をログ出力
    mp_match = re.search(r'MISSING_POINTS:\s*\n(.*?)(?=\nADD_TO_INVESTORS_SECTION:)', result, re.DOTALL)
    if mp_match:
        mp = mp_match.group(1).strip()
        if mp and mp != "なし":
            for line in mp.splitlines():
                if line.strip():
                    print(f"    [欠落視点] {line.strip()}")

    # ADD_TO_INVESTORS_SECTION を抽出して追記
    add_match = re.search(r'ADD_TO_INVESTORS_SECTION:\s*\n(.*?)(?=\nREVISE_ACTION_SECTION:|\Z)', result, re.DOTALL)
    add_text = add_match.group(1).strip() if add_match else ""
    if add_text and add_text != "不要":
        m = re.search(r'(## 投資家はどこに注目すべきか？.*?)(\n## )', draft, re.DOTALL)
        if m:
            insert_at = m.start(1) + len(m.group(1))
            draft = draft[:insert_at] + f"\n\n{add_text}\n" + draft[insert_at:]
            print(f"  [自己添削] 「投資家はどこに注目すべきか？」に{len(add_text)}字を追記しました")

    # REVISE_ACTION_SECTION を抽出して差し替え
    revise_match = re.search(r'REVISE_ACTION_SECTION:\s*\n(.*?)$', result, re.DOTALL)
    revise_text = revise_match.group(1).strip() if revise_match else ""
    if revise_text and revise_text != "不要":
        m_action = re.search(r'(## で、結局どう動けばいいの？)(.*?)(?=\n## |\Z)', draft, re.DOTALL)
        if m_action:
            # 画像マーカーは元のセクションから保持
            markers_in_action = re.findall(r'__IMAGE_\d+__', m_action.group(2))
            marker_block = ("\n\n" + markers_in_action[0]) if markers_in_action else ""
            new_section = f"## で、結局どう動けばいいの？{marker_block}\n\n{revise_text.strip()}"
            draft = draft[:m_action.start()] + new_section + draft[m_action.end():]
            print(f"  [自己添削] 「で、結局どう動けばいいの？」を修正しました")

    return draft


def write_news_section(news: dict, section_num: int) -> dict:
    """1ニュース分のセクションを執筆して返す"""
    timing_context = get_news_timing_context(news)
    if timing_context:
        print(f"  タイミング解析: {timing_context[:60]}...")
    prompt = build_news_section_prompt(news, section_num, timing_context)

    print(f"  Gemini でセクション{section_num}執筆中...")
    draft = run_gemini(prompt)

    if not draft:
        raise RuntimeError(f"セクション{section_num}の執筆に失敗しました")

    print(f"  執筆完了（{len(draft)} 文字）")

    # 文字数チェック：2000字未満なら加筆リクエスト（最大1回）
    if len(draft) < 1800:
        print(f"  [WARN] 文字数不足（{len(draft)}字）→ 加筆リクエスト中...")
        # SKIP_STOCK_SECTIONを除去してから加筆用に渡す（誤引継ぎ防止）
        draft_for_expand = re.sub(r'SKIP_STOCK_SECTION', '', draft).strip()
        expand_prompt = f"""以下の投資記事は{len(draft_for_expand)}文字しかありません。最低2000文字になるよう加筆してください。

【加筆の方針】
- 既存の内容・構成・H2見出し（「どんなニュース？」「投資家はどこに注目すべきか？」「で、結局どう動けばいいの？」「このニュースで注目すべき銘柄」）は絶対に変えない
- 「で、結局どう動けばいいの？」セクションが薄い場合は具体的なアクション・視点を補足する
- ブロガー口調を維持する
- TOPIC_TAGSの行は出力しない
- 銘柄セクションが必要な場合は「## このニュースで注目すべき銘柄」見出しを追加し、不要な場合は「SKIP_STOCK_SECTION」を末尾に出力する

【現在の記事】
{draft_for_expand}

記事全文のみ出力（コメント・前置き不要）。"""
        expanded = run_gemini(expand_prompt)
        if expanded and len(expanded) > len(draft_for_expand):
            draft = expanded
            print(f"  加筆後: {len(draft)} 文字")

    # H2見出しの正規化：「どんなニュース？」が存在しない場合は修正
    if not re.search(r'^## どんなニュース', draft, re.MULTILINE):
        # ケース①：最初のH2が投資家/で、結局/このニュース以外 → 置換
        replaced = re.sub(
            r'^(## (?!投資家|で、結局|このニュース).+)$',
            '## どんなニュース？',
            draft, count=1, flags=re.MULTILINE
        )
        if replaced != draft:
            draft = replaced
            print(f"  [FIX] H2見出しを「どんなニュース？」に修正しました")
        else:
            # ケース②：最初のH2が「投資家…」など → その直前に「どんなニュース？」セクションを挿入
            m_first_h2 = re.search(r'^## ', draft, re.MULTILINE)
            if m_first_h2:
                insert_pos = m_first_h2.start()
                draft = draft[:insert_pos] + "## どんなニュース？\n\n" + draft[insert_pos:]
                print(f"  [FIX] 「どんなニュース？」セクションが欠落していたため先頭に挿入しました")

    # 構造修正：「## どんなニュース？」の前にH3見出しや本文が来ていないかチェック
    # （Claudeが見出し順序を無視してH3+本文を先に書いてしまうケースへの対処）
    m_donnan = re.search(r'^## どんなニュース？', draft, re.MULTILINE)
    if m_donnan and m_donnan.start() > 0:
        before_donnan = draft[:m_donnan.start()]
        # H3またはH2が現れる前の内容だけを「掴み文」とみなす
        m_heading_before = re.search(r'^(##|###)', before_donnan, re.MULTILINE)
        if m_heading_before:
            hook_text = before_donnan[:m_heading_before.start()].strip()
            misplaced_text = before_donnan[m_heading_before.start():].strip()
            after_donnan_and_rest = draft[m_donnan.start():]
            # 「## どんなニュース？\n」の直後に misplaced コンテンツを移動
            nl_pos = after_donnan_and_rest.find('\n') + 1
            draft = (
                hook_text + '\n\n'
                + after_donnan_and_rest[:nl_pos]
                + '\n' + misplaced_text + '\n\n'
                + after_donnan_and_rest[nl_pos:]
            )
            print(f"  [FIX] 「どんなニュース？」前の本文({len(misplaced_text)}字)を見出し後に移動しました")

    # 銘柄セクションをスキップするか判定
    skip_stock = bool(re.search(r'SKIP_STOCK_SECTION', draft))
    if skip_stock:
        draft = re.sub(r'SKIP_STOCK_SECTION', '', draft).strip()
        print(f"  [INFO] 銘柄セクションなし（条件未達）→ 有料note生成もスキップ")

    # TOPIC_TAGS: 抽出
    topic_tags = []
    tags_match = re.search(r'TOPIC_TAGS:\s*(.+)$', draft, re.MULTILINE)
    if tags_match:
        raw = [t.strip() for t in tags_match.group(1).split(',')]
        topic_tags = [t for t in raw if t in TOPIC_TAGS_OPTIONS][:2]
        draft = re.sub(r'TOPIC_TAGS:\s*.+$', '', draft, flags=re.MULTILINE).strip()

    draft = clean_article(draft)

    # [CHART: ...] 残存プレースホルダーを除去してから株価注入（誤ティッカー検知防止）
    draft = re.sub(r'\[CHART:[^\]]*\]', '', draft)

    # リアルタイム株価を注入（引け後はPTS/AH価格も含む）
    print(f"  リアルタイム株価を取得・注入中...")
    draft = inject_realtime_prices(draft, news=news)

    # 銘柄チャートを生成してマーカーを挿入
    print(f"  銘柄チャートを生成中...")
    draft, image_paths = inject_stock_charts(draft)

    # ① データチャートを記事の適切な位置に挿入
    print(f"  データチャートを生成中...")
    chart_infos = generate_data_charts(draft, section_num)
    if chart_infos:
        draft, chart_paths = insert_data_charts_into_draft(draft, chart_infos, len(image_paths))
        image_paths = image_paths + chart_paths
        print(f"  データチャート {len(chart_paths)} 枚を挿入（計{len(image_paths)}枚）")

    # ② ニュースソース引用画像がある場合は先頭に挿入（インデックスをずらす）
    news_img_path = download_news_image(news.get("image_url", ""), section_num)
    if news_img_path:
        # 既存の __IMAGE_n__ インデックスを1つずつ繰り上げ
        draft = re.sub(r'__IMAGE_(\d+)__', lambda m: f'__IMAGE_{int(m.group(1)) + 1}__', draft)
        image_paths = [news_img_path] + image_paths
        # 最初のH1見出し行の直後に __IMAGE_0__ を挿入
        draft = re.sub(r'(^# .+$)', r'\1\n\n__IMAGE_0__', draft, count=1, flags=re.MULTILINE)
        print(f"  ニュース引用画像を先頭に挿入（計{len(image_paths)}枚）")

    # ③ 意見セクション直下にインフォグラフィックを挿入
    print(f"  意見セクションのインフォグラフィックを生成中...")
    infographic_path = generate_opinion_infographic(draft, section_num)
    if infographic_path:
        infographic_idx = len(image_paths)
        draft, inserted = _insert_after_opinion_heading(draft, f'__IMAGE_{infographic_idx}__')
        if not inserted:
            # フォールバック：先頭のH2直後に強制挿入
            first_h2 = re.search(r'(?:^|\n)(## .+)\n', draft)
            if first_h2:
                ip = first_h2.end()
                draft = draft[:ip] + f'__IMAGE_{infographic_idx}__\n\n' + draft[ip:]
                inserted = True
        if inserted:
            image_paths = image_paths + [infographic_path]
            print(f"  インフォグラフィックを挿入（index={infographic_idx}）")
        else:
            print(f"  [WARN] インフォグラフィック挿入位置が見つからずスキップ")

    # ③-b 「で、結局どう動けばいいの？」セクション用アクション画像を常に生成
    print(f"  アクション画像を生成中（「で、結局どう動けばいいの？」セクション用）...")
    action_path = generate_action_image(draft, section_num)
    if action_path:
        action_idx = len(image_paths)
        # 「## で、結局どう動けばいいの？」の直後に挿入
        m_action = re.search(r'(?:^|\n)(## で、結局どう動けばいいの？)\n', draft)
        if m_action:
            ip = m_action.end()
            draft = draft[:ip] + f'__IMAGE_{action_idx}__\n\n' + draft[ip:]
            image_paths = image_paths + [action_path]
            print(f"  アクション画像を「で、結局どう動けばいいの？」直下に挿入（index={action_idx}）")
        else:
            # フォールバック：末尾に追加
            draft = draft.rstrip() + f'\n\n__IMAGE_{action_idx}__\n'
            image_paths = image_paths + [action_path]
            print(f"  アクション画像を末尾に挿入（index={action_idx}）")

    # ④ 画像配置をレビューして最適な位置に修正
    draft = review_image_placement(draft, image_paths)

    # ⑤ プログラム的にデータチャートを銘柄セクションから確実に追い出す
    draft = _fix_data_charts_in_stock_section(draft, image_paths)

    # ⑥ インフォグラフィック（infographic_*.png）を「## どんなニュース？」直下に強制配置（review後に再実行）
    infographic_idx = next(
        (i for i, p in enumerate(image_paths) if re.search(r'infographic_', p)),
        None
    )
    if infographic_idx is not None:
        infographic_marker = f"__IMAGE_{infographic_idx}__"
        donnan_match = re.search(r'(?:^|\n)(## どんなニュース？)\n', draft)
        if donnan_match:
            insert_after_donnan = donnan_match.end()
            after_text = draft[insert_after_donnan:insert_after_donnan + 80].strip()
            marker_after_donnan = after_text.startswith(infographic_marker)
        else:
            marker_after_donnan = False
        if donnan_match and not marker_after_donnan:
            draft = re.sub(r'\n*' + re.escape(infographic_marker) + r'\n*', '\n\n', draft)
            donnan_match2 = re.search(r'(?:^|\n)(## どんなニュース？)\n', draft)
            if donnan_match2:
                ip = donnan_match2.end()
                draft = draft[:ip] + f"\n\n{infographic_marker}\n\n" + draft[ip:]
                print(f"  [FIX] {infographic_marker} をどんなニュース？直下に再配置")

    # ★ 「どんなニュース？」セクションが空の場合は自動補完
    m_donnan_check = re.search(r'## どんなニュース？(.+?)(?=## 投資家はどこに注目すべきか？|$)', draft, re.DOTALL)
    if m_donnan_check:
        donnan_body = re.sub(r'__IMAGE_\d+__', '', m_donnan_check.group(1)).strip()
        if len(donnan_body) < 80:
            print("  [FIX] どんなニュース？セクションが空 -> 自動補完")
            _news_title = news.get("title", "")
            _news_summary = news.get("summary", "") or news.get("text", "")
            _news_source = news.get("source", "")
            _fill_prompt = (
                "以下のニュースについて「どんなニュース？」の本文を300字程度で書いてください。\n\n"
                f"情報源: {_news_source}\n"
                f"タイトル: {_news_title}\n"
                f"概要: {_news_summary[:400]}\n\n"
                "ルール: ブロガー口調(です・ます)で300字程度。"
                f"最初の文に「{_news_source}が報じた」のように情報源を自然に盛り込む。"
                "何が起きたかを簡潔に。意見は書かない。H3小見出しは使わない。本文テキストのみ出力。"
            )
            _fill_text = run_gemini(_fill_prompt)
            if _fill_text and len(_fill_text.strip()) > 50:
                _existing = m_donnan_check.group(1)
                _markers = re.findall(r'__IMAGE_\d+__', _existing)
                _new_sec = '\n\n' + _fill_text.strip() + '\n\n'
                if _markers:
                    _new_sec = '\n\n' + _markers[0] + '\n\n' + _fill_text.strip() + '\n\n'
                draft = draft[:m_donnan_check.start(1)] + _new_sec + draft[m_donnan_check.end(1):]
                print(f"  [FIX] どんなニュース？に{len(_fill_text.strip())}字を補完しました")

    # ★ 銘柄セクションの後処理：余分な説明行と---区切り線を除去
    draft = _sanitize_stock_section(draft)

    # ★ 自己添削：論理の抜けや一面的な分析を確認・修正
    print(f"  自己添削中...")
    draft = self_review_article(draft, news)

    # ★ 最終バリデーション：全要件を一括チェック
    val_errors = _validate_article(draft, skip_stock)

    # ★ 銘柄セクション欠落リトライ：skip_stock=False なのに欠落している場合は補完
    stock_missing = any("このニュースで注目すべき銘柄" in e for e in val_errors)
    if stock_missing and not skip_stock:
        print("  [RETRY] 銘柄セクションが欠落 → Claude で補完します...")
        try:
            stock_prompt = (
                f"以下の投資記事の末尾に「## このニュースで注目すべき銘柄」セクションを追加してください。\n\n"
                f"【記事本文】\n{draft[:3000]}\n\n"
                f"【追加ルール】\n"
                f"- 必ず実在する銘柄（日本株4桁コードまたは米国株ティッカー）を1つ選ぶ\n"
                f"- 書式: ## このニュースで注目すべき銘柄\n### 銘柄名（コード）\n本日終値は〇〇円でした。\n〇〇株は買い優勢でみています。\n\nなぜ今〇〇なのか？\n具体的な利益目標水準\nポートフォリオへの組入れ比率\n"
                f"- 記事のテーマに直結した銘柄を選ぶ\n"
                f"- 銘柄セクションのみを出力（記事全体を再出力しない）"
            )
            stock_section = run_claude(stock_prompt, timeout=120)
            if stock_section and "## このニュースで注目すべき銘柄" in stock_section:
                # X告知セクションの前に挿入
                x_idx = draft.find("## 📢")
                if x_idx > 0:
                    draft = draft[:x_idx].rstrip() + "\n\n" + stock_section.strip() + "\n\n" + draft[x_idx:]
                else:
                    draft = draft.rstrip() + "\n\n" + stock_section.strip()
                skip_stock = False
                print("  [RETRY] 銘柄セクション補完完了")
            else:
                print("  [RETRY] 補完失敗 → スキップ扱いに変更")
                skip_stock = True
        except Exception as _e:
            print(f"  [RETRY] 補完エラー: {_e} → スキップ扱いに変更")
            skip_stock = True

    return {
        "text": draft,
        "image_paths": image_paths,
        "topic_tags": topic_tags,
        "skip_stock": skip_stock,
    }


def _fix_data_charts_in_stock_section(draft: str, image_paths: list) -> str:
    """データチャートが銘柄セクションに入っていたら確実に前のセクションへ移動する（プログラム的処理）"""
    # データチャートのマーカー番号を特定
    data_chart_markers = set()
    for i, path in enumerate(image_paths):
        fname = os.path.basename(path)
        if fname.startswith('data_chart_'):
            data_chart_markers.add(f'__IMAGE_{i}__')

    if not data_chart_markers:
        return draft

    # 銘柄セクションの開始位置を特定
    stock_h2 = re.search(r'^## このニュースで注目すべき銘柄', draft, re.MULTILINE)
    if not stock_h2:
        return draft

    stock_start = stock_h2.start()
    before = draft[:stock_start]
    after = draft[stock_start:]

    # 銘柄セクション内のデータチャートマーカーを抽出・削除
    misplaced = []
    for marker in data_chart_markers:
        if marker in after:
            after = re.sub(r'\n*' + re.escape(marker) + r'\n*', '\n\n', after)
            misplaced.append(marker)

    if not misplaced:
        return draft

    print(f"  [FIX] データチャート {misplaced} を銘柄セクションから移動")

    # 「投資家はどこに注目すべきか？」セクションの末尾（次のH2の直前）に追加
    opinion_end = re.search(r'\n## (?!投資家はどこに注目すべきか).+', before)
    insert_pos = opinion_end.start() if opinion_end else stock_start

    # 「で、結局どう動けばいいの？」の直前に挿入（最後のH2の1つ前）
    all_h2 = list(re.finditer(r'\n## ', before))
    if len(all_h2) >= 2:
        insert_pos = all_h2[-1].start()

    marker_block = '\n\n' + '\n\n'.join(misplaced) + '\n\n'
    before = before[:insert_pos] + marker_block + before[insert_pos:]

    return before + after


def review_image_placement(draft: str, image_paths: list) -> str:
    """記事中の__IMAGE_X__マーカー配置をClaudeが見直して最適な位置に修正する。

    問題パターン：
    - H2/H3見出し直後に複数の画像が連続している
    - データチャートが銘柄セクション（## このニュースで注目すべき銘柄）に置かれている
    - 同じ場所に画像が集中している
    """
    markers = re.findall(r'__IMAGE_\d+__', draft)
    if not markers:
        return draft

    print(f"  [FIX] 画像配置を見直し中（{len(markers)}枚）...")

    # 各__IMAGE_X__が何のファイルかの情報をプロンプトに渡す
    image_info_lines = []
    for i, path in enumerate(image_paths):
        fname = os.path.basename(path)
        if 'infographic' in fname:
            kind = 'インフォグラフィック（意見セクション用）'
        elif '_chart' in fname and not fname.startswith('data_'):
            code = fname.replace('_chart.png', '')
            kind = f'銘柄チャート（{code}の株価ローソク足）→ 銘柄セクションのH3直下に置く'
        elif fname.startswith('data_chart_'):
            kind = 'データチャート（本文中の数値データの可視化）→ 銘柄セクション以外に置く'
        else:
            kind = fname
        image_info_lines.append(f"  __IMAGE_{i}__: {fname}（{kind}）")
    image_info = '\n'.join(image_info_lines)

    prompt = f"""以下の投資記事の画像マーカー（__IMAGE_X__）の配置を見直して、最適な位置に移動してください。

【各画像の内容】
{image_info}

【配置ルール】
1. **インフォグラフィック（infographic_*.png）** は「## どんなニュース？」見出しの直後に配置する
2. **データチャート（data_chart_*.png）** は「## 投資家はどこに注目すべきか？」セクションの、そのデータと関連する段落の直後に配置する。「## このニュースで注目すべき銘柄」セクションには置かない
3. **銘柄チャート（コード_chart.png）** は対応する「### 銘柄名（コード）」見出しの**直下**（H3の次の行）に配置する
4. H2見出しの直後（本文がない状態）に画像を置かない（H3直下への銘柄チャート配置はこのルールの例外）
5. 複数の画像を連続して置かない（画像と画像の間に必ず文章を挟む）
6. __IMAGE_X__のX番号は絶対に変えない
7. 全てのマーカー（{', '.join(markers)}）を必ず全部残す（削除・追加禁止）
8. H2見出し・H3見出し・本文のテキストは変えない
9. TOPIC_TAGSの行は出力しない（削除済み）

【現在の記事】
{draft}

修正後の記事全文のみ出力（コメント・前置き・説明不要）。"""

    result = run_gemini(prompt)
    if not result:
        print(f"  [WARN] 画像配置レビュー: Claude応答なし → 元の配置を維持")
        return draft

    # マーカーが全て残っているか確認
    result_markers = sorted(re.findall(r'__IMAGE_\d+__', result))
    original_markers = sorted(markers)
    if result_markers != original_markers:
        print(f"  [WARN] 画像配置レビュー: マーカー数が変化したため元の配置を維持 (before={original_markers}, after={result_markers})")
        return draft

    # 極端に短くなっていないか確認（元の80%以上の文字数）
    if len(result) < len(draft) * 0.8:
        print(f"  [WARN] 画像配置レビュー: 文字数が大幅減少（{len(draft)}→{len(result)}）のため元の配置を維持")
        return draft

    print(f"  画像配置レビュー完了（{len(markers)}枚を最適配置）")
    return result


def generate_hook(article_text: str) -> str:
    """記事冒頭の「結論ファースト」文（1〜2文）を生成する"""
    prompt = f"""以下の投資記事を読んで、冒頭に置く「結論ファースト」の文を1〜2文で書いてください。

要件：
- **1文で1つの結論だけ**言う。2つのテーマを1文に詰め込まない
- **企業名・銘柄名・数字のどれか1つ以上**を必ず含める（抽象的な表現は禁止）
  - NG：「テック業界全体のサプライチェーンに潜む致命的な問題を確信しました。」（抽象的・何の話かわからない）
  - OK：「AppleがTSMCへの依存を断ち切り始めました。持っている人は今すぐ確認してほしい銘柄があります。」
  - OK：「円が158円を超えました。これ、トヨタより先に動くべき銘柄があります。」
- **読者自身の資産・行動**に引きつける（「持っている人は」「今すぐ〇〇すべき」「日本株にも直撃」等）
- 「なぜそうなのか？」の理由は絶対に書かない（本文の役目）。結論・行動だけ先に伝える
- テンプレートの使い回し禁止。記事の固有名詞・数字・状況に完全に沿った一点もの表現にする
- 「ちょっと待って」「待ってほしいんです」「このニュース、投資家にとって絶対に見逃せません。」などの汎用フレーズは絶対禁止
- 「〜を確信しました」「〜という問題」「〜という状況」などの抽象的な締め方も禁止
- です・ます調で統一（断言形「〜だ」「〜である」は禁止）
- 50〜80字程度・専門用語なし
- 「ーー」などのダッシュ記号は絶対に使わない
- 文のみ出力（前置き・説明不要）

【記事（抜粋）】
{article_text[:800]}"""

    result = run_gemini(prompt)
    if result:
        return result.strip()

    # フォールバック：記事の最初の文
    clean = re.sub(r'^#{1,3}\s+.+$', '', article_text, flags=re.MULTILINE).strip()
    m = re.search(r'[。！？]', clean[:200])
    return clean[:m.end()] if m else clean[:100]


def generate_summary(sec1_text: str, sec2_text: str) -> str:
    """後方互換。generate_hookを使う"""
    return generate_hook(sec1_text)


def generate_title(article_text: str, news_title: str) -> str:
    """記事本文からクリックされる具体的なタイトルをClaudeが生成する"""
    import re as _re

    # 銘柄セクションから銘柄名・コードを抽出
    stock_name = ""
    stock_code = ""
    stock_section = ""
    m_sec = _re.search(r'## このニュースで注目すべき銘柄(.+?)(?=^## |\Z)', article_text, _re.DOTALL | _re.MULTILINE)
    if m_sec:
        stock_section = m_sec.group(1)[:400]
        m_h3 = _re.search(r'^### (.+?)$', stock_section, _re.MULTILINE)
        if m_h3:
            h3_text = m_h3.group(1)
            # "企業名（コード）" → コードを抽出
            m_code = _re.search(r'[（(]([A-Z0-9]{1,6})[）)]', h3_text)
            if m_code:
                stock_code = m_code.group(1)
            # "企業名（コード）" → "企業名" だけ取り出す
            stock_name = _re.sub(r'[（(][^）)]+[）)]', '', h3_text).strip()

    # yfinanceで直近5日間の値動きを取得して方向性を判定
    price_direction = "unknown"
    price_change_pct = None
    if stock_code:
        try:
            import yfinance as yf
            ticker = stock_code + ".T" if stock_code.isdigit() else stock_code
            hist = yf.Ticker(ticker).history(period="5d")
            closes = hist['Close'].dropna()
            if len(closes) >= 2:
                price_change_pct = (closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100
                if price_change_pct >= 5:
                    price_direction = "big_up"
                elif price_change_pct >= 2:
                    price_direction = "up"
                elif price_change_pct <= -5:
                    price_direction = "big_down"
                elif price_change_pct <= -2:
                    price_direction = "down"
                else:
                    price_direction = "neutral"
        except Exception:
            pass

    # 値動き情報をプロンプトに注入
    if price_change_pct is not None:
        pct_str = f"{price_change_pct:+.1f}%"
        if price_direction == "big_up":
            price_context = (
                f"【⚠️ 値動き確認済み・必須】{stock_name}株は直近5日で{pct_str}の急伸中。"
                f"タイトルには「急伸」「急騰」「急浮上」などの上昇表現を使うこと。"
            )
            format_examples = (
                f"- 「なぜ{stock_name}株は急伸したのか？」\n"
                f"- 「〇〇の裏で急浮上する{stock_name}株」\n"
                f"- 「〇〇が起きると、なぜ{stock_name}株が急騰するのか？」"
            )
        elif price_direction == "up":
            price_context = (
                f"【⚠️ 値動き確認済み・必須】{stock_name}株は直近5日で{pct_str}の上昇中。"
                f"タイトルには「上昇」「注目」「浮上」などの表現を使うこと。「急伸」「急騰」は使わないこと。"
            )
            format_examples = (
                f"- 「{stock_name}株が静かに上昇している本当の理由」\n"
                f"- 「〇〇が起きると、なぜ{stock_name}株が動くのか？」\n"
                f"- 「{stock_name}株に今すぐ注目すべき理由」"
            )
        elif price_direction == "big_down":
            price_context = (
                f"【⚠️ 値動き確認済み・必須】{stock_name}株は直近5日で{pct_str}の急落中（下落トレンド）。"
                f"タイトルには「急落」「下落」「売られている」などの下落表現を使うこと。"
                f"「急伸」「急騰」「上昇」「浮上」は絶対禁止。"
            )
            if stock_code.isdigit():  # 日本株のみ空売り表現可
                format_examples = (
                    f"- 「空売り注目：{stock_name}株の下落はまだ続くのか？」\n"
                    f"- 「なぜ{stock_name}株は急落しているのか？」\n"
                    f"- 「{stock_name}株が売られている本当の理由」"
                )
            else:  # 米国株は空売り表現禁止
                format_examples = (
                    f"- 「なぜ{stock_name}株は急落しているのか？」\n"
                    f"- 「{stock_name}株が売られている本当の理由」\n"
                    f"- 「{stock_name}株、下落はどこまで続くのか？」"
                )
        elif price_direction == "down":
            price_context = (
                f"【⚠️ 値動き確認済み・必須】{stock_name}株は直近5日で{pct_str}の下落中。"
                f"タイトルには「下落」「売り圧力」「反発なるか」などの表現を使うこと。「急伸」「急騰」は絶対禁止。"
            )
            if stock_code.isdigit():  # 日本株のみ空売り表現可
                format_examples = (
                    f"- 「{stock_name}株の下落トレンド、反発のきっかけはあるのか？」\n"
                    f"- 「なぜ{stock_name}株は売られているのか？」\n"
                    f"- 「空売りで狙える？{stock_name}株の今後を読む」"
                )
            else:  # 米国株は空売り表現禁止
                format_examples = (
                    f"- 「{stock_name}株の下落トレンド、反発のきっかけはあるのか？」\n"
                    f"- 「なぜ{stock_name}株は売られているのか？」\n"
                    f"- 「{stock_name}株、今が買い増しのチャンスか？」"
                )
        else:  # neutral
            price_context = (
                f"【⚠️ 値動き確認済み・必須】{stock_name}株は直近5日で{pct_str}とほぼ横ばい。"
                f"タイトルには「急伸するのか？」「どこへ向かうのか」「注目すべき理由」などの中立・問いかけ表現を使うこと。"
                f"「急伸済み」「急落済み」などの既成事実表現は禁止。"
            )
            format_examples = (
                f"- 「{stock_name}株は急伸するのか？今すぐ注目すべき理由」\n"
                f"- 「〇〇が起きると、なぜ{stock_name}株が動くのか？」\n"
                f"- 「{stock_name}株に今すぐ注目すべき理由」"
            )
    else:
        price_context = ""
        format_examples = (
            f"- 「なぜ{stock_name or '〇〇'}株は急伸したのか？」\n"
            f"- 「{stock_name or '〇〇'}株に今すぐ注目すべき理由」\n"
            f"- 「〇〇が起きると、なぜ{stock_name or '〇〇'}株が動くのか？」\n"
            f"- 「〇〇の裏で急浮上する{stock_name or '〇〇'}株」"
        )

    # 銘柄名を強制注入するブロック
    stock_constraint = f"""
【絶対条件・これを守らないタイトルは不合格】
タイトルの中に必ず「{stock_name}」という文字列を入れること。
「{stock_name}株」「{stock_name}が」「{stock_name}の」などの形で自然に組み込む。
この条件を満たさないタイトルは採用しない。
""" if stock_name else ""

    prompt = f"""以下の投資記事のタイトルを1つ生成してください。
{stock_constraint}
【元のニュース】
{news_title}

【記事本文（冒頭）】
{article_text[:500]}

【銘柄セクション】
{stock_section if stock_section else "（銘柄セクションなし）"}

【タイトル生成ルール】

**① 銘柄の実際の値動きをタイトルに正確に反映させる（最重要）**
{price_context if price_context else "値動きデータが取得できなかった場合は記事の文脈から判断すること。"}
推奨フォーマット：
{format_examples}

✅ 良い例（上昇）：「なぜアクセンチュアのAI全社導入で、マイクロソフト株が急伸するのか？」
✅ 良い例（下落）：「下落トレンドが続く任天堂株、Switch 2好調でも空売りが正解な理由」
✅ 良い例（横ばい）：「TSMCがArm株を売った裏で、東京エレクトロン株は急騰するのか？」
❌ NG：「TSMCはArm株を売却？巨額投資とAIバブルが導く資金戦略」（銘柄名が埋もれている）
❌ NG：急落中の銘柄に「なぜ急伸したのか？」→ 事実と乖離したタイトルは絶対禁止

**② SEOキーワードを組み込む**
「{stock_name or "銘柄名"} 株」「{stock_name or "銘柄名"} 急騰」「{stock_name or "銘柄名"} 注目」など
読者が実際に検索するキーワードをタイトルに自然に含める。

**③ 意外な因果構造で読者を引き付ける**
「え、なぜそれが関係あるの？」と思わせる一見つながらない連鎖を選ぶ。
常識・当たり前の因果（円安→輸出株上昇など）はNG。

**禁止事項**
- 専門用語（TOB・YCC・フォワードPER・テーパリング等）禁止
- 「〜かも」「〜の可能性」など曖昧表現禁止
- 「日経平均が〜」「相場解説」など抽象的なものは禁止
- 実際に記事に登場しない銘柄名を使うことは禁止

**文字数：25〜45字。タイトルのみ出力（説明・前置き不要）**"""

    result = run_gemini(prompt)
    if result:
        title = result.strip().strip('「」').strip('*').strip()
        title = _re.sub(r'^\*+|\*+$', '', title).strip()
        # 銘柄名が含まれていない場合、先頭に補完
        if stock_name and stock_name not in title and 10 <= len(title) <= 60:
            title = f"{stock_name}株──{title}"
        if 10 <= len(title) <= 70:
            return title

    # フォールバック（値動き方向を反映）
    today = datetime.datetime.now(JST)
    if stock_name:
        is_jp = stock_code.isdigit() if stock_code else False
        if price_direction in ("big_down", "down"):
            if is_jp:
                return f"空売り注目：{stock_name}株の下落はまだ続くのか？"
            else:
                return f"なぜ{stock_name}株は急落しているのか？"
        elif price_direction in ("big_up", "up"):
            return f"なぜ今{stock_name}株が急伸しているのか？"
        else:
            return f"{stock_name}株は急伸するのか？今すぐ注目すべき理由"
    return f"今日の注目ニュース深掘り｜{today.month}/{today.day}"


def generate_x_post(title: str, article_text: str) -> str:
    """noteへ誘導するX（旧Twitter）告知ポストを生成する"""
    # 銘柄名を抽出
    import re as _re
    stock_name = ""
    m_sec = _re.search(r'## このニュースで注目すべき銘柄(.+?)(?=^## |\Z)', article_text, _re.DOTALL | _re.MULTILINE)
    if m_sec:
        m_h3 = _re.search(r'^### (.+?)$', m_sec.group(1), _re.MULTILINE)
        if m_h3:
            stock_name = _re.sub(r'（[^）]+）', '', m_h3.group(1)).strip()

    stock_hint = f"（注目銘柄: {stock_name}）" if stock_name else ""

    prompt = (
        "X（旧Twitter）でnote記事へ誘導するための告知ポストを1つ作成してください。\n\n"
        f"記事タイトル: {title}\n"
        f"{stock_hint}\n"
        f"記事冒頭: {article_text[:300]}\n\n"
        "【Xポストのルール】\n"
        "① 1行目（フック）: 読者が「自分のことだ」「気になる」と思う一言。疑問形か断言で始める。絵文字1〜2個OK\n"
        "② 2〜4行目（ベネフィット）: この記事を読むと何がわかるか・何が得られるかを箇条書き（・で列挙）\n"
        "③ 最終行（CTA）: 「全文はこちら→ [note_url]」で締める\n\n"
        "【トーン】プロフェッショナルかつ親しみやすい。投資家目線。煽りすぎない。\n"
        "【禁止】「爆益」「必ず儲かる」などの誇大表現。投資助言的な断言。\n"
        "【文字数】全体で140字以内（Xの1ポスト上限）\n"
        "【出力】ポスト本文のみ。前置き・説明不要。[note_url] はそのままプレースホルダーとして残す。"
    )

    result = run_gemini(prompt)
    if result and len(result.strip()) > 20:
        post = result.strip()
        # [note_url] が含まれていない場合は末尾に追加
        if "[note_url]" not in post:
            post = post.rstrip() + "\n全文はこちら→ [note_url]"
        return post

    # フォールバック
    return (
        f"📊 {title}\n\n"
        "・なぜこの銘柄が今注目されているのか\n"
        "・中長期でどう動けばいいか\n"
        "・投資家が見落としているポイント\n\n"
        "全文はこちら→ [note_url]"
    )


def get_random_cover_image() -> str | None:
    """~/Desktop/投資画像/ からランダムに画像を返す（フォールバック用）"""
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


def _extract_stock_from_article(article_text: str) -> str:
    """「## このニュースで注目すべき銘柄」セクション内の H3（銘柄名）を抽出する。なければ空文字を返す"""
    # H2（## ）のみで区切る（H3 ### はセクション内なので区切りにしない）
    m_sec = re.search(r'## このニュースで注目すべき銘柄(.+?)(?=^## [^#]|\Z)', article_text, re.DOTALL | re.MULTILINE)
    if m_sec:
        m_h3 = re.search(r'^### (.+?)$', m_sec.group(1), re.MULTILINE)
        if m_h3:
            return m_h3.group(1).strip()
    return ""


def generate_thumbnail(title: str, article_text: str, suffix: str = "") -> str | None:
    """記事タイトルと本文から1920×1006pxのバズるサムネイルを生成する"""
    # 記事の核心キーワード・数値を抽出（プロンプト用）
    keywords = re.findall(r'\*\*([^*]{2,20})\*\*', article_text[:1000])
    keyword_block = "・".join(keywords[:4]) if keywords else ""

    # 注目銘柄を抽出してサムネイルに絡める
    stock_name = _extract_stock_from_article(article_text)
    stock_block = f"""
【注目銘柄バッジ（必須）】
画像の右上または左上の隅に、小さな半透明バッジ（角丸の黒背景）を配置し、
以下の銘柄名を白いフォントで表示すること：
  「注目 {stock_name}」
バッジは控えめに・主役はあくまでタイトルテキストとビジュアル。
バッジ内のテキストは日本語のみ（英語・記号は最小限）。
""" if stock_name else ""

    prompt = f"""投資ブログのカバー画像（アイキャッチ）を作成してください。

【記事タイトル】
{title}

【記事の核心キーワード】
{keyword_block}
{stock_block}
【デザインコンセプト（最重要）】
「クールで重厚感のある」プロフェッショナル投資メディアのサムネイル。
テンプレートの使い回しは禁止。記事タイトルのテーマ・業界・キーワードに完全に沿った、
そのタイトルにしか使えない一点もののビジュアルを作ること。

【ビジュアルの方向性】
- タイトルのテーマを読み取り、そのテーマを象徴するビジュアルを選ぶ
  例：造船・ロボット → 工場内の溶接ロボットアーム・鉄鋼の火花・巨大船体
  例：半導体・AI → マイクロチップの電子回路・データセンターのサーバー列・光ファイバー
  例：金融政策・金利 → FRB建物・ドル紙幣のクローズアップ・株価ボードの数字
  例：エネルギー・資源 → 油田・LNGタンカー・パイプライン・地政学的な地図
  例：人手不足・労働 → 製造ラインの映像・高齢化した職人の手元・工場の夜景
- 写実的・映画的なクオリティ。アニメ・イラスト・ポップなデザインは禁止
- 重厚感・緊張感・知性を感じさせる色調とライティング

【レイアウト】
1. **背景ビジュアル**：テーマに沿った実写風の映像美。暗く重厚なトーンで全面に配置
2. **グラデーションオーバーレイ**：下部〜中央にかけて深い黒または濃紺のグラデーションをかけ、テキストを際立たせる
3. **タイトルテキスト**：画像の中央〜下部に白の極太フォントで配置。テキストに薄いドロップシャドウまたは輪郭線を入れて可読性を確保。長い場合は自然な位置で2行に折り返す（文字が端で途切れないこと）。**タイトルテキストは画像内に必ず1箇所のみ配置すること。同じテキストを複数箇所に重複配置することは絶対禁止。**
4. **アクセント**：細いゴールドまたはシアンのラインを1〜2本入れてモダンな質感を加えてもよい

【テキスト要件】
- 白または明るいゴールドの極太フォント
- フォントサイズは画像高さの10〜14%（十分に大きく・読みやすく）
- テキストはすべて日本語（中国語・韓国語・英語は使わない）
- タイトルテキストは画像内に1回のみ。同じテキストの二重配置・重複は絶対禁止

【禁止事項】
- 発光する「？」マークのみを中央に置くデザイン（旧テンプレート）は禁止
- 抽象的な光の粒子・ホログラム風の汎用背景は禁止
- 毎回同じような構図の使い回しは禁止

【仕様】
- 16:9横長、高解像度
"""

    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from generate_images import generate_image
        from PIL import Image as _Image

        today = datetime.datetime.now(JST).strftime("%Y%m%d")
        os.makedirs("output/images", exist_ok=True)
        path = f"output/images/thumbnail_{today}{suffix}.png"
        result = generate_image(prompt, path)
        if result:
            # 1920×1006px にリサイズ（auto-1方式）
            try:
                img = _Image.open(result)
                img = img.resize((1920, 1006), _Image.LANCZOS)
                img.save(result)
                print(f"  サムネイル 1920×1006px リサイズ完了: {path}")
            except Exception as _e:
                print(f"  [WARN] リサイズ失敗: {_e}")
            return result
        else:
            print("  [WARN] サムネイル生成失敗、フォールバック使用")
            return get_random_cover_image()
    except Exception as e:
        print(f"  [WARN] サムネイル生成エラー: {e}")
        return get_random_cover_image()


def _write_article(news: dict, article_num: int) -> dict:
    """1トピックから記事を執筆してJSONを保存し、記事dictを返す"""
    today_str = datetime.datetime.now(JST).strftime("%Y%m%d")
    print(f"\n  --- 記事{article_num}執筆: {news['title'][:60]} ---")

    sec = write_news_section(news, article_num)

    print(f"  タイトル生成中...")
    title = generate_title(sec["text"], news['title'])

    # タイトルと銘柄セクションの買い/売り方向が矛盾していれば修正
    body_aligned = _align_stock_direction_with_title(sec["text"], title)
    if body_aligned is not sec["text"]:
        sec = dict(sec)
        sec["text"] = body_aligned

    print(f"  サムネイル生成中...")
    # 記事番号付きサムネイル名（article_1はそのまま、2以降は_2, _3と付ける）
    thumb_suffix = "" if article_num == 1 else f"_{article_num}"
    cover_path = generate_thumbnail(title, sec["text"], suffix=thumb_suffix)

    body = sec['text']

    # X告知ポスト生成
    print(f"  X告知ポスト生成中...")
    x_post = generate_x_post(title, body)
    # 記事末尾にX告知ポストセクションを追加（[note_url]は投稿後に置換）
    x_section = (
        "\n\n"
        "## 📢 この記事をXでシェアする場合のテンプレ\n\n"
        "> " + x_post.replace("\n", "\n> ") + "\n\n"
        "*↑ [note_url] 部分を投稿後のURLに差し替えてください*"
    )
    # ── メンバーシップCTA（X告知の直前に挿入） ──
    MEMBERSHIP_URL = "https://note.com/kawasewatson0106/membership"
    membership_cta = (
        "\n\n"
        "## 毎週月曜更新：私の実際の売買判断を公開中\n\n"
        "このnoteでは「仕組みの解説」を届けていますが、"
        "**私が実際にどの銘柄をいつ買ったか・なぜ見送ったか・どこで売ったか**は"
        "有料メンバーシップで毎週月曜に更新しています。\n\n"
        "メンバー限定コンテンツ（毎週月曜更新）：\n"
        "- 今週私がエントリーした銘柄と、その根拠\n"
        "- 「これは見送り」と判断した銘柄の理由（買わない理由を知ることが一番重要です）\n"
        "- 損切りした場合はその理由も正直に公開\n\n"
        "**月980円、最初の1ヶ月は無料。**合わなければすぐ退会できます。\n\n"
        f"{MEMBERSHIP_URL}\n"
    )
    # ── 中盤CTA（2番目のH2見出し手前に挿入） ──
    MEMBERSHIP_URL_MID = "https://note.com/kawasewatson0106/membership"
    mid_cta = (
        "\n\n"
        f"> **毎週の売買判断（買った銘柄・見送った銘柄・売った銘柄）は[メンバーシップ]({MEMBERSHIP_URL_MID})で公開中。最初の1ヶ月は無料。**\n\n"
    )
    h2_positions = [m.start() for m in __import__("re").finditer(r'\n## ', body)]
    if len(h2_positions) >= 2:
        insert_pos = h2_positions[1]
        body = body[:insert_pos] + mid_cta + body[insert_pos:]

    # X告知テンプレートは記事本文には含めない（ターミナル出力のみ）
    article_body = body + membership_cta

    all_topic_tags = sec["topic_tags"][:2]
    all_tags = FIXED_TAGS + [t for t in all_topic_tags if t not in FIXED_TAGS]

    article = {
        "title": title,
        "article": article_body,
        "tags": all_tags,
        "topic_tags": all_topic_tags,
        "source_news": {"news1": news},
        "image_paths": sec["image_paths"],
        "cover_path": cover_path,
        "skip_stock": sec.get("skip_stock", False),
        "x_post": x_post,
    }

    out_path = f"output/article_{article_num}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(article, f, ensure_ascii=False, indent=2)
    print(f"  保存: {out_path}  タイトル: {title}")

    if article_num == 1:
        with open("output/final.json", "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)

    return article


def main(force_topic_keyword: str = None):
    print("=== ② 記事執筆（複数ニュース・複数記事） ===")

    with open("output/collected_news.json", encoding="utf-8") as f:
        articles = json.load(f)

    # force_topic_keyword が指定された場合はキーワードで強制選定
    if force_topic_keyword:
        matched = [a for a in articles if force_topic_keyword in a.get("title", "")]
        if matched:
            selected = [matched[0]]
            print(f"  強制選定: {matched[0]['title']}")
        else:
            print(f"  [WARN] キーワード '{force_topic_keyword}' に一致するニュースが見つからず通常選定へ")
            selected = select_multiple_topics(articles, max_topics=1)
    else:
        # 複数トピック選定（必要本数をClaudeが判断・上限5件・AI/Trump優先）
        print("  トピック選定中...")
        selected = select_multiple_topics(articles, max_topics=1)

    os.makedirs("output", exist_ok=True)

    result = {}
    for i, news in enumerate(selected, start=1):
        try:
            article = _write_article(news, i)
            result[f"article_{i}"] = article
        except Exception as e:
            print(f"  [WARN] 記事{i}執筆失敗: {e}")
            import traceback as _tb
            _tb.print_exc()

    if not result:
        raise RuntimeError("全記事の執筆に失敗しました")

    # 後方互換：article_1がなければ最初の記事をarticle_1として保存
    if "article_1" not in result:
        first = list(result.values())[0]
        result["article_1"] = first
        with open("output/article_1.json", "w", encoding="utf-8") as f:
            json.dump(first, f, ensure_ascii=False, indent=2)

    return result


if __name__ == "__main__":
    main()
