"""
④ Gemini 画像生成で図表・グラフを挿入
- カバー画像：記事内容から毎回Geminiで生成
- 本文画像：Geminiが必要数・挿入箇所を判断して生成
"""

from __future__ import annotations

import json
import os
import re
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# 画像生成に使うモデル（優先順）
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
    """記事の3大ニュースをもとにカバー画像を生成"""
    # 今日のポイントセクションを抽出
    points_match = re.search(r'## 今日のポイント\s*(.*?)(?=---|\n##)', article_text, re.DOTALL)
    points = points_match.group(1).strip()[:300] if points_match else article_text[:300]

    prompt = f"""投資ニュース速報ブログのカバー画像を作成してください。

【今日のニュース概要】
{points}

【デザイン要件】
- 「新聞よりわかりやすくて早い 今日の投資ニュース速報」というタイトルを画像上部に大きく日本語で入れる
- ダークな背景（深い青・黒・グレー）にゴールドや白のテキスト
- 世界の政治家・経営者・金融街・株式チャート・データを組み合わせた迫力あるビジュアル
- ニュース速報・BREAKING感のある緊張感あるデザイン
- 16:9横長、高解像度、noteのカバー画像として映える品質
"""

    print("  カバー画像生成中...")
    path = "output/images/cover.png"
    return generate_image(prompt, path)


def identify_chart_sections(article_text: str) -> list[dict]:
    """Geminiが記事を分析して図表が効果的な箇所と数を決定（2〜4箇所）"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""以下の投資記事を読み、図表・グラフ・表を挿入すると読者の理解が最も深まる箇所を**2〜4箇所**特定してください。
数は記事の内容に応じて判断してください（データが多い記事は多め、少ない記事は少なめ）。

【記事】
{article_text[:5000]}

以下のJSON配列で出力してください（要素数は2〜4、余分な説明不要、JSONのみ）：
[
  {{
    "position": "この段落の最初の20文字をそのままコピー",
    "chart_type": "bar_chart|line_chart|table|pie_chart のいずれか",
    "description": "日本語での図表タイトル",
    "prompt_ja": "日本語で詳細な図表の指示（タイトル・軸・凡例は全て日本語、数値は架空でOK、プロ品質）"
  }}
]"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=2048),
        )
        text = response.text.strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            sections = json.loads(match.group())
            if isinstance(sections, list) and sections:
                return sections[:4]
    except Exception as e:
        print(f"  [WARN] 図表箇所特定エラー: {e}")

    # フォールバック：3箇所固定
    paragraphs = [p.strip() for p in article_text.split("\n\n") if len(p.strip()) > 50]
    total = len(paragraphs)
    return [
        {"position": paragraphs[total//4][:20] if total > 4 else "", "chart_type": "bar_chart",
         "description": "主要銘柄・指数の比較", "prompt_ja": "棒グラフ。記事に登場する銘柄・指数を比較。日本語。金融チャート風。"},
        {"position": paragraphs[total//2][:20] if total > 2 else "", "chart_type": "table",
         "description": "主要データ一覧", "prompt_ja": "整理された表。記事の主要な数値データ。日本語。シンプルで読みやすい。"},
        {"position": paragraphs[total*3//4][:20] if total > 3 else "", "chart_type": "line_chart",
         "description": "市場動向の推移", "prompt_ja": "折れ線グラフ。株価や指数の推移。日本語。金融チャート風。"},
    ]


def generate_chart_image(section: dict, index: int) -> str | None:
    """Geminiで図表画像を生成"""
    desc = section.get("description", f"図表{index+1}")
    prompt_ja = section.get("prompt_ja", desc)
    chart_type = section.get("chart_type", "chart")

    full_prompt = f"""投資ブログ記事用の図表を作成してください。

【図表タイプ】{chart_type}
【タイトル】{desc}
【詳細指示】{prompt_ja}

【デザイン要件】
- 全テキスト（タイトル・軸ラベル・凡例・数値）を日本語で記載
- プロフェッショナルな金融・投資ブログに適したデザイン
- 背景は白またはライトグレー、見やすい配色
- フォントは明瞭で読みやすく
- 適切なグリッドラインを含める
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
    print("=== ④ Gemini 画像生成（カバー画像＋本文図表） ===")

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

    # ── 本文図表 ──────────────────────────────────
    print("  図表箇所を特定中（Geminiが枚数を判断）...")
    sections = identify_chart_sections(article_text)
    print(f"  {len(sections)} 箇所の図表を生成予定")
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
