"""
異常検知・アラートモジュール
- 投稿失敗の検出
- スキ数の急落（前週比 -50% 以上）
- 記事生成の停止（指定日数投稿なし）
- 検知結果を daily_report.py に渡す
"""
from __future__ import annotations

import datetime
import json
import os

JST = datetime.timezone(datetime.timedelta(hours=9))

_BASE = os.path.join(os.path.dirname(__file__), "..")
PERFORMANCE_PATH = os.path.join(_BASE, "data", "article_performance.json")
POSTED_PATH      = os.path.join(os.path.dirname(__file__), "..", "output", "posted.json")

# 閾値
STALE_DAYS            = 2    # N日以上投稿がなければアラート
LIKES_DROP_RATIO      = 0.5  # 前週比でスキ平均がこの割合以下に落ちたらアラート
MIN_ARTICLES_FOR_DROP = 3    # スキ急落判定に必要な最小記事数


def _load_performance() -> list[dict]:
    try:
        with open(PERFORMANCE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _parse_dt(s: str) -> datetime.datetime:
    try:
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt
    except Exception:
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def check_posting_staleness(perf: list[dict]) -> str | None:
    """最終投稿からN日以上経過していたらアラート"""
    if not perf:
        return "記事データが空です（DBが未初期化の可能性）"

    dates = [_parse_dt(p.get("posted_at", "")) for p in perf]
    latest = max(dates)
    now = datetime.datetime.now(JST)
    delta = now - latest

    if delta.days >= STALE_DAYS:
        return f"投稿が{delta.days}日間停止中（最終: {latest.strftime('%Y-%m-%d')}）"
    return None


def check_likes_drop(perf: list[dict]) -> str | None:
    """直近7日のスキ平均が前週比 50% 以下に落ちたらアラート"""
    now = datetime.datetime.now(JST)
    week1_start = now - datetime.timedelta(days=7)
    week2_start = now - datetime.timedelta(days=14)

    week1 = [
        p.get("latest_likes", 0) for p in perf
        if week1_start <= _parse_dt(p.get("posted_at", "")) <= now
    ]
    week2 = [
        p.get("latest_likes", 0) for p in perf
        if week2_start <= _parse_dt(p.get("posted_at", "")) < week1_start
    ]

    if len(week1) < MIN_ARTICLES_FOR_DROP or len(week2) < MIN_ARTICLES_FOR_DROP:
        return None  # データ不足で判定しない

    avg1 = sum(week1) / len(week1)
    avg2 = sum(week2) / len(week2)

    if avg2 > 0 and avg1 / avg2 < LIKES_DROP_RATIO:
        return (
            f"スキ数が急落: 先週平均 {avg2:.1f} → 今週平均 {avg1:.1f} "
            f"({avg1/avg2*100:.0f}%)"
        )
    return None


def check_zero_likes_streak(perf: list[dict], streak: int = 5) -> str | None:
    """直近N本の記事が全部スキ0だったらアラート"""
    recent = sorted(perf, key=lambda x: _parse_dt(x.get("posted_at", "")), reverse=True)[:streak]
    if len(recent) < streak:
        return None
    if all(p.get("latest_likes", 0) == 0 for p in recent):
        return f"直近{streak}本の記事がすべてスキ0です"
    return None


def check_posted_today() -> str | None:
    """本日の投稿が completed かどうか（posted.json の日付を確認）"""
    try:
        with open(POSTED_PATH, encoding="utf-8") as f:
            data = json.load(f)
        posted_at = data.get("posted_at", "")
        dt = _parse_dt(posted_at)
        today = datetime.datetime.now(JST).date()
        if dt.date() < today:
            return f"本日の投稿が見当たりません（最終: {dt.strftime('%Y-%m-%d')}）"
    except FileNotFoundError:
        return "posted.json が存在しません（初回実行または投稿失敗の可能性）"
    except Exception:
        pass
    return None


def run_checks() -> dict:
    """全チェックを実行してアラートリストを返す"""
    alerts = []
    perf = _load_performance()

    checks = [
        check_posting_staleness(perf),
        check_likes_drop(perf),
        check_zero_likes_streak(perf),
        check_posted_today(),
    ]

    for result in checks:
        if result:
            alerts.append(result)
            print(f"  🚨 異常検知: {result}")

    if not alerts:
        print("  ✅ 異常なし")

    return {"alerts": alerts, "checked_at": datetime.datetime.now(JST).isoformat()}


def main() -> None:
    print("=== 異常検知 ===")
    result = run_checks()
    if result["alerts"]:
        print(f"\n⚠️ {len(result['alerts'])}件のアラートが検出されました")
    return result


if __name__ == "__main__":
    main()
