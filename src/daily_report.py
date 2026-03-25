"""
日次パフォーマンスレポート通知
- LINE Notify または Slack Webhook でパイプライン結果を通知
- 環境変数 LINE_NOTIFY_TOKEN または SLACK_WEBHOOK_URL が設定されていれば送信
"""
from __future__ import annotations

import datetime
import json
import os
import urllib.request
import urllib.parse

JST = datetime.timezone(datetime.timedelta(hours=9))

_BASE = os.path.join(os.path.dirname(__file__), "..")
PERFORMANCE_PATH = os.path.join(_BASE, "data", "article_performance.json")
STRATEGY_PATH    = os.path.join(_BASE, "data", "strategy_state.json")


def _load_json(path: str) -> dict | list:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _send_line(message: str) -> bool:
    token = os.environ.get("LINE_NOTIFY_TOKEN", "")
    if not token:
        return False
    data = urllib.parse.urlencode({"message": message}).encode()
    req = urllib.request.Request(
        "https://notify-api.line.me/api/notify",
        data=data,
        headers={"Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print(f"  [WARN] LINE Notify 送信失敗: {e}")
        return False


def _send_slack(message: str) -> bool:
    url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        return False
    payload = json.dumps({"text": message}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print(f"  [WARN] Slack Webhook 送信失敗: {e}")
        return False


def _build_report(posted_url: str = "", anomaly_result: dict = None) -> str:
    now = datetime.datetime.now(JST)
    weekday = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]
    lines = [
        f"【TATSUJIN TRADE 日次レポート】",
        f"{now.strftime('%Y-%m-%d')} ({weekday})",
        "",
    ]

    # 投稿URL
    if posted_url:
        lines.append(f"✅ 本日の記事: {posted_url}")
    else:
        lines.append("⚠️ 本日の記事: 投稿URLなし")

    # パフォーマンスサマリー
    perf = _load_json(PERFORMANCE_PATH)
    if isinstance(perf, list) and perf:
        likes_list = [p.get("latest_likes", 0) for p in perf]
        total_articles = len(likes_list)
        avg_likes = sum(likes_list) / total_articles if total_articles else 0
        max_likes = max(likes_list) if likes_list else 0
        total_likes = sum(likes_list)

        # 直近7日の記事
        cutoff = now - datetime.timedelta(days=7)
        recent = [
            p for p in perf
            if _parse_dt(p.get("posted_at", "")) >= cutoff
        ]
        recent_avg = (
            sum(p.get("latest_likes", 0) for p in recent) / len(recent)
            if recent else 0
        )

        lines.append("")
        lines.append(f"📊 パフォーマンス")
        lines.append(f"  総記事数: {total_articles}本  総スキ: {total_likes}")
        lines.append(f"  全期間平均: {avg_likes:.1f}スキ  最高: {max_likes}スキ")
        lines.append(f"  直近7日平均: {recent_avg:.1f}スキ（{len(recent)}本）")

        # トップ3記事
        top3 = sorted(perf, key=lambda x: x.get("latest_likes", 0), reverse=True)[:3]
        if top3:
            lines.append("")
            lines.append("🏆 スキTOP3")
            for i, p in enumerate(top3, 1):
                title = p.get("title", "")[:25]
                likes = p.get("latest_likes", 0)
                lines.append(f"  {i}. {title}… ({likes}スキ)")

    # strategy_state サマリー
    state = _load_json(STRATEGY_PATH)
    if isinstance(state, dict) and state:
        best_days = state.get("best_posting_days", [])
        rec_style = state.get("recommended_title_style", "")
        if best_days:
            lines.append("")
            lines.append(f"💡 推奨: 投稿は{'/'.join(best_days[:2])}曜日、{rec_style}")

    # 異常検知結果
    if anomaly_result:
        alerts = anomaly_result.get("alerts", [])
        if alerts:
            lines.append("")
            lines.append(f"🚨 アラート ({len(alerts)}件)")
            for alert in alerts[:5]:
                lines.append(f"  ・{alert}")
        else:
            lines.append("")
            lines.append("✅ 異常なし")

    return "\n".join(lines)


def _parse_dt(s: str) -> datetime.datetime:
    try:
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt
    except Exception:
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def send_daily_report(posted_url: str = "", anomaly_result: dict = None) -> None:
    """LINE / Slack に日次レポートを送信"""
    if anomaly_result is None:
        anomaly_result = {}

    message = _build_report(posted_url=posted_url, anomaly_result=anomaly_result)
    print("\n── 日次レポート ──")
    print(message)

    sent = False
    if _send_line(message):
        print("  ✅ LINE Notify 送信完了")
        sent = True
    if _send_slack(message):
        print("  ✅ Slack Webhook 送信完了")
        sent = True
    if not sent:
        print("  [INFO] 通知先未設定（LINE_NOTIFY_TOKEN / SLACK_WEBHOOK_URL）")


def main() -> None:
    """単体実行用"""
    print("=== 日次レポート送信 ===")
    send_daily_report()


if __name__ == "__main__":
    main()
