"""
銘柄チャート生成（日足・1時間足、MACD・サポレジ・MA付き）

watson0106/stock-analysis-auto からの移植版。
Windows環境で動作するよう、日本語フォントを Yu Gothic に差し替え。
"""
from __future__ import annotations

import os
import platform
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib import font_manager
import pandas as pd
import yfinance as yf
from PIL import Image

warnings.filterwarnings("ignore")

# ── 日本語フォント設定（OS別） ──
def _setup_jp_font():
    system = platform.system()
    candidates = []
    if system == "Windows":
        candidates = [
            r"C:\Windows\Fonts\YuGothB.ttc",
            r"C:\Windows\Fonts\YuGothM.ttc",
            r"C:\Windows\Fonts\meiryo.ttc",
            r"C:\Windows\Fonts\msgothic.ttc",
        ]
    elif system == "Darwin":
        candidates = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
        ]
    else:
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        ]
    for p in candidates:
        if os.path.exists(p):
            try:
                font_manager.fontManager.addfont(p)
                prop = font_manager.FontProperties(fname=p)
                plt.rcParams["font.family"] = prop.get_name()
                plt.rcParams["axes.unicode_minus"] = False
                return prop.get_name()
            except Exception:
                continue
    return None

_setup_jp_font()

BG_COLOR     = "#1a1a2e"
TEXT_COLOR   = "#cccccc"
GRID_COLOR   = "#2d2d4e"
UP_COLOR     = "#26a69a"
DOWN_COLOR   = "#ef5350"
MA5_COLOR    = "#ffeb3b"
MA20_COLOR   = "#ff9800"
MA50_COLOR   = "#ab47bc"
MACD_COLOR   = "#42a5f5"
SIGNAL_COLOR = "#ff7043"

NOTE_WIDTH  = 1920
NOTE_HEIGHT = 1006


def calc_macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram


def find_sr_levels(df: pd.DataFrame, window: int = 5, n_levels: int = 3) -> tuple[list, list]:
    """スイングハイ・スイングローからサポート/レジスタンスを検出"""
    highs = df["High"].values
    lows  = df["Low"].values
    n = len(df)

    resistance, support = [], []
    for i in range(window, n - window):
        if highs[i] == max(highs[i - window: i + window + 1]):
            resistance.append(float(highs[i]))
        if lows[i] == min(lows[i - window: i + window + 1]):
            support.append(float(lows[i]))

    def cluster(levels, tol=0.01):
        if not levels:
            return []
        levels = sorted(set(levels), reverse=True)
        result, group = [], [levels[0]]
        for v in levels[1:]:
            if abs(v - group[0]) / group[0] < tol:
                group.append(v)
            else:
                result.append(sum(group) / len(group))
                group = [v]
        result.append(sum(group) / len(group))
        return result[:n_levels]

    return cluster(resistance), cluster(support)


def _draw_chart(df: pd.DataFrame, title: str, ma_periods: list,
                output_path: str, date_fmt: str = "%m/%d") -> dict:
    """ローソク足 + MA + SR + 出来高 + MACD の3パネルチャートを描画"""
    df = df.copy()
    for p in ma_periods:
        df[f"MA{p}"] = df["Close"].rolling(p).mean()
    macd_vals, signal_vals, hist_vals = calc_macd(df["Close"])
    df["MACD"]   = macd_vals
    df["Signal"] = signal_vals
    df["Hist"]   = hist_vals

    n = len(df)
    ma_colors = [MA5_COLOR, MA20_COLOR, MA50_COLOR]
    resistance, support = find_sr_levels(df)

    fig = plt.figure(figsize=(19.2, 10.06), facecolor=BG_COLOR)
    gs  = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 1.2], hspace=0.08)
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

    for i, (_, row) in enumerate(df.iterrows()):
        c = UP_COLOR if row["Close"] >= row["Open"] else DOWN_COLOR
        ax1.plot([i, i], [row["Low"], row["High"]], color=c, linewidth=0.8, zorder=2)
        body_bottom = min(row["Open"], row["Close"])
        body_height = abs(row["Close"] - row["Open"]) or (row["High"] - row["Low"]) * 0.01
        ax1.add_patch(mpatches.Rectangle(
            (i - 0.35, body_bottom), 0.7, body_height,
            facecolor=c, edgecolor=c, zorder=3
        ))

    legend_handles = []
    for p, color in zip(ma_periods, ma_colors):
        col = f"MA{p}"
        valid = df[col].dropna()
        if not valid.empty:
            line, = ax1.plot(range(n - len(valid), n), valid.values,
                             color=color, linewidth=1.0, label=f"MA{p}", zorder=4)
            legend_handles.append(line)

    for r in resistance:
        ax1.axhline(r, color=DOWN_COLOR, linewidth=0.8, linestyle="--", alpha=0.6)
        ax1.text(n - 1, r, f" R:{r:,.0f}", color=DOWN_COLOR, fontsize=7, va="bottom", ha="right")
    for s in support:
        ax1.axhline(s, color=UP_COLOR, linewidth=0.8, linestyle="--", alpha=0.6)
        ax1.text(n - 1, s, f" S:{s:,.0f}", color=UP_COLOR, fontsize=7, va="top", ha="right")

    ax1.legend(handles=legend_handles, loc="upper left", fontsize=8,
               facecolor=BG_COLOR, labelcolor=TEXT_COLOR, framealpha=0.7, edgecolor=GRID_COLOR)
    ax1.set_ylabel("Price", color=TEXT_COLOR, fontsize=9)
    ax1.set_title(title, color="#ffffff", fontsize=11, pad=8)

    for i, (_, row) in enumerate(df.iterrows()):
        c = UP_COLOR if row["Close"] >= row["Open"] else DOWN_COLOR
        ax2.bar(i, row["Volume"], color=c, alpha=0.7, width=0.8)
    ax2.set_ylabel("Vol", color=TEXT_COLOR, fontsize=8)

    valid_macd   = df["MACD"].dropna()
    valid_signal = df["Signal"].dropna()
    valid_hist   = df["Hist"].dropna()
    offset = n - len(valid_macd)

    for i, val in enumerate(valid_hist.values):
        c = UP_COLOR if val >= 0 else DOWN_COLOR
        ax3.bar(offset + i, val, color=c, alpha=0.7, width=0.8)
    if not valid_macd.empty:
        ax3.plot(range(offset, n), valid_macd.values, color=MACD_COLOR, linewidth=1.0, label="MACD")
    if not valid_signal.empty:
        ax3.plot(range(n - len(valid_signal), n), valid_signal.values,
                 color=SIGNAL_COLOR, linewidth=1.0, label="Signal")
    ax3.axhline(0, color=GRID_COLOR, linewidth=0.5)
    ax3.set_ylabel("MACD", color=TEXT_COLOR, fontsize=8)
    ax3.legend(loc="upper left", fontsize=7, facecolor=BG_COLOR,
               labelcolor=TEXT_COLOR, framealpha=0.7, edgecolor=GRID_COLOR)

    step = max(1, n // 8)
    xticks = list(range(0, n, step))
    xlabels = [df.index[i].strftime(date_fmt) for i in xticks]
    ax3.set_xticks(xticks)
    ax3.set_xticklabels(xlabels, rotation=30, ha="right", fontsize=7, color=TEXT_COLOR)
    plt.setp(ax1.get_xticklabels(), visible=False)
    plt.setp(ax2.get_xticklabels(), visible=False)

    plt.savefig(output_path, dpi=100, bbox_inches="tight",
                facecolor=BG_COLOR, edgecolor="none")
    plt.close(fig)

    img = Image.open(output_path)
    img = img.resize((NOTE_WIDTH, NOTE_HEIGHT), Image.LANCZOS)
    img.save(output_path)

    last_macd   = float(valid_macd.iloc[-1])   if not valid_macd.empty   else None
    last_signal = float(valid_signal.iloc[-1]) if not valid_signal.empty else None
    last_hist   = float(valid_hist.iloc[-1])   if not valid_hist.empty   else None

    return {
        "macd":         last_macd,
        "signal":       last_signal,
        "histogram":    last_hist,
        "bullish_cross": (last_macd is not None and last_signal is not None
                          and last_macd > last_signal),
        "resistance":   resistance,
        "support":      support,
    }


def generate_daily_chart(symbol: str, code: str, output_dir: str) -> tuple[str | None, dict]:
    """日足チャート（3ヶ月〜1年）を生成してパスとテクニカルデータを返す"""
    os.makedirs(output_dir, exist_ok=True)
    ticker = yf.Ticker(symbol)
    df = pd.DataFrame()
    for period in ("3mo", "6mo", "1y"):
        try:
            df = ticker.history(period=period, interval="1d")
            if not df.empty and len(df) >= 30:
                break
        except Exception:
            continue

    if df.empty:
        print(f"  [WARN] {symbol} の日足データ取得失敗")
        return None, {}

    output_path = os.path.join(output_dir, f"{code}_daily_chart.png")
    data = _draw_chart(df, f"{code}  日足チャート", ma_periods=[25, 75],
                       output_path=output_path, date_fmt="%m/%d")
    print(f"  日足チャート生成: {output_path}")
    return os.path.abspath(output_path), data


def generate_1h_chart(symbol: str, code: str, output_dir: str = None) -> tuple[str | None, dict]:
    """1時間足チャートを生成してパスとテクニカルデータを返す"""
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "..", "output", "charts")
    os.makedirs(output_dir, exist_ok=True)

    ticker = yf.Ticker(symbol)
    df = pd.DataFrame()
    for period in ("5d", "10d", "60d"):
        try:
            df = ticker.history(period=period, interval="1h")
            if not df.empty and len(df) >= 10:
                break
        except Exception:
            continue

    if df.empty:
        print(f"  [WARN] {symbol} の1時間足データ取得失敗")
        return None, {}

    output_path = os.path.join(output_dir, f"{code}_1h_chart.png")
    data = _draw_chart(df, f"{code}  1時間足チャート", ma_periods=[5, 20],
                       output_path=output_path, date_fmt="%m/%d %H:%M")
    print(f"  1時間足チャート生成: {output_path}")
    return os.path.abspath(output_path), data


if __name__ == "__main__":
    import sys
    out_dir = os.path.join(os.path.dirname(__file__), "..", "output", "charts")
    code = sys.argv[1] if len(sys.argv) > 1 else "7203"
    print(f"テスト: {code}")
    generate_daily_chart(f"{code}.T", code, out_dir)
    generate_1h_chart(f"{code}.T", code, out_dir)
