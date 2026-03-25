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

    prompt = f"""あなたは投資ブログの編集者です。以下の記事を読んで、**画像・図・グラフ・表を挿入すると読者の理解が格段に深まる箇所**を2〜4箇所特定してください。

【判断基準】
- 複数の数値・指標を比較している → 棒グラフ・表
- 時系列の変化・推移を説明している → 折れ線グラフ
- 複数の要因・仕組みを説明している → インフォグラフィック・概念図
- 構造・フロー・因果関係を説明している → フローチャート
- 複数の選択肢・シナリオを比較している → 比較表
- 割合・構成を説明している → 円グラフ

【記事全文】
{article_text[:6000]}

以下のJSON配列で出力してください（要素数は2〜4、JSONのみ、余分な説明不要）：
[
  {{
    "position": "挿入したい段落の最初の25文字をそのままコピー（完全一致）",
    "chart_type": "bar_chart|line_chart|pie_chart|table|infographic|comparison_table|flowchart|concept_diagram のいずれか",
    "description": "日本語での図表タイトル（20字以内）",
    "prompt_ja": "Geminiへの詳細な画像生成指示（日本語）。記事の具体的な内容・数値・銘柄名を反映した指示。タイトル・軸・凡例はすべて日本語。プロの金融メディア品質。300字以内。"
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

    # フォールバック：3箇所固定
    paragraphs = [p.strip() for p in article_text.split("\n\n") if len(p.strip()) > 50]
    total = len(paragraphs)
    return [
        {"position": paragraphs[total//4][:25] if total > 4 else "", "chart_type": "bar_chart",
         "description": "主要銘柄・指数の比較",
         "prompt_ja": "横棒グラフ。記事に登場する銘柄・指数の変動率を比較。プラスはゴールド、マイナスはネイビー。日本語。白背景。金融メディア風。"},
        {"position": paragraphs[total//2][:25] if total > 2 else "", "chart_type": "comparison_table",
         "description": "主要データ比較表",
         "prompt_ja": "シンプルな比較表。記事の主要な数値データを整理。ヘッダーはダークブルー背景に白文字。日本語。読みやすいフォント。"},
        {"position": paragraphs[total*3//4][:25] if total > 3 else "", "chart_type": "infographic",
         "description": "今日の投資ポイント",
         "prompt_ja": "縦型インフォグラフィック。本日の3大投資ポイントをアイコン付きで視覚的に整理。ダークネイビー背景にゴールド・ホワイトのテキスト。日本語。"},
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
}


def generate_chart_image(section: dict, index: int) -> str | None:
    """Gemini 3で図表・説明画像を生成"""
    desc = section.get("description", f"図表{index+1}")
    prompt_ja = section.get("prompt_ja", desc)
    chart_type = section.get("chart_type", "infographic")
    type_guide = _CHART_TYPE_GUIDE.get(chart_type, "")

    full_prompt = f"""日本の投資ブログ記事（note.com掲載）用の画像を作成してください。

【画像タイプ】{chart_type} — {type_guide}
【タイトル】{desc}
【詳細指示】
{prompt_ja}

【必須デザイン要件】
- テキスト・ラベル・凡例・数値は**すべて日本語**で記載
- 日本語フォントを使用（ゴシック体推奨）
- プロフェッショナルな金融・投資メディアに適したデザイン
- 16:9横長（note記事幅に最適）
- 高解像度・鮮明・読みやすい
- 情報が整理されていてひと目で要点が伝わる
- グラフ・表の場合は適切なグリッド・ボーダーを含める
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
