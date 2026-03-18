"""
① ニュース収集・ピックアップ
Bloomberg・日経（Nikkei Asia）・ロイター（スクレイピング）・Yahoo Finance・note の
リアルタイム情報を収集し、Gemini で最も注目度の高い記事を選定する
"""

from __future__ import annotations

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import json
import re
import os
from google import genai
from google.genai import types

JST = timezone(timedelta(hours=9))
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# 動作確認済み RSS ソース
RSS_SOURCES = [
    {"name": "Bloomberg Markets",    "url": "https://feeds.bloomberg.com/markets/news.rss"},
    {"name": "Bloomberg Technology", "url": "https://feeds.bloomberg.com/technology/news.rss"},
    {"name": "Nikkei Asia",          "url": "https://asia.nikkei.com/rss/feed/nar"},
    {"name": "Yahoo Finance",        "url": "https://finance.yahoo.com/news/rssindex"},
    {"name": "Yahoo Finance Japan",  "url": "https://news.yahoo.co.jp/rss/topics/business.xml"},
    {"name": "CNBC",                 "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"},
    {"name": "MarketWatch",          "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},
]


def fetch_feed(source: dict) -> list[dict]:
    """RSS フィードを取得してパース"""
    try:
        feed = feedparser.parse(source["url"], request_headers=HEADERS)
        articles = []
        cutoff = datetime.now(JST) - timedelta(hours=24)

        for entry in feed.entries[:30]:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(JST)
            if published and published < cutoff:
                continue

            title   = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            link    = entry.get("link", "")
            summary = BeautifulSoup(summary, "html.parser").get_text()[:500]

            if title:
                articles.append({
                    "source":    source["name"],
                    "title":     title,
                    "summary":   summary,
                    "url":       link,
                    "published": published.isoformat() if published else "",
                })
        return articles

    except Exception as e:
        print(f"  [WARN] {source['name']}: {e}")
        return []


def fetch_reuters_japan(max_articles: int = 20) -> list[dict]:
    """ロイター日本語版のマーケット記事をスクレイピング"""
    articles = []
    pages = [
        "https://jp.reuters.com/markets/",
        "https://jp.reuters.com/economy/",
    ]
    seen_hrefs = set()

    for page_url in pages:
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")

            for a in soup.select("a"):
                href = a.get("href", "")
                text = a.get_text(strip=True)

                # 記事URLパターン（英数字ID付き）
                if not re.search(r"/[A-Z0-9]{10,}", href):
                    continue
                if href in seen_hrefs or not text or len(text) < 10:
                    continue

                seen_hrefs.add(href)
                full_url = href if href.startswith("http") else f"https://jp.reuters.com{href}"
                articles.append({
                    "source":    "ロイター",
                    "title":     text[:200],
                    "summary":   "",
                    "url":       full_url,
                    "published": "",
                })

                if len(articles) >= max_articles:
                    break
        except Exception as e:
            print(f"  [WARN] ロイター({page_url}): {e}")

    print(f"  ロイター: {len(articles)} 件取得")
    return articles


def fetch_nikkei_web(max_articles: int = 15) -> list[dict]:
    """日経電子版のマーケット記事をスクレイピング"""
    articles = []
    try:
        resp = requests.get("https://www.nikkei.com/markets/", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.select("a"):
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            if "/article/" not in href and "/news/" not in href:
                continue

            full_url = href if href.startswith("http") else f"https://www.nikkei.com{href}"
            articles.append({
                "source":    "日経新聞",
                "title":     title[:200],
                "summary":   "",
                "url":       full_url,
                "published": "",
            })
            if len(articles) >= max_articles:
                break
    except Exception as e:
        print(f"  [WARN] 日経: {e}")

    print(f"  日経: {len(articles)} 件取得")
    return articles


def fetch_note_trending(max_articles: int = 10) -> list[dict]:
    """note.com API で投資関連トレンド記事を取得"""
    articles = []
    seen = set()
    queries = ["投資", "米国株", "日本株", "マーケット"]

    for q in queries:
        try:
            url = (
                f"https://note.com/api/v3/searches"
                f"?context=note&q={requests.utils.quote(q)}&size=5&sort=popular"
            )
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue

            data  = resp.json()
            notes = data.get("data", {}).get("notes", {}).get("contents", [])

            for note in notes:
                key   = note.get("key", "")
                title = note.get("name", "").strip()
                body  = note.get("body", "") or ""
                user  = note.get("user", {}).get("urlname", "")

                if not title or key in seen:
                    continue
                seen.add(key)

                articles.append({
                    "source":    "note",
                    "title":     title[:200],
                    "summary":   BeautifulSoup(body, "html.parser").get_text()[:300],
                    "url":       f"https://note.com/{user}/n/{key}",
                    "published": "",
                })
        except Exception as e:
            print(f"  [WARN] note({q}): {e}")

    print(f"  note: {len(articles)} 件取得")
    return articles


def deduplicate(articles: list[dict]) -> list[dict]:
    """タイトルの類似度で重複除去"""
    seen = []
    unique = []
    for art in articles:
        title = re.sub(r"[^\w\s]", "", art["title"].lower())
        words = set(title.split())
        if not words:
            continue
        is_dup = any(
            len(words & s) / max(len(words | s), 1) > 0.6
            for s in seen
        )
        if not is_dup:
            seen.append(words)
            unique.append(art)
    return unique


def interleave_by_source(articles: list[dict]) -> list[dict]:
    """ソースごとに均等にインターリーブして順番の偏りをなくす"""
    from collections import defaultdict
    import random
    buckets: dict[str, list] = defaultdict(list)
    for a in articles:
        buckets[a["source"]].append(a)
    result = []
    while any(buckets.values()):
        for src in list(buckets.keys()):
            if buckets[src]:
                result.append(buckets[src].pop(0))
    return result


def select_top_with_gemini(articles: list[dict], top_n: int = 10, history_summary: str = "") -> list[dict]:
    """Gemini で投資家にとって最も注目度の高い記事を選定"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    # ソースごとにインターリーブして順番の偏りをなくす
    articles = interleave_by_source(articles)

    article_list = "\n".join(
        f"{i+1}. [{a['source']}] {a['title']}\n   {a['summary'][:120]}"
        for i, a in enumerate(articles)
    )

    history_block = f"\n【過去に書いた記事テーマ（これらと重複するテーマは避けること）】\n{history_summary}\n" if history_summary and history_summary != "（過去記事なし）" else ""

    prompt = f"""あなたはプロの投資アナリストです。
以下のニュース一覧から、**本日の投資家にとって深く掘り下げる価値のある記事を{top_n}本**選んでください。
{history_block}
【選定基準（重要度順）】
1. **具体性・固有性が高い**：特定企業・特定セクター・特定政策・特定指標に関するニュース
   - 良い例：「NVIDIAが新GPU発表、データセンター向け需要が〜」「FRBのパウエル議長が〜と発言」「日本の春闘で〜%の賃上げ妥結」
   - 悪い例：「株式市場が上昇」「日経平均が〜円高」「マーケット概況」→ 毎日同じ内容になるためNG

2. **背景・構造的テーマがある**：一時的な数値変動ではなく、中長期の投資判断に使えるテーマ
   - 例：産業構造の変化、規制・政策の転換、企業の戦略転換、マクロ経済のトレンド変化

3. **日本人投資家に関連性がある**：日本株・円・日本企業・日本の経済政策に絡むものを優先

4. **3本の記事が互いに異なるテーマ**：同じ日に同じ話題ばかりにならないよう多様性を確保

【ニュース一覧】
{article_list}

選んだ記事の番号をJSON配列で出力してください（例：[1, 3, 7, 12, 15]）。
番号のみ、JSONのみ、説明不要。"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=256),
        )
        text = response.text.strip()
        match = re.search(r"\[[\d,\s]+\]", text)
        if match:
            indices = json.loads(match.group())
            selected = [articles[i - 1] for i in indices if 1 <= i <= len(articles)]
            if selected:
                print(f"  Gemini 選定: {len(selected)} 件")
                return selected[:top_n]
    except Exception as e:
        print(f"  [WARN] Gemini 選定失敗: {e}")

    return articles[:top_n]


def collect_and_rank(top_n: int = 10, history_summary: str = "") -> list[dict]:
    """全ソースからニュースを収集して Gemini で選定"""
    all_articles = []

    # RSS フィード
    for source in RSS_SOURCES:
        print(f"  取得中: {source['name']}")
        articles = fetch_feed(source)
        all_articles.extend(articles)

    # ロイター（スクレイピング）
    print("  取得中: ロイター日本語版")
    all_articles.extend(fetch_reuters_japan())

    # 日経（スクレイピング）
    print("  取得中: 日経新聞")
    all_articles.extend(fetch_nikkei_web())

    # note トレンド（API）
    print("  取得中: note トレンド")
    all_articles.extend(fetch_note_trending())

    print(f"  取得合計: {len(all_articles)} 件")

    # 重複除去
    unique = deduplicate(all_articles)
    print(f"  重複除去後: {len(unique)} 件")

    # Gemini で注目度選定
    print("  Gemini で注目度分析・選定中...")
    return select_top_with_gemini(unique, top_n=top_n, history_summary=history_summary)


def main():
    print("=== ① ニュース収集 ===")
    from article_history import load_history, build_history_summary
    history = load_history()
    history_summary = build_history_summary(history)
    if history:
        print(f"  過去記事履歴: {len(history)} 件参照")
    articles = collect_and_rank(top_n=10, history_summary=history_summary)

    os.makedirs("output", exist_ok=True)
    out_path = "output/collected_news.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\n選出記事 ({len(articles)} 件):")
    for i, a in enumerate(articles, 1):
        print(f"  {i}. [{a['source']}] {a['title'][:65]}")

    print(f"\n保存: {out_path}")
    return articles


if __name__ == "__main__":
    main()
