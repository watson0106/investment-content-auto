"""
④ Gemini 画像生成で図表・グラフを挿入
記事本文を解析し、図表が効果的な箇所に画像を生成・挿入する
"""

from __future__ import annotations


import json
import os
import base64
import re
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]


def identify_chart_sections(article_text: str) -> list[dict]:
    """Claude / Gemini で図表が有効な箇所を特定"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""以下の投資記事を読み、図表・グラフを挿入すると読者の理解が深まる箇所を特定してください。

【記事】
{article_text[:3000]}

以下のJSON形式で最大3箇所を出力してください：
[
  {{
    "position": "段落の最初の10文字（挿入位置の目印）",
    "chart_type": "bar_chart / line_chart / table / pie_chart / heatmap のいずれか",
    "description": "日本語で図表の内容説明（例：直近12ヶ月のS&P500推移グラフ）",
    "prompt_en": "English prompt for image generation (concise, specific)"
  }}
]

JSONのみ出力してください。"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=1024),
    )

    try:
        text = response.text.strip()
        # JSON ブロックを抽出
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"  [WARN] 図表箇所特定エラー: {e}")

    return []


def generate_chart_image(section: dict, index: int) -> str | None:
    """Gemini で図表画像を生成して保存、ファイルパスを返す"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    image_prompt = (
        f"Create a clean, professional financial chart for a Japanese investment blog. "
        f"Type: {section['chart_type']}. "
        f"Content: {section['prompt_en']}. "
        f"Style: dark background, green/blue color scheme, clear labels, no text overlays."
    )

    try:
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=image_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["image", "text"],
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data:
                img_data = base64.b64decode(part.inline_data.data)
                os.makedirs("output/images", exist_ok=True)
                path = f"output/images/chart_{index}.png"
                with open(path, "wb") as f:
                    f.write(img_data)
                print(f"  画像生成: {path}")
                return path

    except Exception as e:
        print(f"  [WARN] 画像生成エラー ({section['description']}): {e}")

    return None


def insert_images_into_article(article_text: str, sections: list[dict], image_paths: list[str | None]) -> str:
    """記事テキストに画像プレースホルダーを挿入"""
    result = article_text
    inserted = 0

    for i, (section, path) in enumerate(zip(sections, image_paths)):
        if not path:
            continue
        pos_hint = section.get("position", "")
        desc = section.get("description", f"図表{i+1}")

        # 挿入位置を探す
        idx = result.find(pos_hint)
        if idx == -1:
            # 見つからなければ段落区切りで挿入
            paragraphs = result.split("\n\n")
            insert_at = min(len(paragraphs) // 2 + i, len(paragraphs) - 1)
            paragraphs.insert(insert_at, f"\n![{desc}]({path})\n*{desc}*\n")
            result = "\n\n".join(paragraphs)
        else:
            image_md = f"\n\n![{desc}]({path})\n*{desc}*\n\n"
            result = result[:idx] + image_md + result[idx:]

        inserted += 1

    print(f"  {inserted} 枚の画像を記事に挿入")
    return result


def main():
    print("=== ④ Gemini 画像生成 ===")

    with open("output/polished.json", encoding="utf-8") as f:
        data = json.load(f)

    article_text = data["polished"]

    # 図表箇所を特定
    print("  図表箇所を特定中...")
    sections = identify_chart_sections(article_text)
    print(f"  {len(sections)} 箇所の図表を生成予定")

    # 画像を生成
    image_paths = []
    for i, section in enumerate(sections):
        print(f"  [{i+1}/{len(sections)}] {section.get('description', '')}")
        path = generate_chart_image(section, i)
        image_paths.append(path)

    # 記事に挿入
    article_with_images = insert_images_into_article(article_text, sections, image_paths)

    result = {
        "article":     article_with_images,
        "image_paths": [p for p in image_paths if p],
        "articles":    data["articles"],
    }

    out_path = "output/article_with_images.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"保存: {out_path}")
    return result


if __name__ == "__main__":
    main()
