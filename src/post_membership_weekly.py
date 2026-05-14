"""
post_membership_weekly.py
毎週月曜9:00に「今週の注目銘柄ウォッチリスト」を自動生成・投稿する。

メンバーシップ会員向けコンテンツのサンプル公開版として投稿し、
「毎週このような分析を届けます」という形で会員獲得につなげる。

cron: 0 9 * * 1 (毎週月曜9:00)
実行: python3 ~/investment-content-auto/src/post_membership_weekly.py
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

JST = datetime.timezone(datetime.timedelta(hours=9))
MEMBERSHIP_URL = "https://note.com/kawasewatson0106/membership"
OUTPUT_PATH = BASE_DIR / "output" / "membership_weekly.json"
POSTED_LOG = BASE_DIR / "output" / "membership_posted.json"


def already_ran_this_week() -> bool:
    """今週すでに実行済みか確認"""
    if not POSTED_LOG.exists():
        return False
    try:
        log = json.loads(POSTED_LOG.read_text(encoding="utf-8"))
        last = log[-1].get("date", "") if log else ""
        if not last:
            return False
        last_dt = datetime.date.fromisoformat(last)
        today = datetime.date.today()
        # 同じ週（月曜基準）なら済みとみなす
        return today.isocalendar()[:2] == last_dt.isocalendar()[:2]
    except Exception:
        return False


def get_market_snapshot() -> dict:
    """yfinanceで主要市場データを取得"""
    try:
        import yfinance as yf
        tickers = {
            "ドル円": "JPY=X",
            "日経225": "^N225",
            "SP500": "^GSPC",
            "NASDAQ": "^IXIC",
            "VIX": "^VIX",
            "WTI原油": "CL=F",
            "米10年金利": "^TNX",
        }
        snapshot = {}
        for name, symbol in tickers.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d").dropna()
                if hist.empty:
                    continue
                last = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last
                chg = (last - prev) / prev * 100
                snapshot[name] = {"value": last, "change_pct": chg}
            except Exception:
                pass
        return snapshot
    except Exception:
        return {}


def get_top_stocks() -> list[dict]:
    """株探から売買代金上位銘柄を取得"""
    try:
        import requests
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        url = "https://kabutan.jp/warning/trading_value_ranking"
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        stocks = []
        for row in soup.select("table.stock_table tbody tr")[:20]:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            code_tag = row.find("a", href=re.compile(r"/stock/\?code="))
            if not code_tag:
                continue
            code = re.search(r"code=(\d{4})", code_tag["href"])
            if not code:
                continue
            code = code.group(1)
            # ETFや超低位株を除外
            if code in ("1360", "1570", "1321", "1306", "1330", "1545", "1546"):
                continue
            name = code_tag.text.strip()
            stocks.append({"code": code, "name": name})
        return stocks[:10]
    except Exception:
        return []


def generate_watchlist(market: dict, stocks: list[dict], today_str: str) -> str:
    """ウォッチリスト記事を生成（Claude CLI → Gemini フォールバック）"""
    from deep_research import run_claude, _call_gemini

    # 市場データの文字列化
    market_lines = []
    for name, data in market.items():
        val = data["value"]
        chg = data["change_pct"]
        sign = "+" if chg >= 0 else ""
        if name == "ドル円":
            market_lines.append(f"- {name}: {val:.2f}円（前日比{sign}{chg:.1f}%）")
        elif name in ("米10年金利", "VIX"):
            market_lines.append(f"- {name}: {val:.2f}（前日比{sign}{chg:.1f}%）")
        else:
            market_lines.append(f"- {name}: {val:,.0f}（前日比{sign}{chg:.1f}%）")
    market_block = "\n".join(market_lines) if market_lines else "（取得失敗）"

    stocks_block = "\n".join(
        f"- {s['name']}（{s['code']}）" for s in stocks
    ) if stocks else "（取得失敗）"

    prompt = f"""あなたは個人投資家ワトソンです。毎週月曜日に会員向けに「今週の注目銘柄ウォッチリスト」を書いています。
今週（{today_str}週）のレポートをブロガー口調で書いてください。

【今週の市場データ（必ずこの数値を使うこと）】
{market_block}

【先週の売買代金上位銘柄（この中から選定すること）】
{stocks_block}

【記事フォーマット（厳守）】
# 今週の相場環境

市場データをもとに、今週の相場環境を3〜4文で解説する。具体的な数値を使う。

## 今週ワトソンが注目している銘柄3選

### 1. 銘柄名（証券コード）
**注目理由（2〜3文）**
今週の注目価格帯：〇〇〜〇〇円
見通し：〇〇（強気/中立/警戒）

### 2. 銘柄名（証券コード）
（同様の形式）

### 3. 銘柄名（証券コード）
（同様の形式）

## 今週のリスク要因

今週特に注意すべきイベント・リスクを箇条書きで3つ。

## ワトソンの今週のスタンス

自分がどんな姿勢で今週の相場に臨むかを2〜3文で。「私は〜」という一人称で具体的に。

【文体ルール（必ず守ること）】
- 「です・ます」調で統一（断言形「〜だ」は禁止）
- ブロガー口調・友人に話すように書く
- 絵文字禁止
- 「〜においては」「〜という観点から」などのAI調禁止
- 同じカタカナ語を3回以上使わない
- 「リスク」は多くても2回まで（3回目からは「危うさ」「落とし穴」などに言い換え）
- 記事全体で800〜1200文字

記事本文のみ出力（前置きや説明不要）。"""

    result = run_claude(prompt, model="claude-sonnet-4-6", timeout=180)
    if result and len(result.strip()) > 200:
        return result.strip()
    # Claude CLI失敗時はGeminiにフォールバック
    print("  [INFO] Claude CLI失敗 → Gemini にフォールバック")
    result = _call_gemini(prompt)
    return result.strip() if result else ""


def build_article(body: str, today_str: str) -> str:
    """記事本文にCTAを追加して完成させる"""
    cta = f"""---

このウォッチリストは毎週月曜日にメンバーシップで公開しています。

今週は**サンプルとして全文公開**しています。通常は会員限定です。

- 月額980円（最初の1ヶ月は無料）
- 毎週月曜更新、ノイズなしの実践的な分析
- 「情報収集」を「売買判断」に変えたい方向け

{MEMBERSHIP_URL}

※本記事は情報提供を目的としており、投資勧誘ではありません。投資判断は必ずご自身で行ってください。"""

    return body + "\n\n" + cta


def post_to_note(title: str, body: str, cover_path: str = "") -> str:
    """note.comに投稿してURLを返す"""
    import post_to_note as ptr
    tags = ["投資", "株式投資", "資産運用", "日本株", "週次レポート"]
    article_data = {
        "title": title,
        "article": body,
        "tags": tags,
        "image_paths": [],
        "cover_path": cover_path,
    }
    tmp_path = str(BASE_DIR / "output" / "membership_tmp.json")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(article_data, f, ensure_ascii=False, indent=2)
    result = ptr.main(article_file=tmp_path, auto_publish=True)
    return result.get("url", "")


def log_posted(date_str: str, title: str, url: str):
    """投稿履歴を記録"""
    log = []
    if POSTED_LOG.exists():
        try:
            log = json.loads(POSTED_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    log.append({"date": date_str, "title": title, "url": url})
    POSTED_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    now = datetime.datetime.now(JST)
    today_str = now.strftime("%Y-%m-%d")
    week_str = f"{now.month}月{now.day}日"

    print(f"=== 会員限定週次ウォッチリスト 開始 {now.strftime('%Y-%m-%d %H:%M JST')} ===")

    if already_ran_this_week():
        print(f"  [SKIP] 今週はすでに実行済みです")
        sys.exit(0)

    # 市場データ取得
    print("  市場データ取得中...")
    market = get_market_snapshot()
    print(f"  取得完了: {len(market)}指標")

    # 売買代金上位取得
    print("  売買代金上位取得中...")
    stocks = get_top_stocks()
    print(f"  銘柄取得: {len(stocks)}件")

    # 記事生成
    print("  ウォッチリスト生成中...")
    body = generate_watchlist(market, stocks, week_str)
    if not body or len(body) < 300:
        print("❌ 記事生成失敗")
        sys.exit(1)
    print(f"  生成完了: {len(body)}文字")

    # CTA追加
    title = f"【今週のウォッチリスト】ワトソンが注目する銘柄3選（{week_str}週）"
    final_body = build_article(body, week_str)

    # note投稿
    print("  note投稿中...")
    try:
        url = post_to_note(title, final_body)
        print(f"  ✅ 公開完了: {url}")
    except Exception as e:
        print(f"  ❌ note投稿失敗: {e}")
        sys.exit(1)

    # 履歴記録
    log_posted(today_str, title, url)

    print(f"\n✅ 会員限定週次ウォッチリスト完了")
    print(f"   タイトル: {title}")
    print(f"   URL: {url}")
    return url


if __name__ == "__main__":
    main()
