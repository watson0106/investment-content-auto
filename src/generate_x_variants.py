"""
1本のnote記事から、X(Twitter)に複数日数・複数時間帯で投稿できる
ツイートバリエーションを生成する。

なぜ複数バリエーションが必要か:
- 同一記事を1回ツイートだけだと、その時タイムラインを見ていない人に届かない
- 「朝の通勤」「昼休み」「夕方退社」「夜のゴルデンタイム」と層が違う
- 切り口を変えることで「2回見たけど別の話だと思って両方読む」が起きる

使い方:
  python generate_x_variants.py "<note URL>" "<記事タイトル>"
出力: output/x_variants.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"


def build_variants(url: str, title: str) -> list[dict]:
    """記事URLとタイトルから6パターンの予告ツイートを生成"""
    return [
        {
            "slot": "投稿当日 朝 (7:30-9:00)",
            "tone": "数字で釣る",
            "text": f"""半導体トップ銘柄の月曜朝シナリオ:

▶ 5EMA押し目 13,200〜13,300円で買い
▶ 損切り -1.7%（SL到達率10%）
▶ 利確 +4.0%（MFE中央値ライン）

普段はメンバーシップ限定の内容を、今日だけ公開しました。

{url}""",
        },
        {
            "slot": "投稿当日 昼 (12:00-13:00)",
            "tone": "問題提起型",
            "text": f"""「読み放題プラン980円って、結局何が読めるの？」

note のメンバーシップを検討する人なら誰でも引っかかる疑問だと思う。

実物を見ないと判断できないと思ったので、今朝の配信を丸ごと公開しました。

{title}
{url}""",
        },
        {
            "slot": "投稿当日 夜 (20:00-22:00)",
            "tone": "実績＆透明性",
            "text": f"""過去2年OOS検証で勝率57%、PF1.85、年率+47.92%。

ただし先週は2敗で-1.9%でした。勝てない週もあります。

それでも「いつ・いくらで・なぜ」を毎日数字で出す意味はあると思っています。

メンバーシップで毎朝届く配信を、今日だけそのまま公開しました。

{url}""",
        },
        {
            "slot": "翌日 朝 (再露出)",
            "tone": "ストーリー型",
            "text": f"""昨日、メンバーシップで普段配信している「半導体銘柄の具体的売買水準」を、無料記事として丸ごと公開しました。

買い水準・損切り・利確、すべて具体的な数字付きです。

「これに月¥980払う価値があるかどうか」自分で判断してもらえれば嬉しいです。

{url}""",
        },
        {
            "slot": "翌日 夜 (再露出)",
            "tone": "結論ファースト",
            "text": f"""結論: 投資noteの99%は「○○が上がる！」と煽って、有料記事は抽象論で終わる。

私はそれが嫌いなので、無料も有料も具体的な数字と行動可能なシナリオしか書きません。

今朝の配信を丸ごと公開してます。

{url}""",
        },
        {
            "slot": "投稿2日後 夕方 (最終露出)",
            "tone": "比較訴求",
            "text": f"""「月¥980で読み放題」のメンバーシップって何が読めるか?

私の場合、毎朝7時の銘柄分析(買値・損切り・利確まで)＋週1の実トレード結果＋月1のポートフォリオ全公開。

実物を見たい方はこちらをどうぞ:
{url}""",
        },
    ]


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://note.com/kawasewatson0106/n/XXXXXX"
    title = sys.argv[2] if len(sys.argv) > 2 else "月曜朝のメンバーシップ配信を今日だけ無料公開｜半導体トップ銘柄の具体的売買水準"

    variants = build_variants(url, title)

    out_path = OUTPUT_DIR / "x_variants.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        for v in variants:
            f.write(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            f.write(f"【{v['slot']}】({v['tone']})\n")
            f.write(f"文字数: {len(v['text'])}字\n")
            f.write(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            f.write(v["text"])
            f.write("\n\n")

    print(f"保存: {out_path}")
    print(f"バリエーション: {len(variants)}本")
    print()
    print("使い方: 各時間帯にコピペでXに投稿してください。")
    print("       同じ記事URLを6回露出させることで認知が一気に上がります。")


if __name__ == "__main__":
    main()
