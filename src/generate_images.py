"""
④ 画像生成
- カバー画像：Geminiで生成（GEMINI_API_KEY が使えない場合はスキップ）
- 銘柄チャート：yfinance + matplotlib で1時間足チャートを生成（__CHART_0__, __CHART_1__ を置換）
"""

from __future__ import annotations

import json
import os
import re
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# Gemini はオプション（APIキーがなければスキップ）
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ─── チャートカラー ────────────────────────────────────────────────
BG_COLOR   = "#1a1a2e"
TEXT_COLOR = "#cccccc"
GRID_COLOR = "#2d2d4e"
UP_COLOR   = "#26a69a"
DOWN_COLOR = "#ef5350"
MA5_COLOR  = "#ffeb3b"
MA20_COLOR = "#ff9800"
RSI_COLOR  = "#ce93d8"


# ─── yfinance 1時間足チャート ──────────────────────────────────────

def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.where(delta > 0, 0.0)
    loss  = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("inf"))
    return 100 - (100 / (1 + rs))


def _fetch_1h_data(symbol: str) -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    for period in ("5d", "10d", "60d"):
        try:
            df = ticker.history(period=period, interval="1h")
            if not df.empty and len(df) >= 10:
                return df
        except Exception:
            continue
    return pd.DataFrame()


def generate_stock_chart(symbol: str, output_path: str) -> str | None:
    """1時間足チャート（MA5/MA20/RSI/出来高）を生成して保存"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    df = _fetch_1h_data(symbol)
    if df.empty:
        print(f"  [WARN] {symbol} の価格データ取得失敗（チャートなし）")
        return None

    df = df.copy()
    df["MA5"]  = df["Close"].rolling(5).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["RSI"]  = calc_rsi(df["Close"], 14)

    n = len(df)
    x = list(range(n))

    fig = plt.figure(figsize=(12, 8), facecolor=BG_COLOR)
    gs  = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.08)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    for ax in (ax1, ax2, ax3):
        ax.set_facecolor(BG_COLOR)
        ax.tick_params(colors=TEXT_COLOR, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(GRID_COLOR)
        ax.yaxis.label.set_color(TEXT_COLOR)
        ax.grid(color=GRID_COLOR, linewidth=0.5, alpha=0.5)

    # ローソク足
    for i, (_, row) in enumerate(df.iterrows()):
        c = UP_COLOR if row["Close"] >= row["Open"] else DOWN_COLOR
        ax1.plot([i, i], [row["Low"], row["High"]], color=c, linewidth=0.8, zorder=2)
        bottom = min(row["Open"], row["Close"])
        height = abs(row["Close"] - row["Open"]) or (row["High"] - row["Low"]) * 0.01
        ax1.add_patch(mpatches.Rectangle(
            (i - 0.35, bottom), 0.7, height, facecolor=c, edgecolor=c, zorder=3
        ))

    # 移動平均線
    valid_ma5  = df["MA5"].dropna()
    valid_ma20 = df["MA20"].dropna()
    if not valid_ma5.empty:
        ax1.plot(range(n - len(valid_ma5), n), valid_ma5.values,
                 color=MA5_COLOR, linewidth=1.0, label="MA5", zorder=4)
    if not valid_ma20.empty:
        ax1.plot(range(n - len(valid_ma20), n), valid_ma20.values,
                 color=MA20_COLOR, linewidth=1.0, label="MA20", zorder=4)

    ax1.legend(loc="upper left", fontsize=8,
               facecolor=BG_COLOR, labelcolor=TEXT_COLOR,
               framealpha=0.7, edgecolor=GRID_COLOR)
    ax1.set_ylabel("Price", color=TEXT_COLOR, fontsize=9)
    ax1.set_title(f"{symbol}  1時間足チャート", color="#ffffff", fontsize=11, pad=8)

    # 出来高
    for i, (_, row) in enumerate(df.iterrows()):
        c = UP_COLOR if row["Close"] >= row["Open"] else DOWN_COLOR
        ax2.bar(i, row["Volume"], color=c, alpha=0.7, width=0.8)
    ax2.set_ylabel("Vol", color=TEXT_COLOR, fontsize=8)

    # RSI
    rsi_vals = df["RSI"].ffill().values
    ax3.plot(x, rsi_vals, color=RSI_COLOR, linewidth=1.2)
    ax3.axhline(70, color=DOWN_COLOR, linewidth=0.8, linestyle="--", alpha=0.7)
    ax3.axhline(30, color=UP_COLOR,   linewidth=0.8, linestyle="--", alpha=0.7)
    ax3.set_ylim(0, 100)
    ax3.set_ylabel("RSI", color=TEXT_COLOR, fontsize=8)
    ax3.text(2, 72, "70", color=DOWN_COLOR, fontsize=7, alpha=0.8)
    ax3.text(2, 22, "30", color=UP_COLOR,   fontsize=7, alpha=0.8)

    # X軸ラベル
    step = max(1, n // 8)
    xticks = list(range(0, n, step))
    xlabels = [df.index[i].strftime("%m/%d %H:%M") for i in xticks]
    ax3.set_xticks(xticks)
    ax3.set_xticklabels(xlabels, rotation=30, ha="right", fontsize=7, color=TEXT_COLOR)
    plt.setp(ax1.get_xticklabels(), visible=False)
    plt.setp(ax2.get_xticklabels(), visible=False)

    plt.savefig(output_path, dpi=120, bbox_inches="tight",
                facecolor=BG_COLOR, edgecolor="none")
    plt.close(fig)
    print(f"  株価チャート生成: {os.path.basename(output_path)}")
    return os.path.abspath(output_path)


def extract_stock_tickers(article_text: str) -> list[str]:
    """
    記事から銘柄のティッカーを抽出する。
    「# このニュースで注目すべき銘柄」セクション直後の行から抽出。
    例: 「トヨタ自動車（7203）」→ "7203.T"
         「NVIDIA（NVDA）」→ "NVDA"
    後方互換: 「銘柄名：トヨタ自動車（7203）」形式も対応
    """
    tickers = []
    # 「# このニュースで注目すべき銘柄」直後の行から抽出
    for section_match in re.finditer(r'# このニュースで注目すべき銘柄\s*\n([^\n]+)', article_text):
        line = section_match.group(1).strip()
        # 「銘柄名：」プレフィックスがあれば除去
        line = re.sub(r'^銘柄名[：:]\s*', '', line)
        # （コード）または（TICKER）を抽出
        m = re.search(r'[（(]([^）)]+)[）)]', line)
        if m:
            raw = m.group(1).strip()
            if re.match(r'^\d{4}$', raw):
                tickers.append(raw + ".T")
            else:
                tickers.append(raw)
    return tickers


def generate_stock_charts(article_text: str) -> tuple[str, list[str]]:
    """
    __CHART_0__, __CHART_1__ を実際のチャート画像で解決する。
    - 記事からティッカーを抽出して1時間足チャートを生成
    - __CHART_N__ を __IMAGE_N__ に置換（image_paths の先頭に追加）
    - 生成したチャートのパスリストと更新済み記事テキストを返す
    """
    os.makedirs("output/images", exist_ok=True)
    tickers = extract_stock_tickers(article_text)
    chart_paths = []

    for i, ticker in enumerate(tickers[:2]):  # 最大2銘柄
        out_path = f"output/images/stock_chart_{i}.png"
        path = generate_stock_chart(ticker, out_path)
        chart_paths.append(path)
        placeholder = f"__CHART_{i}__"
        image_placeholder = f"__IMAGE_{i}__"
        article_text = article_text.replace(placeholder, image_placeholder)

    # ティッカーが見つからなかった分は除去
    for i in range(len(tickers), 2):
        article_text = article_text.replace(f"__CHART_{i}__", "")

    print(f"  株価チャート: {len([p for p in chart_paths if p])} 枚生成")
    return article_text, chart_paths


# ─── カバー画像（デスクトップ優先 → Gemini API フォールバック） ──────

def find_desktop_cover_image() -> str | None:
    """
    ~/Desktop/投資画像/ 内の最新ファイルを返す。
    ファイル名が Gemini_Gener... で始まるものを優先し、なければ最新ファイルを使う。
    """
    desktop_dir = os.path.expanduser("~/Desktop/投資画像")
    if not os.path.isdir(desktop_dir):
        return None
    files = [f for f in os.listdir(desktop_dir)
             if os.path.isfile(os.path.join(desktop_dir, f))
             and f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    if not files:
        return None
    # Gemini_Gener... で始まるファイルを優先
    gemini_files = [f for f in files if f.startswith('Gemini_Gener')]
    candidates = gemini_files if gemini_files else files
    # 最終更新日時が新しいものを選ぶ
    candidates.sort(key=lambda f: os.path.getmtime(os.path.join(desktop_dir, f)), reverse=True)
    chosen = os.path.join(desktop_dir, candidates[0])
    print(f"  カバー画像: デスクトップから使用 → {candidates[0]}")
    return chosen


def generate_cover_image(article_text: str) -> str | None:
    """カバー画像を取得（デスクトップ優先 → assets/cover_image.png）"""
    # ① デスクトップの投資画像フォルダを確認
    desktop_path = find_desktop_cover_image()
    if desktop_path:
        return desktop_path

    # ② Geminiは使用しない
    print("  カバー画像: デスクトップ画像なし（assets/cover_image.pngをフォールバックとして使用）")
    return None


# ─── メイン ───────────────────────────────────────────────────────

def main():
    print("=== ④ 画像生成（株価チャート＋カバー画像） ===")

    with open("output/polished.json", encoding="utf-8") as f:
        data = json.load(f)

    article_text = data["polished"]
    os.makedirs("output/images", exist_ok=True)

    # 株価チャート生成（__CHART_N__ → __IMAGE_N__）
    print("  株価チャートを生成中...")
    article_text, stock_chart_paths = generate_stock_charts(article_text)

    # カバー画像生成
    print("  カバー画像生成中...")
    cover_path = generate_cover_image(article_text)
    if not cover_path:
        fixed = os.path.join(os.path.dirname(__file__), "..", "assets", "cover_image.png")
        cover_path = fixed if os.path.exists(fixed) else None
        if cover_path:
            print(f"  カバー画像: フォールバック使用")

    # image_paths = [stock_chart_0, stock_chart_1, ...]（後続処理で __IMAGE_N__ に対応）
    valid_stock_paths = [p for p in stock_chart_paths if p]

    result = {
        "article":     article_text,
        "image_paths": valid_stock_paths,
        "cover_path":  cover_path,
        "articles":    data["articles"],
    }

    out_path = "output/article_with_images.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"保存: {out_path}")
    return result


if __name__ == "__main__":
    main()
