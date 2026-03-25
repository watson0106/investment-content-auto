"""
PDCAトラッカー
- 投稿済み記事のパフォーマンス（スキ数）を追跡
- 週次で分析し strategy_state.json を更新
- deep_research.py / generate_title.py が参照して記事品質を自動改善
"""
from __future__ import annotations

import json
import os
import re
import time
import requests
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

_BASE = os.path.join(os.path.dirname(__file__), "..")
PERF_PATH    = os.path.join(_BASE, "data", "article_performance.json")
STATE_PATH   = os.path.join(_BASE, "data", "strategy_state.json")


# ─── 保存・読み込み ──────────────────────────────────────────────

def _ensure_data_dir():
    os.makedirs(os.path.join(_BASE, "data"), exist_ok=True)


def load_performance() -> list[dict]:
    try:
        with open(PERF_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_performance(data: list[dict]) -> None:
    _ensure_data_dir()
    with open(PERF_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_strategy_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_strategy_state(state: dict) -> None:
    _ensure_data_dir()
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ─── 記事登録 ────────────────────────────────────────────────────

def _classify_title_pattern(title: str) -> str:
    """タイトルのパターンを分類"""
    if re.search(r"[？?]", title) and re.search(r"\d", title):
        return "疑問形+数字"
    elif re.search(r"[？?]", title):
        return "疑問形"
    elif re.search(r"\d+[%％]", title):
        return "パーセント数字"
    elif "なぜ" in title or "どうして" in title:
        return "逆張り・理由系"
    elif re.search(r"私|俺|僕", title):
        return "一人称"
    elif re.search(r"\d", title):
        return "数字あり"
    else:
        return "その他"


def record_posted_article(
    note_key: str,
    title: str,
    source_news: list[str] = None,
    is_paid: bool = False,
    price: int = 0,
) -> None:
    """投稿済み記事をパフォーマンスDBに登録"""
    perf = load_performance()
    # 重複チェック
    if any(p["note_key"] == note_key for p in perf):
        return

    # トピックキーワードを簡易抽出
    keywords = []
    keyword_candidates = [
        "FRB", "Fed", "金利", "利下げ", "利上げ",
        "NVIDIA", "半導体", "AI", "エヌビディア",
        "任天堂", "ソフトバンク", "トヨタ",
        "円安", "円高", "為替", "ドル",
        "日経", "S&P", "ナスダック", "NISA",
        "原油", "金", "ゴールド",
    ]
    for kw in keyword_candidates:
        if kw in title or any(kw in (n or "") for n in (source_news or [])):
            keywords.append(kw)

    entry = {
        "note_key":      note_key,
        "title":         title,
        "posted_at":     datetime.now(JST).isoformat(),
        "weekday":       ["月", "火", "水", "木", "金", "土", "日"][datetime.now(JST).weekday()],
        "is_paid":       is_paid,
        "price":         price,
        "topic_keywords": keywords[:6],
        "title_pattern": _classify_title_pattern(title),
        "source_news":   (source_news or [])[:3],
        "likes_history": [],
        "latest_likes":  0,
        "last_checked_at": None,
    }
    perf.append(entry)
    save_performance(perf)
    print(f"  [PDCA] 記事登録: {note_key} | {title[:30]}")


# ─── スキ数取得 ──────────────────────────────────────────────────

def _fetch_all_likes_from_creator_api(username: str = "kawasewatson0106") -> dict[str, int]:
    """クリエイターコンテンツ API で全記事のスキ数をまとめて取得（key→likes の dict）"""
    result: dict[str, int] = {}
    page = 1
    while True:
        try:
            url = f"https://note.com/api/v2/creators/{username}/contents?kind=note&page={page}"
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                break
            data = resp.json()
            contents = data.get("data", {}).get("contents", [])
            if not contents:
                break
            for item in contents:
                key = item.get("key", "")
                likes = item.get("likeCount", 0)
                if key:
                    result[key] = likes
            if data.get("data", {}).get("isLastPage", True):
                break
            page += 1
            time.sleep(0.3)
        except Exception as e:
            print(f"  [WARN] クリエイターAPI取得失敗 (page={page}): {e}")
            break
    return result


def update_likes_for_recent_articles(days: int = 30) -> int:
    """直近N日分の記事のスキ数を更新。更新件数を返す"""
    perf = load_performance()
    if not perf:
        return 0

    now = datetime.now(JST)
    cutoff = now - timedelta(days=days)

    # 直近N日の記事キーを抽出
    target_keys = set()
    for entry in perf:
        try:
            posted = datetime.fromisoformat(entry["posted_at"])
            if posted >= cutoff:
                target_keys.add(entry["note_key"])
        except Exception:
            continue

    if not target_keys:
        return 0

    # クリエイターAPIで全スキ数を一括取得
    likes_map = _fetch_all_likes_from_creator_api()
    updated = 0

    for entry in perf:
        if entry["note_key"] not in target_keys:
            continue
        likes = likes_map.get(entry["note_key"])
        if likes is not None:
            entry["latest_likes"] = likes
            entry["last_checked_at"] = now.isoformat()
            entry.setdefault("likes_history", []).append({
                "checked_at": now.isoformat(),
                "likes": likes,
            })
            entry["likes_history"] = entry["likes_history"][-30:]
            updated += 1

    save_performance(perf)
    print(f"  [PDCA] スキ数更新: {updated}件")
    return updated


# ─── 週次分析 ────────────────────────────────────────────────────

def analyze_weekly_performance(days: int = 30) -> dict:
    """過去N日のデータを分析してパターンを抽出"""
    perf = load_performance()
    now = datetime.now(JST)
    cutoff = now - timedelta(days=days)

    # 直近N日の記事だけ対象
    recent = []
    for entry in perf:
        try:
            posted = datetime.fromisoformat(entry["posted_at"])
            if posted >= cutoff:
                recent.append(entry)
        except Exception:
            continue

    if not recent:
        print("  [PDCA] 分析対象データなし")
        return {}

    # ── 曜日別平均スキ ──
    by_weekday: dict[str, list[int]] = {}
    for e in recent:
        wd = e.get("weekday", "?")
        by_weekday.setdefault(wd, []).append(e.get("latest_likes", 0))
    avg_by_weekday = {wd: round(sum(v)/len(v), 1) for wd, v in by_weekday.items()}

    # ── トピックキーワード別平均スキ ──
    by_kw: dict[str, list[int]] = {}
    for e in recent:
        for kw in e.get("topic_keywords", []):
            by_kw.setdefault(kw, []).append(e.get("latest_likes", 0))
    top_topics = sorted(
        [{"topic": kw, "avg_likes": round(sum(v)/len(v), 1), "count": len(v)}
         for kw, v in by_kw.items() if len(v) >= 2],
        key=lambda x: x["avg_likes"], reverse=True
    )[:5]

    # ── タイトルパターン別平均スキ ──
    by_pattern: dict[str, list[int]] = {}
    for e in recent:
        pat = e.get("title_pattern", "その他")
        by_pattern.setdefault(pat, []).append(e.get("latest_likes", 0))
    top_patterns = sorted(
        [{"pattern": pat, "avg_likes": round(sum(v)/len(v), 1), "count": len(v)}
         for pat, v in by_pattern.items()],
        key=lambda x: x["avg_likes"], reverse=True
    )[:3]

    # ── ベスト曜日 ──
    best_days = sorted(avg_by_weekday, key=lambda d: avg_by_weekday.get(d, 0), reverse=True)[:2]

    # ── 避けるべきトピック（スキが0が多い） ──
    avoid = [
        kw for kw, v in by_kw.items()
        if len(v) >= 3 and sum(v)/len(v) < 1.5
    ][:3]

    # ── 推奨タイトルスタイル ──
    best_pattern = top_patterns[0]["pattern"] if top_patterns else "疑問形+数字"
    # ベストパターンに対応する例をrecentから取得
    best_examples = [
        e["title"] for e in sorted(recent, key=lambda x: x.get("latest_likes", 0), reverse=True)
        if e.get("title_pattern") == best_pattern
    ][:2]
    style_desc = best_pattern
    if best_examples:
        style_desc += f"（例：「{best_examples[0][:25]}」）"

    analysis = {
        "last_updated":          now.strftime("%Y-%m-%d"),
        "analysis_period_days":  days,
        "articles_analyzed":     len(recent),
        "avg_likes_overall":     round(sum(e.get("latest_likes", 0) for e in recent) / len(recent), 1),
        "top_topics":            top_topics,
        "top_title_patterns":    top_patterns,
        "best_posting_days":     best_days,
        "avg_likes_by_weekday":  avg_by_weekday,
        "recommended_topics":    [t["topic"] for t in top_topics[:3]],
        "recommended_title_style": style_desc,
        "avoid_topics":          avoid,
    }
    return analysis


def update_strategy_state(analysis: dict) -> None:
    """分析結果を strategy_state.json に保存（既存の paid_article_history は保持）"""
    if not analysis:
        return
    existing = load_strategy_state()
    # paid_article_history は上書きしない
    if "paid_article_history" in existing:
        analysis["paid_article_history"] = existing["paid_article_history"]
    save_strategy_state(analysis)
    print(f"  [PDCA] strategy_state.json 更新: トピック上位={[t['topic'] for t in analysis.get('top_topics', [])[:3]]}")


# ─── エントリポイント ─────────────────────────────────────────────

def main(mode: str = "daily") -> None:
    """
    mode="daily"  → スキ数を更新のみ
    mode="weekly" → スキ数更新 + 週次分析 + strategy_state.json 更新
    """
    print(f"=== PDCA トラッカー（{mode}モード） ===")
    update_likes_for_recent_articles(days=30)

    if mode == "weekly":
        print("  週次分析を実行中...")
        analysis = analyze_weekly_performance(days=30)
        if analysis:
            update_strategy_state(analysis)
            print(f"  分析完了: {analysis.get('articles_analyzed', 0)}記事 | "
                  f"平均スキ{analysis.get('avg_likes_overall', 0)}")
        else:
            print("  [WARN] 分析データ不足")


if __name__ == "__main__":
    import sys
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "daily"
    main(mode_arg)
