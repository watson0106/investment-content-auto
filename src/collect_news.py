"""
① ニュース収集・ピックアップ
RSS フィードから投資ニュースを収集し、スコアリングしてピックアップする
"""

from __future__ import annotations


import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import json
import re
import os

JST = timezone(timedelta(hours=9))

RSS_SOURCES = [
    {"name": "Reuters Business",    "url": "https://feeds.reuters.com/reuters/businessNews"},
    {"name": "Reuters Markets",     "url": "https://feeds.reuters.com/reuters/marketsNews"},
    {"name": "Yahoo Finance",       "url": "https://finance.yahoo.com/news/rssindex"},
    {"name": "MarketWatch",         "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},
    {"name": "Bloomberg Markets",   "url": "https://feeds.bloomberg.com/markets/news.rss"},
    {"name": "Seeking Alpha",       "url": "https://seekingalpha.com/feed.xml"},
    {"name": "Investing.com",       "url": "https://www.investing.com/rss/news.rss"},
    {"name": "CNBC Top News",       "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"},
    {"name": "Financial Times",     "url": "https://www.ft.com/rss/home/japanese"},
    {"name": "日経新聞 マーケット", "url": "https://www.nikkei.com/rss/rss_nikkei_news.rdf"},
]

# 投資関連キーワード（スコアリング用）
HIGH_IMPACT_KEYWORDS = [
    "Fed", "FOMC", "interest rate", "inflation", "GDP", "earnings", "revenue",
    "profit", "guidance", "beat", "miss", "upgrade", "downgrade", "merger",
    "acquisition", "IPO", "bankruptcy", "recession", "rate cut", "rate hike",
    "金利", "利下げ", "利上げ", "インフレ", "決算", "GDP", "日銀", "Fed",
    "S&P", "Nasdaq", "Dow", "NVIDIA", "Apple", "Tesla", "Amazon", "Google",
    "景気", "株価", "為替", "円安", "円高", "米国株", "日本株", "半導体",
    "AI", "chip", "tariff", "関税", "trade war",
]

NOISE_KEYWORDS = ["スポーツ", "芸能", "天気", "ファッション", "レシピ", "旅行"]


def fetch_feed(source: dict) -> list[dict]:
    """RSS フィードを取得してパース"""
    try:
        feed = feedparser.parse(source["url"])
        articles = []
        cutoff = datetime.now(JST) - timedelta(hours=24)

        for entry in feed.entries[:30]:
            # 日時パース
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(JST)
            if published and published < cutoff:
                continue

            title   = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            link    = entry.get("link", "")

            # HTML タグを除去
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


def score_article(article: dict) -> float:
    """記事の投資関連スコアを計算"""
    text = (article["title"] + " " + article["summary"]).lower()

    # ノイズキーワードがあれば低スコア
    for kw in NOISE_KEYWORDS:
        if kw.lower() in text:
            return 0.0

    score = 0.0
    for kw in HIGH_IMPACT_KEYWORDS:
        if kw.lower() in text:
            score += 1.0

    # タイトルに含まれる場合はボーナス
    title_lower = article["title"].lower()
    for kw in HIGH_IMPACT_KEYWORDS:
        if kw.lower() in title_lower:
            score += 0.5

    return score


def deduplicate(articles: list[dict]) -> list[dict]:
    """タイトルの類似度で重複除去"""
    seen = []
    unique = []
    for art in articles:
        title = re.sub(r"[^\w\s]", "", art["title"].lower())
        words = set(title.split())
        is_dup = False
        for s in seen:
            overlap = len(words & s) / max(len(words | s), 1)
            if overlap > 0.6:
                is_dup = True
                break
        if not is_dup:
            seen.append(words)
            unique.append(art)
    return unique


def collect_and_rank(top_n: int = 10) -> list[dict]:
    """全ソースからニュースを収集してランキング"""
    all_articles = []

    for source in RSS_SOURCES:
        print(f"  取得中: {source['name']}")
        articles = fetch_feed(source)
        all_articles.extend(articles)

    print(f"  取得合計: {len(all_articles)} 件")

    # スコアリング
    for art in all_articles:
        art["score"] = score_article(art)

    # スコア順にソート
    all_articles.sort(key=lambda x: x["score"], reverse=True)

    # 重複除去
    unique = deduplicate(all_articles)

    # スコア > 0 のみ対象
    filtered = [a for a in unique if a["score"] > 0]

    print(f"  投資関連: {len(filtered)} 件 → 上位 {top_n} 件を選出")
    return filtered[:top_n]


def main():
    print("=== ① ニュース収集 ===")
    articles = collect_and_rank(top_n=10)

    os.makedirs("output", exist_ok=True)
    out_path = "output/collected_news.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\n選出記事 ({len(articles)} 件):")
    for i, a in enumerate(articles, 1):
        print(f"  {i}. [{a['score']:.1f}] {a['title'][:60]}  ({a['source']})")

    print(f"\n保存: {out_path}")
    return articles


if __name__ == "__main__":
    main()
