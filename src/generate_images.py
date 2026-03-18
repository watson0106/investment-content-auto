"""
④ Gemini 画像生成で図表・グラフを挿入
記事本文を解析し、日本語の図表・グラフ画像を生成して挿入する
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


def identify_chart_sections(article_text: str) -> list[dict]:
    """Gemini で図表が有効な箇所を特定（3箇所確保）"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""以下の投資記事を読み、図表・グラフ・表を挿入すると読者の理解が深まる箇所を必ず3箇所特定してください。

【記事】
{article_text[:4000]}

以下のJSON配列を必ず3要素で出力してください（余分な説明は不要、JSONのみ）：
[
  {{
    "position": "この段落の最初の15文字をそのままコピー",
    "chart_type": "bar_chart",
    "description": "日本語での図表タイトル（例：S&P500と日経平均の比較グラフ）",
    "prompt_ja": "日本語で詳細な図表の指示（例：棒グラフ。S&P500と日経平均を比較。数値は架空でOK。タイトル・軸ラベル・凡例は日本語で）"
  }},
  {{
    "position": "別の段落の最初の15文字",
    "chart_type": "table",
    "description": "日本語での表タイトル",
    "prompt_ja": "表の詳細指示"
  }},
  {{
    "position": "さらに別の段落の最初の15文字",
    "chart_type": "line_chart",
    "description": "日本語での図表タイトル",
    "prompt_ja": "折れ線グラフの詳細指示"
  }}
]"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=2048),
        )
        text = response.text.strip()
        # JSONブロック抽出
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            sections = json.loads(match.group())
            if sections:
                return sections[:3]
    except Exception as e:
        print(f"  [WARN] 図表箇所特定エラー: {e}")

    # フォールバック：記事の構造から均等に3箇所選ぶ
    paragraphs = [p.strip() for p in article_text.split("\n\n") if len(p.strip()) > 50]
    total = len(paragraphs)
    fallback = []
    for i, (pos_idx, ctype, desc, prompt_ja) in enumerate([
        (total // 4,       "bar_chart",  "主要銘柄・指数の比較グラフ",
         "棒グラフ。記事に登場する株価指数や銘柄を比較。タイトル・軸・凡例は全て日本語。プロフェッショナルな金融チャート風。"),
        (total // 2,       "table",      "主要データ一覧表",
         "整理された表。記事の主要な数値データをまとめる。列ヘッダーは日本語。読みやすくシンプルなデザイン。"),
        (total * 3 // 4,   "line_chart", "市場動向の推移グラフ",
         "折れ線グラフ。株価や指数の時系列推移。タイトル・軸ラベル・凡例は日本語。金融チャート風。"),
    ]):
        if pos_idx < len(paragraphs):
            pos = paragraphs[pos_idx][:15]
        else:
            pos = ""
        fallback.append({
            "position": pos,
            "chart_type": ctype,
            "description": desc,
            "prompt_ja": prompt_ja,
        })
    return fallback


def generate_chart_image(section: dict, index: int, article_context: str = "") -> str | None:
    """Gemini で日本語図表画像を生成して保存"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    desc = section.get("description", f"図表{index+1}")
    prompt_ja = section.get("prompt_ja", desc)
    chart_type = section.get("chart_type", "chart")

    # 記事のコンテキストを踏まえた日本語プロンプト
    full_prompt = f"""以下の仕様で投資ブログ記事用の図表を作成してください。

【図表タイプ】{chart_type}
【タイトル】{desc}
【詳細指示】{prompt_ja}

【デザイン要件】
- 全てのテキスト（タイトル・軸ラベル・凡例・数値）を日本語で記載
- プロフェッショナルな金融・投資ブログに適したデザイン
- 背景は白またはライトグレー、見やすい配色
- フォントは明瞭で読みやすく
- 適切なグリッドラインを含める
"""

    os.makedirs("output/images", exist_ok=True)
    path = f"output/images/chart_{index}.png"

    for model in IMAGE_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["image", "text"],
                ),
            )
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    # inline_data.data はすでにバイト列（base64デコード不要）
                    img_data = part.inline_data.data
                    with open(path, "wb") as f:
                        f.write(img_data)
                    print(f"  画像生成完了 [{model}]: {path} ({len(img_data)//1024}KB)")
                    return path
        except Exception as e:
            print(f"  [WARN] {model} 失敗: {e}")
            continue

    # Imagen 4 フォールバック
    try:
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=full_prompt,
            config=types.GenerateImagesConfig(number_of_images=1),
        )
        if response.generated_images:
            img_data = response.generated_images[0].image.image_bytes
            with open(path, "wb") as f:
                f.write(img_data)
            print(f"  画像生成完了 [imagen-4.0]: {path}")
            return path
    except Exception as e:
        print(f"  [WARN] imagen-4.0 失敗: {e}")

    return None


def extract_headings(article_text: str) -> list[dict]:
    """記事から ## 見出しを全て抽出"""
    headings = []
    lines = article_text.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r'^#{1,3}\s+(.+)', line)
        if m:
            # 見出し直後の段落（最大200文字）をコンテキストとして取得
            context_lines = []
            for j in range(i + 1, min(i + 6, len(lines))):
                if lines[j].strip() and not re.match(r'^#+', lines[j]):
                    context_lines.append(lines[j].strip())
                    if len(" ".join(context_lines)) > 200:
                        break
            headings.append({
                "heading": m.group(1).strip(),
                "line": line,
                "context": " ".join(context_lines)[:200],
            })
    return headings


def generate_heading_image(heading: str, context: str, index: int) -> str | None:
    """見出しの内容から投資ブログ用イメージ画像を生成"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""投資・金融ブログの記事見出し用イメージ画像を作成してください。

【見出し】{heading}
【内容の概要】{context}

【デザイン要件】
- ビジネス・金融・投資をテーマにしたプロフェッショナルな写真風またはイラスト風
- 株式チャート・都市の夜景・グローバルな金融街・ビジネスマン・デジタルデータなどを活用
- 16:9横長構図（ブログのヘッダー画像として映える構図）
- 青・紺・金・白などのプロフェッショナルな配色
- テキストは最小限（見出しタイトルのみ日本語で右下or左下に小さく入れてもOK）
- 高品質でnote記事に映えるビジュアル
"""

    os.makedirs("output/images", exist_ok=True)
    path = f"output/images/heading_{index}.png"

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
                    print(f"    見出し画像生成完了 [{model}]: {path} ({len(img_data)//1024}KB)")
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
            print(f"    見出し画像生成完了 [imagen-4.0]: {path}")
            return path
    except Exception as e:
        print(f"    [WARN] imagen-4.0 失敗: {e}")

    return None


def insert_heading_images(article_text: str, headings: list[dict], heading_image_paths: list[str | None]) -> str:
    """各 ## 見出しの直下にイメージ画像を挿入"""
    result = article_text
    offset = 0  # 挿入によるインデックスずれを補正

    for heading_info, path in zip(headings, heading_image_paths):
        if not path:
            continue
        line = heading_info["line"]
        heading_text = heading_info["heading"]
        image_md = f"\n![{heading_text}]({path})\n"

        # 見出し行を検索して直後に挿入
        idx = result.find(line)
        if idx != -1:
            insert_pos = idx + len(line)
            result = result[:insert_pos] + image_md + result[insert_pos:]

    return result


def insert_images_into_article(article_text: str, sections: list[dict], image_paths: list[str | None]) -> str:
    """記事テキストに画像プレースホルダー（__IMAGE_n__）を挿入。実際の画像はpost_to_noteがペーストする"""
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
            insert_at = min(total // (3 - i) + i, total - 1)
            paragraphs.insert(insert_at, placeholder.strip())
            result = "\n\n".join(paragraphs)

        inserted += 1

    print(f"  図表 {inserted} 枚のプレースホルダーを挿入")
    return result


def main():
    print("=== ④ Gemini 画像生成（日本語図表） ===")

    with open("output/polished.json", encoding="utf-8") as f:
        data = json.load(f)

    article_text = data["polished"]

    # 図表箇所を特定（必ず3箇所）
    print("  図表箇所を特定中...")
    sections = identify_chart_sections(article_text)
    print(f"  {len(sections)} 箇所の図表を生成予定")
    for i, s in enumerate(sections):
        print(f"    [{i+1}] {s.get('description')} ({s.get('chart_type')})")

    image_paths = []
    for i, section in enumerate(sections):
        print(f"  [{i+1}/{len(sections)}] {section.get('description', '')} 生成中...")
        path = generate_chart_image(section, i, article_text[:1000])
        image_paths.append(path)

    article_with_images = insert_images_into_article(article_text, sections, image_paths)
    valid_paths = [p for p in image_paths if p]
    print(f"  合計 {len(valid_paths)} 枚の画像を挿入")

    result = {
        "article":     article_with_images,
        "image_paths": valid_paths,
        "articles":    data["articles"],
    }

    out_path = "output/article_with_images.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"保存: {out_path}")
    return result


if __name__ == "__main__":
    main()
