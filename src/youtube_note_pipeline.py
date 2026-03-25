"""
YouTube note パイプライン

毎日の収集済みニュースから YouTube 向けに最適な題材を1本選び、
Claude で深掘りリサーチ → Gemini 3.0 で画像・表を挿入 → note に下書き保存する。

フロー:
  collected_news.json
    ↓ Gemini: YouTube向け題材を1本選定
  youtube_topic.json
    ↓ Claude CLI: 深掘りリサーチ記事生成（6000字以上）
  youtube_draft.json
    ↓ generate_images: 図表・画像挿入
  youtube_article_with_images.json
    ↓ post_to_note: note下書き保存
  youtube_posted.json
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
OUTPUT_DIR = Path("output")


# ─── Step 1: YouTube向け題材を1本選定 ─────────────────────────

def select_youtube_topic(articles: list[dict]) -> dict:
    """
    収集済みニュースから YouTube 動画に最も適した題材を1本 Gemini で選定する。

    YouTube向けの基準:
    - 「なぜ？」「どういうこと？」と視聴者が思うような背景・構造がある
    - 図解・グラフ・比較表で説明すると分かりやすい
    - 3〜10分動画で完結できるテーマの深さ
    - 日本人投資家が今週中に知るべきトピック
    """
    client = genai.Client(api_key=GEMINI_API_KEY)

    article_list = "\n".join(
        f"{i+1}. [{a['source']}] {a['title']}\n   {a['summary'][:150]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""あなたはYouTube投資チャンネルのプロデューサーです。
以下のニュース一覧から、**YouTube動画の題材として最も適した1本**を選んでください。

【YouTube題材として優れた基準（重要度順）】
1. **「なぜ？」「どういうこと？」と視聴者が思う構造的テーマ**
   - 単なるニュース報告ではなく、背景・仕組み・因果関係が説明できるもの
2. **図解・グラフ・比較表で説明すると格段に分かりやすい**
   - 数値の推移、複数要因の比較、仕組みの図解が映える
3. **3〜10分の動画で完結できる深さ**
   - 広すぎず狭すぎないスコープ
4. **日本人個人投資家が「今週知っておくべき」もの**

【ニュース一覧】
{article_list}

選んだ記事の番号と、その理由・動画タイトル案・視聴者に伝えたい3つのポイントをJSONで出力してください：
{{
  "index": 選んだ記事の番号（1始まり）,
  "reason": "YouTube題材として選んだ理由（50字以内）",
  "video_title": "YouTube動画タイトル案（必ず日本語・40字以内・疑問形推奨）",
  "key_points": ["伝えたいポイント1", "伝えたいポイント2", "伝えたいポイント3"],
  "chart_ideas": ["図解アイデア1", "図解アイデア2"]
}}
JSONのみ出力。余分な説明不要。"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=1024),
        )
        text = response.text.strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            idx = int(result.get("index", 1)) - 1
            idx = max(0, min(idx, len(articles) - 1))
            topic = {
                **articles[idx],
                "video_title":  result.get("video_title", articles[idx]["title"]),
                "reason":       result.get("reason", ""),
                "key_points":   result.get("key_points", []),
                "chart_ideas":  result.get("chart_ideas", []),
            }
            print(f"  YouTube題材選定: {topic['video_title']}")
            print(f"  選定理由: {topic['reason']}")
            return topic
    except Exception as e:
        print(f"  [WARN] 題材選定エラー: {e}")

    # フォールバック：先頭記事（タイトルは日本語に翻訳）
    fallback = articles[0]
    fallback_title = fallback["title"]
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"以下の英語タイトルを投資家向けに自然な日本語（40字以内）に翻訳してください。JSONで{{\"title\": \"...\"}}のみ出力。\n{fallback_title}",
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=100),
        )
        m2 = re.search(r'\{"title":\s*"([^"]+)"\}', resp.text)
        if m2:
            fallback_title = m2.group(1)
    except Exception:
        pass
    return {**fallback, "video_title": fallback_title, "key_points": [], "chart_ideas": []}


# ─── Step 2: Claude で深掘りリサーチ記事生成 ──────────────────

def generate_youtube_article(topic: dict) -> str:
    """
    Claude CLI でYouTube台本の元になる深掘りリサーチ記事を生成する。
    単なる要約ではなく「なぜ・どうなる・何に注目」を深く掘り下げる。
    """
    key_points = "\n".join(f"- {p}" for p in topic.get("key_points", []))
    chart_ideas = "\n".join(f"- {c}" for c in topic.get("chart_ideas", []))

    prompt = f"""あなたは投資歴20年以上のプロ投資家であり、YouTube投資チャンネルの台本ライターです。
以下のニューストピックについて、YouTube動画の元になる**深掘りリサーチ記事**を書いてください。

【トピック】
タイトル: {topic['title']}
ソース: {topic['source']}
概要: {topic.get('summary', '')}

【動画で伝えたいポイント】
{key_points or '（自由に設定）'}

【図解したいアイデア】
{chart_ideas or '（自由に設定）'}

---

## 記事構成（必ずこの順番・形式で書くこと）

## 導入：なぜ今これが重要なのか
（300字程度。視聴者の興味を引く冒頭。「実は〜」「知らないとヤバい〜」的な引き込み）

---

## 基本を理解する：そもそも何が起きているのか
（600字程度。小学生でも分かる平易な言葉で背景・経緯・仕組みを説明）

---

## 深掘り①：構造的背景と歴史的文脈
（800字程度。なぜこれが今起きているのか。業界トレンド・政策・歴史的経緯）

---

## 深掘り②：他の市場・銘柄・指標への連鎖
（800字程度。このニュースが何を引き起こすか芋づる式に展開。具体的な銘柄名・ETF名・セクター名を挙げる）

---

## 深掘り③：市場が見落としているリスクと機会
（600字程度。一般報道では語られない裏側の視点。強気・弱気の両シナリオ）

---

## 3ヶ月後・1年後のシナリオ
（600字程度。具体的な数値・銘柄・ETFを挙げながら2〜3シナリオを描く）

---

## 個人投資家へのアクションプラン
（400字程度。「まず何から調べるか」「いつ動くか」「何を買うか・避けるか」の具体的指針）

---

## まとめ：今日の3行要点
（3行箇条書き。動画の締めに使えるシンプルな結論）

---

【執筆ルール】
- 全体で**6000字以上**
- YouTube台本として読み上げやすい口語体（「〜なんです」「実は〜」「ちょっと待って」）
- 専門用語は必ず括弧で補足
- 数字は具体的に（「大幅」でなく「+3.5%」）
- 不確かな情報は「〜と報じられています」「〜とされています」と明記
- 断定はせず「〜を意識したい」「個人的には〜と見ている」の表現を使う
- 絵文字は使わない

記事本文のみ出力（前置き・コメント不要）。"""

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    claude_available = subprocess.run(["which", "claude"], capture_output=True).returncode == 0
    if claude_available:
        print("  Claude CLI で深掘りリサーチ中（6000字以上）...")
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text", "--model", "claude-opus-4-6"],
            capture_output=True, text=True, timeout=600, env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            article = result.stdout.strip()
            print(f"  Claude記事生成完了（{len(article)} 文字）")
            return article
        print(f"  [WARN] Claude CLI 失敗: {result.stderr[:200]}")

    # Gemini フォールバック
    print("  Gemini で深掘りリサーチ中（フォールバック）...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.6, max_output_tokens=16000),
    )
    article = response.text.strip()
    print(f"  Gemini記事生成完了（{len(article)} 文字）")
    return article


# ─── Step 3 & 4: 画像挿入 → note下書き ────────────────────────

def run_youtube_note_pipeline() -> dict:
    """YouTube noteパイプライン全体を実行する。"""

    # collected_news.json を読み込む
    news_path = OUTPUT_DIR / "collected_news.json"
    if not news_path.exists():
        raise FileNotFoundError("output/collected_news.json が見つかりません。先にcollect_news.pyを実行してください。")
    with open(news_path, encoding="utf-8") as f:
        articles = json.load(f)

    # ── Step 1: YouTube題材を1本選定 ──
    print("\n  [YouTube] 題材選定中...")
    topic = select_youtube_topic(articles)
    topic_path = OUTPUT_DIR / "youtube_topic.json"
    with open(topic_path, "w", encoding="utf-8") as f:
        json.dump(topic, f, ensure_ascii=False, indent=2)

    # ── Step 2: Claude で深掘りリサーチ記事生成 ──
    print("\n  [YouTube] Claude 深掘りリサーチ...")
    article_text = generate_youtube_article(topic)
    draft_data = {
        "polished":  article_text,
        "topic":     topic,
        "articles":  articles,
    }
    draft_path = OUTPUT_DIR / "youtube_draft.json"
    with open(draft_path, "w", encoding="utf-8") as f:
        json.dump(draft_data, f, ensure_ascii=False, indent=2)

    # ── Step 3: Gemini 3.0 で画像・図表挿入 ──
    # generate_images.main() は polished.json を読み article_with_images.json に書く。
    # 通常記事ファイルを保護するため、実行前後にバックアップ・リストアする。
    print("\n  [YouTube] Gemini 3.0 で画像・図表挿入...")
    import generate_images
    import shutil

    polished_path  = OUTPUT_DIR / "polished.json"
    awimg_path     = OUTPUT_DIR / "article_with_images.json"
    polished_bak   = OUTPUT_DIR / "polished.json.bak"
    awimg_bak      = OUTPUT_DIR / "article_with_images.json.bak"

    # バックアップ
    for src, dst in [(polished_path, polished_bak), (awimg_path, awimg_bak)]:
        if src.exists():
            shutil.copy2(src, dst)

    try:
        # YouTube 記事を polished.json として書き込み → generate_images.main() 実行
        with open(polished_path, "w", encoding="utf-8") as f:
            json.dump(draft_data, f, ensure_ascii=False, indent=2)
        generate_images.main()

        # 結果を youtube_article_with_images.json に保存
        yt_img_path = OUTPUT_DIR / "youtube_article_with_images.json"
        if awimg_path.exists():
            with open(awimg_path, encoding="utf-8") as f:
                img_data = json.load(f)
            img_data["video_title"] = topic.get("video_title", topic["title"])
            img_data["topic"] = topic
            with open(yt_img_path, "w", encoding="utf-8") as f:
                json.dump(img_data, f, ensure_ascii=False, indent=2)
        else:
            img_data = {"article": article_text, "image_paths": [], "cover_path": None}
    finally:
        # 通常記事ファイルをリストア
        for bak, dst in [(polished_bak, polished_path), (awimg_bak, awimg_path)]:
            if bak.exists():
                shutil.move(str(bak), str(dst))

    article_body = img_data.get("article", article_text)
    valid_paths  = img_data.get("image_paths", [])
    cover_path   = img_data.get("cover_path")

    # ── Step 4: note に下書き保存 ──
    print("\n  [YouTube] note 下書き保存...")
    import post_to_note

    video_title = topic.get("video_title", topic["title"])
    url = post_to_note.post_article(
        title=video_title,
        body=article_body,
        image_paths=valid_paths,
        tags=["投資", "YouTube", "マーケット", "深掘り"],
        headless=os.environ.get("HEADLESS", "true").lower() == "true",
        cover_path=cover_path,
    )
    result = {"url": url, "status": "success" if url else "failed"}

    posted_path = OUTPUT_DIR / "youtube_posted.json"
    with open(posted_path, "w", encoding="utf-8") as f:
        json.dump({
            "title":  video_title,
            "url":    url,
            "topic":  topic,
            "status": "success" if url else "failed",
        }, f, ensure_ascii=False, indent=2)

    print(f"\n  [YouTube] 完了: {result.get('url', '（URL取得失敗）')}")
    return result


def main():
    print("=== YouTube note パイプライン ===")
    run_youtube_note_pipeline()


if __name__ == "__main__":
    main()
