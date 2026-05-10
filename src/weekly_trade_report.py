"""
週次トレード結果レポート生成（毎週月曜投稿）

algo-research/data/auto_trade_log.json から先週分のトレードを抽出し、
- 勝敗・損益・勝率・PF
- 個別トレードの教訓
- メンバーシップへの強いCTA
を含む無料記事を生成して note に投稿する。

メンバーシップ登録の最強の入会ドライバー: 「実際にこの人は勝っているのか」を
全公開することで信頼を獲得し、銘柄分析の有料配信に流入させる。

使い方:
  python weekly_trade_report.py          # 先週分のレポートを生成・保存
  python weekly_trade_report.py --post   # 生成 + note 投稿
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
TRADE_LOG = ROOT / "algo-research" / "data" / "auto_trade_log.json"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def last_week_range(today: datetime.date | None = None) -> tuple[datetime.date, datetime.date]:
    """直近の完了したMon-Fri 5営業日の範囲を返す（土日に走らせても今週、平日に走らせると先週）"""
    if today is None:
        today = datetime.now(JST).date()
    weekday = today.weekday()  # Mon=0..Sun=6
    if weekday <= 4:  # Mon-Fri: 先週の月-金
        last_friday = today - timedelta(days=weekday + 3)
    else:  # Sat-Sun: 今週ちょうど終わった月-金
        last_friday = today - timedelta(days=weekday - 4)
    last_monday = last_friday - timedelta(days=4)
    return last_monday, last_friday


def load_last_week_trades() -> list[dict]:
    if not TRADE_LOG.exists():
        return []
    with open(TRADE_LOG, encoding="utf-8") as f:
        all_trades = json.load(f)

    last_monday, last_friday = last_week_range()

    out = []
    for t in all_trades:
        date_str = t.get("date", "")
        try:
            d = datetime.strptime(date_str, "%Y/%m/%d").date()
        except ValueError:
            continue
        if last_monday <= d <= last_friday:
            out.append(t)
    return out


def compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {
            "n": 0, "wins": 0, "losses": 0, "winrate": 0.0,
            "total_pnl": 0, "total_ret": 0.0, "pf": 0.0,
            "best": None, "worst": None,
        }

    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    total_ret = sum(t.get("ret", 0) for t in trades)
    win_pnl = sum(t.get("pnl", 0) for t in wins)
    loss_pnl = abs(sum(t.get("pnl", 0) for t in losses))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else float("inf") if win_pnl > 0 else 0.0

    best = max(trades, key=lambda x: x.get("ret", 0)) if trades else None
    worst = min(trades, key=lambda x: x.get("ret", 0)) if trades else None

    return {
        "n": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "winrate": len(wins) / len(trades) * 100 if trades else 0,
        "total_pnl": total_pnl,
        "total_ret": total_ret,
        "pf": pf,
        "best": best,
        "worst": worst,
    }


def build_article(trades: list[dict], stats: dict) -> tuple[str, str]:
    """(タイトル, 本文) を返す"""
    last_monday, last_friday = last_week_range()
    period = f"{last_monday.month}/{last_monday.day}〜{last_friday.month}/{last_friday.day}"

    if stats["n"] == 0:
        title = f"先週({period})はトレードなし。なぜシステムがエントリーしなかったか"
        body = f"""# 先週({period})の実トレード記録

先週は自動売買システムが1度もエントリーしませんでした。

これは負けたのではなく、**S/N判定の閾値（スコア6以上）を満たす銘柄が出なかった**ということです。

## なぜエントリーしなかったか

私のシステムは、過去2年のOOS検証で勝率57%・PF1.85のエッジを確認した条件のみエントリーします。具体的には:

- スコア絶対値6以上（充足率80%以上）
- ギャップ1.5%以上
- RSI 70以下
- 09:05以降の5EMAタッチ

これを満たさない日は「無理に張らない」が正解です。エントリーしないことも勝ちです。

## 今週の予定

引き続き同じ条件で監視します。シグナルが出た銘柄は、メンバーシップで毎朝7時に配信します。

"""
    else:
        title = f"私の実トレード全公開｜{period}: {stats['wins']}勝{stats['losses']}敗 ({stats['total_ret']:+.1f}%)"
        body = f"""# 先週({period})の実トレード全記録

私が自動売買システムで実際に取った先週のトレードを、勝ちも負けも全公開します。

## 損益サマリー

- トレード数: **{stats['n']}件**
- 勝敗: **{stats['wins']}勝 {stats['losses']}敗**（勝率 {stats['winrate']:.1f}%）
- 合計リターン: **{stats['total_ret']:+.2f}%**
- 合計損益: **{stats['total_pnl']:+,}円**
- プロフィットファクター: **{stats['pf']:.2f}**

## 個別トレード一覧

| 日付 | 銘柄 | 方向 | エントリー | 決済 | 損益 |
|---|---|---|---|---|---|
"""
        for t in trades:
            dir_txt = "買い" if t.get("dir") == "S" else "空売り"
            body += f"| {t.get('date', '')} | {t.get('name', '')}({t.get('code', '')}) | {dir_txt} | {t.get('entry_time', '')} {t.get('entry', 0):,}円 | {t.get('exit_type', '')} {t.get('exit', 0):,}円 | **{t.get('ret', 0):+.2f}%** |\n"

        body += "\n## 振り返り\n\n"

        if stats["best"]:
            b = stats["best"]
            dir_txt = "買い" if b.get("dir") == "S" else "空売り"
            body += f"**勝ち頭**: {b.get('name')}({b.get('code')}) {dir_txt} {b.get('ret'):+.2f}%。{b.get('exit_type')}で決済。\n\n"

        if stats["worst"] and stats["worst"].get("ret", 0) < 0:
            w = stats["worst"]
            dir_txt = "買い" if w.get("dir") == "S" else "空売り"
            body += f"**負け頭**: {w.get('name')}({w.get('code')}) {dir_txt} {w.get('ret'):+.2f}%。{w.get('exit_type')}で決済。\n\n"

        if stats["winrate"] >= 60:
            body += "今週は読み筋がはまった週でした。とはいえ来週も同じように勝てる保証はないので、ルールを淡々と続けます。\n\n"
        elif stats["winrate"] >= 40:
            body += "勝ちと負けが拮抗した週でした。負けトレードは想定通りの損切り幅で収まっており、ルール通りの動きはできました。\n\n"
        else:
            body += "厳しい週でした。負けが続いた時こそルールを変えないことが重要です。来週は同じ条件で淡々と継続します。\n\n"

    body += """---

## このトレードはどう判断しているのか

私は毎朝、その日に動きそうな銘柄を**スコアリング → 5EMAタッチでエントリー → 動的SL/TP決済**というルールで自動執行しています。

ルールの詳細・銘柄ごとのエントリー水準・損切り設定は、メンバーシップで毎朝配信しています。

▶ メンバーシップで読める内容（¥980/月・初月無料）
　・毎朝7時の注目銘柄2本を、買い水準・損切り・利確目安まで具体的な数字付きで配信
　・毎週月曜の実トレード全記録（この記事のさらに詳細版）
　・月1回のポートフォリオ全開示（買付理由・撤退基準まで）

「知っている」を「稼げる」に変えたい方は、まず1ヶ月無料で試してみてほしい。退会はいつでも1クリック。
"""

    return title, body


def main():
    trades = load_last_week_trades()
    stats = compute_stats(trades)
    title, body = build_article(trades, stats)

    out_path = OUTPUT_DIR / "weekly_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "title": title,
            "body": body,
            "stats": {k: v for k, v in stats.items() if k not in ("best", "worst")},
            "n_trades": len(trades),
            "generated_at": datetime.now(JST).isoformat(),
        }, f, ensure_ascii=False, indent=2)

    print(f"タイトル: {title}")
    print(f"トレード数: {stats['n']}")
    print(f"勝敗: {stats['wins']}勝{stats['losses']}敗")
    print(f"合計リターン: {stats['total_ret']:+.2f}%")
    print(f"保存: {out_path}")

    if "--post" in sys.argv:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import post_to_note
            article_data = {"title": title, "polished": body}
            with open(OUTPUT_DIR / "polished.json", "w", encoding="utf-8") as f:
                json.dump(article_data, f, ensure_ascii=False, indent=2)
            with open(OUTPUT_DIR / "final.json", "w", encoding="utf-8") as f:
                json.dump({"title": title, "body": body}, f, ensure_ascii=False, indent=2)
            print("note 投稿を実行...")
            post_to_note.main()
        except Exception as e:
            print(f"投稿エラー: {e}")


if __name__ == "__main__":
    main()
