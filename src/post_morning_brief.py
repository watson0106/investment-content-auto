"""
post_morning_brief.py
毎朝9:00に「今日の市場ひとこと」を投稿する。
- yfinanceで昨日の市場データを取得
- 200〜400文字の短いブリーフを生成
- メンバーシップCTAを添える
- note下書き保存（後で手動公開、または auto_publish=True で自動公開）

毎朝の短い投稿がフォロワーとの接触頻度を維持し、
メンバーへの興味を高める。

cron: 0 9 * * * cd ~/investment-content-auto && python3 src/post_morning_brief.py
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")
sys.path.insert(0, str(Path(__file__).parent))

JST = datetime.timezone(datetime.timedelta(hours=9))
MEMBERSHIP_URL = "https://note.com/kawasewatson0106/membership"
BRIEF_LOG = BASE_DIR / "data" / "morning_brief_log.json"


def get_market_data() -> dict:
    """主要指数・為替のデータを取得する"""
    try:
        import yfinance as yf
        tickers = {
            "日経平均": "^N225",
            "S&P500": "^GSPC",
            "ドル円": "JPY=X",
            "米10年金利": "^TNX",
        }
        data = {}
        for name, ticker in tickers.items():
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="2d")
                if len(hist) >= 1:
                    last = hist.iloc[-1]
                    prev = hist.iloc[-2] if len(hist) >= 2 else hist.iloc[-1]
                    close = last["Close"]
                    change = (close - prev["Close"]) / prev["Close"] * 100
                    data[name] = {"price": close, "change": change}
            except Exception:
                pass
        return data
    except Exception:
        return {}


def generate_brief(market_data: dict, today: datetime.datetime) -> str:
    """今日の市場ひとことを生成する"""
    try:
        shutil = __import__("shutil")
        claude_path = shutil.which("claude")
    except Exception:
        claude_path = None

    weekday_map = ["月", "火", "水", "木", "金", "土", "日"]
    weekday = weekday_map[today.weekday()]
    date_str = today.strftime(f"%m月%d日（{weekday}）")

    # 市場データを文字列に変換
    market_summary = ""
    for name, d in market_data.items():
        sign = "+" if d["change"] >= 0 else ""
        market_summary += f"  {name}: {d['price']:,.1f} ({sign}{d['change']:.1f}%)\n"

    if not market_summary:
        market_summary = "  （市場データ取得中）"

    prompt = f"""今日{date_str}の投資家向け朝のひとことを書いてください。

【昨日の主要指数】
{market_summary}

【形式】
- 200〜350文字
- ブロガー口調（です・ます）
- 昨日の市場の動きを一言で表現する
- 今日注目すべき点を1つ挙げる
- 最後に「今日の私の判断は、メンバーシップで共有しています。（URL不要）」のような一文で締める
- AI感のある文章は禁止（「〜でしょう」「〜と言えます」「注目が集まっています」禁止）
- 絵文字使用禁止
- コメント・前置き不要。本文のみ出力

本文（コメント・前置き不要）:"""

    if claude_path:
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION")}
        try:
            result = subprocess.run(
                [claude_path, "-p", prompt, "--output-format", "text",
                 "--allowedTools", "none", "--dangerously-skip-permissions"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60, env=env,
            )
            if result.returncode == 0 and len(result.stdout.strip()) > 50:
                return result.stdout.strip()
        except Exception:
            pass

    # フォールバック: テンプレートベース
    lines = [f"{date_str}の市場チェックです。"]
    for name, d in list(market_data.items())[:2]:
        sign = "+" if d["change"] >= 0 else ""
        direction = "上昇" if d["change"] >= 0 else "下落"
        lines.append(f"{name}は昨日比{sign}{d['change']:.1f}%の{direction}でした。")
    lines.append("")
    lines.append("今日の市場で私が注目しているポイントは、メンバーシップで共有しています。")
    return "\n".join(lines)


def post_brief(brief_text: str, today: datetime.datetime) -> str | None:
    """ブリーフをnoteに投稿する"""
    import post_to_note

    weekday_map = ["月", "火", "水", "木", "金", "土", "日"]
    weekday = weekday_map[today.weekday()]
    date_str = today.strftime(f"%-m月%-d日")
    title = f"{date_str}（{weekday}）の市場ひとこと"

    # CTA付きの本文
    article = f"""{brief_text}

{MEMBERSHIP_URL}
"""
    tags = ["投資", "株式投資", "資産運用", "日本株", "米国株"]

    url = post_to_note.post_article(
        title=title,
        body=article,
        image_paths=[],
        tags=tags,
        price=0,
        auto_publish=True,  # 短いブリーフは自動公開
    )
    return url


def already_posted_today(today: datetime.datetime) -> bool:
    if not BRIEF_LOG.exists():
        return False
    with open(BRIEF_LOG, encoding="utf-8") as f:
        log = json.load(f)
    today_str = today.strftime("%Y-%m-%d")
    return any(e["date"] == today_str for e in log)


def save_log(entry: dict):
    BRIEF_LOG.parent.mkdir(parents=True, exist_ok=True)
    log = []
    if BRIEF_LOG.exists():
        with open(BRIEF_LOG, encoding="utf-8") as f:
            log = json.load(f)
    log.append(entry)
    with open(BRIEF_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def main():
    now = datetime.datetime.now(JST)
    print(f"=== 朝のひとこと投稿 {now.strftime('%Y-%m-%d %H:%M')} JST ===")

    # 平日のみ投稿（土日はスキップ）
    if now.weekday() >= 5:  # 土日
        print("  土日のためスキップ")
        return

    if already_posted_today(now):
        print("  今日は既に投稿済み")
        return

    print("  市場データ取得中...")
    market_data = get_market_data()
    print(f"  取得: {list(market_data.keys())}")

    print("  ブリーフ生成中...")
    brief = generate_brief(market_data, now)
    print(f"  生成完了: {len(brief)}文字")
    print(f"  内容: {brief[:100]}...")

    print("  note投稿中...")
    url = post_brief(brief, now)

    if url:
        print(f"  ✅ 投稿完了: {url}")
        save_log({"date": now.strftime("%Y-%m-%d"), "url": url})
    else:
        print("  ❌ 投稿失敗")


if __name__ == "__main__":
    main()
