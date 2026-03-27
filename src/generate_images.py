"""
④ Gemini 3 画像生成で図表・グラフ・説明画像を挿入
- カバー画像：記事内容から毎回Geminiで生成
- 本文画像：Geminiが記事全文を読み、画像で説明した方が分かりやすい箇所を判断して生成
  対応タイプ: 棒グラフ/折れ線/円グラフ/表/インフォグラフィック/比較図/概念図/フローチャートなど
"""

from __future__ import annotations

import json
import os
import re
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# 画像生成モデル（優先順）— Gemini 3 Pro を最優先
IMAGE_MODELS = [
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-image-preview",
    "gemini-2.5-flash-image",
]


def generate_image(prompt: str, path: str) -> str | None:
    """Geminiで画像を生成して保存。成功したらpathを返す"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    for model in IMAGE_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["image", "text"],
                ),
            )
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    img_data = part.inline_data.data
                    with open(path, "wb") as f:
                        f.write(img_data)
                    print(f"    生成完了 [{model}]: {os.path.basename(path)} ({len(img_data)//1024}KB)")
                    return path
        except Exception as e:
            print(f"    [WARN] {model} 失敗: {e}")
            continue

    # Imagen フォールバック
    try:
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1),
        )
        if response.generated_images:
            img_data = response.generated_images[0].image.image_bytes
            with open(path, "wb") as f:
                f.write(img_data)
            print(f"    生成完了 [imagen-4.0]: {os.path.basename(path)}")
            return path
    except Exception as e:
        print(f"    [WARN] imagen-4.0 失敗: {e}")

    return None


def generate_cover_image(article_text: str) -> str | None:
    """記事の3大ニュースをもとにカバー画像を生成（Gemini 3 Pro）"""
    # 今日のポイントセクションを抽出
    points_match = re.search(r'## 今日のポイント\s*(.*?)(?=---|\n##)', article_text, re.DOTALL)
    points = points_match.group(1).strip()[:400] if points_match else article_text[:400]

    # 記事タイトル（## ニュース①〜③）を抽出
    news_titles = re.findall(r'## ニュース[①②③]\s+(.+)', article_text)
    titles_block = "\n".join(f"・{t.strip()}" for t in news_titles[:3]) if news_titles else ""

    prompt = f"""note.com投資ブログのカバー画像（アイキャッチ）を作成してください。

【本日の主要ニュース】
{titles_block or points}

【デザイン要件】
- 画像上部に「今日の投資ニュース速報」を大きく日本語で入れる
- ダークネイビー〜黒のグラデーション背景にゴールド・ホワイトのテキスト
- 株式チャート・世界地図・データビジュアル・金融都市を組み合わせた迫力あるビジュアル
- Breaking News / 速報感のある緊張感あるレイアウト
- 16:9横長（1280×720以上）、高解像度
- noteのカバー画像として視覚的に映える品質
- 日本語テキストは鮮明で読みやすいフォント
"""

    print("  カバー画像生成中（Gemini 3 Pro）...")
    path = "output/images/cover.png"
    return generate_image(prompt, path)


def identify_chart_sections(article_text: str) -> list[dict]:
    """Gemini 2.5 Flashが記事全文を読み、画像で説明した方が分かりやすい箇所を2〜4箇所特定"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""あなたは投資ブログの編集者です。以下の記事を読んで、**画像があると読者の理解が格段に深まる箇所**を2〜4箇所特定してください。

【最重要ルール】
画像は「その段落を読んだ読者が、文章だけでは掴みにくいことを一目で理解できる」ものでなければならない。
記事の前後の文脈を無視した汎用的な画像（適当な棒グラフ、関係ない比較表など）は絶対NG。

【画像の種類と使い分け】
1. 記事に具体的な数値が3つ以上並んでいる段落 → その数値を正確に使ったグラフ・表
2. 複雑な仕組み・因果関係・プロセスを説明している段落 → 概念図・フローチャート
3. 市場の雰囲気・感情・状況を描写している段落 → その状況を象徴する写真風イメージ画像
4. シナリオ分析（強気/弱気等）→ シナリオの対比を視覚化したイメージ

【記事全文】
{article_text[:6000]}

以下のJSON配列で出力してください（要素数は2〜4、JSONのみ、余分な説明不要）：
[
  {{
    "position": "挿入したい段落の最初の25文字をそのままコピー（完全一致）",
    "context": "挿入箇所の前後300文字をそのままコピー（画像生成AIが文脈を理解するために必要）",
    "chart_type": "bar_chart|line_chart|pie_chart|table|infographic|comparison_table|flowchart|concept_diagram|image のいずれか",
    "description": "日本語での画像タイトル（20字以内）",
    "why": "この箇所に画像が必要な理由（読者がこの画像を見ることで何を理解できるか）を1文で",
    "prompt_ja": "Gemini画像生成への具体的な指示。記事の文脈（context）の内容を正確に反映すること。数値がある場合はその数値を使う。イメージ画像の場合は記事で語られている具体的な状況・テーマを描写する指示にする。500字以内。"
  }}
]"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=3000),
        )
        text = response.text.strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            sections = json.loads(match.group())
            if isinstance(sections, list) and sections:
                return sections[:4]
    except Exception as e:
        print(f"  [WARN] 図表箇所特定エラー: {e}")

    # フォールバック：記事テーマに合ったイメージ画像3枚
    paragraphs = [p.strip() for p in article_text.split("\n\n") if len(p.strip()) > 50]
    total = len(paragraphs)
    # 記事冒頭からキーワードを抽出
    snippet = article_text[:500]
    return [
        {"position": paragraphs[total//4][:25] if total > 4 else "", "chart_type": "image",
         "description": "記事テーマのイメージ",
         "prompt_ja": f"投資ブログ用のイメージ画像。記事テーマ:「{snippet[:100]}」を象徴する、株式市場・金融をテーマにした写真風の高品質画像。ダークトーン、プロフェッショナルな雰囲気。16:9横長。"},
        {"position": paragraphs[total//2][:25] if total > 2 else "", "chart_type": "image",
         "description": "市場分析イメージ",
         "prompt_ja": "投資家がモニターで株式チャートを分析している写真風イメージ。複数のモニターにチャートやデータが表示。プロフェッショナルな雰囲気。16:9横長。高品質。"},
        {"position": paragraphs[total*3//4][:25] if total > 3 else "", "chart_type": "image",
         "description": "投資戦略イメージ",
         "prompt_ja": "投資戦略・意思決定をイメージした写真風画像。チェスの駒、方位磁石、ロードマップなどの比喩的ビジュアル。ダークネイビー基調。16:9横長。高品質。"},
    ]


_CHART_TYPE_GUIDE = {
    "bar_chart":        "棒グラフ（縦棒または横棒）。複数項目の比較に最適。",
    "line_chart":       "折れ線グラフ。時系列の推移・トレンドを表現。",
    "pie_chart":        "円グラフ。割合・構成比を視覚化。",
    "table":            "データテーブル。数値を整理した見やすい表。",
    "comparison_table": "比較表。複数の選択肢・項目をマトリクスで比較。",
    "infographic":      "インフォグラフィック。複数の情報をビジュアルで整理。アイコンや矢印を活用。",
    "flowchart":        "フローチャート。因果関係・プロセスの流れを矢印で表現。",
    "concept_diagram":  "概念図。複雑な仕組みや構造を図解で説明。",
    "image":            "テーマに合ったイメージ画像。写真風またはイラスト風。記事の内容を視覚的に象徴するビジュアル。",
}


def generate_chart_image(section: dict, index: int) -> str | None:
    """Gemini 3で記事文脈に合った画像を生成"""
    desc = section.get("description", f"画像{index+1}")
    prompt_ja = section.get("prompt_ja", desc)
    chart_type = section.get("chart_type", "image")
    type_guide = _CHART_TYPE_GUIDE.get(chart_type, "")
    context = section.get("context", "")
    why = section.get("why", "")

    full_prompt = f"""日本の投資ブログ記事（note.com掲載）に挿入する画像を作成してください。

【この画像の目的】
{why}

【この画像が挿入される箇所の記事文脈】
{context}

【画像タイプ】{chart_type} — {type_guide}
【画像タイトル】{desc}
【詳細な画像生成指示】
{prompt_ja}

【デザイン要件】
- 16:9横長（1280×720以上）、高解像度
- プロフェッショナルな金融・投資メディアに適した品質
- グラフ・表の場合：テキスト・ラベル・数値はすべて日本語。記事中の実際の数値を正確に使う
- イメージ画像の場合：記事の文脈に合った具体的なシーン。汎用的なストック画像感を避ける
- 読者が「この画像があって理解が深まった」と感じるクオリティ
"""

    path = f"output/images/chart_{index}.png"
    return generate_image(full_prompt, path)


def insert_images_into_article(article_text: str, sections: list[dict], image_paths: list[str | None]) -> str:
    """記事テキストに画像プレースホルダー（__IMAGE_n__）を挿入"""
    result = article_text
    inserted = 0

    for i, (section, path) in enumerate(zip(sections, image_paths)):
        if not path:
            continue
        pos_hint = section.get("position", "")
        placeholder = f"\n__IMAGE_{i}__\n"

        idx = result.find(pos_hint) if pos_hint else -1
        if idx != -1:
            result = result[:idx] + placeholder + result[idx:]
        else:
            paragraphs = result.split("\n\n")
            total = len(paragraphs)
            n = len(sections)
            insert_at = min(int(total * (i + 1) / (n + 1)), total - 1)
            paragraphs.insert(insert_at, placeholder.strip())
            result = "\n\n".join(paragraphs)
        inserted += 1

    print(f"  本文画像 {inserted} 枚のプレースホルダーを挿入")
    return result


def main():
    print("=== ④ Gemini 3 画像生成（カバー＋本文図表・説明画像） ===")

    with open("output/polished.json", encoding="utf-8") as f:
        data = json.load(f)

    article_text = data["polished"]
    os.makedirs("output/images", exist_ok=True)

    # ── カバー画像 ────────────────────────────────
    cover_path = generate_cover_image(article_text)
    if cover_path:
        print(f"  カバー画像: {cover_path}")
    else:
        # フォールバック：固定カバー画像
        fixed = os.path.join(os.path.dirname(__file__), "..", "assets", "cover_image.png")
        cover_path = fixed if os.path.exists(fixed) else None
        print(f"  カバー画像: フォールバック使用")

    # ── 本文画像（図表・説明画像） ────────────────
    print("  画像挿入箇所を分析中（Gemini 2.5 Flashが記事全文を読んで判断）...")
    sections = identify_chart_sections(article_text)
    print(f"  {len(sections)} 箇所の画像を生成予定")
    for i, s in enumerate(sections):
        print(f"    [{i+1}] {s.get('description')} ({s.get('chart_type')})")

    image_paths = []
    for i, section in enumerate(sections):
        print(f"  [{i+1}/{len(sections)}] {section.get('description', '')} 生成中...")
        path = generate_chart_image(section, i)
        image_paths.append(path)

    article_with_images = insert_images_into_article(article_text, sections, image_paths)
    valid_paths = [p for p in image_paths if p]
    print(f"  合計 {len(valid_paths)} 枚の本文画像を挿入")

    result = {
        "article":      article_with_images,
        "image_paths":  valid_paths,
        "cover_path":   cover_path,
        "articles":     data["articles"],
    }

    out_path = "output/article_with_images.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"保存: {out_path}")
    return result


if __name__ == "__main__":
    main()
