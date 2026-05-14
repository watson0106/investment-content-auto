"""
post_evergreen.py
毎週土曜10:00に「保存版・手法解説」記事を自動生成・note下書き保存する。

「なぜ〇〇株」型の速報記事とは異なる、時間が経っても価値が失われない
エバーグリーンコンテンツを週1本投稿することで：
- フォロワーの信頼・エンゲージメントを回復
- 「保存・引用」が増えてリーチが拡大
- サブスクメンバーシップへの自然な誘導

実行: python3 ~/investment-content-auto/src/post_evergreen.py
cron: 0 10 * * 6 (毎週土曜10:00)
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import datetime
from pathlib import Path

# パス設定
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

JST = datetime.timezone(datetime.timedelta(hours=9))

# ── エバーグリーンテーマ一覧 ──────────────────────────────────
# 時間が経っても価値が失われないテーマ。スキTOP10の傾向（保存版・手法・大きな問い）から設計。
EVERGREEN_THEMES = [
    {
        "title_template": "【保存版】私が絶対にエントリーしない相場の条件",
        "theme": "テクニカル分析の観点から、エントリーしてはいけない相場状況（出来高が薄い、上髭・下髭が異常に長い、MACDがデッドクロス直後など）を5つ解説する。具体的なチャートパターンと理由を詳しく説明する。",
        "tags": ["テクニカル分析", "投資"],
    },
    {
        "title_template": "NISA口座で個別株を買う前に知っておくべき、たった1つの事実",
        "theme": "NISAの非課税メリットは損失が出たときに最も悪影響が出る（損益通算ができない）という逆説を中心に、NISAで個別株投資をするリスクとその対策を解説する。",
        "tags": ["NISA", "投資"],
    },
    {
        "title_template": "「売り時がわからない」を卒業する、私の利確ルール3つ",
        "theme": "利確の判断基準として①目標株価到達 ②保有期間ルール ③テクニカルシグナル（週足での売りシグナル）の3つを具体的に解説。感情に左右されない機械的な利確の重要性を説く。",
        "tags": ["投資", "株式投資"],
    },
    {
        "title_template": "株で「普通の人」が勝てない本当の理由──プロとの情報格差の正体",
        "theme": "機関投資家との情報格差・スピード格差を正直に認めた上で、個人投資家が有利に戦える唯一の土俵（長期保有・ニッチセクター・忍耐力）について解説する。フィリップ・フィッシャーの教えも引用。",
        "tags": ["投資", "資産運用"],
    },
    {
        "title_template": "【実例付き】私が「これは見送り」と判断した銘柄の共通点",
        "theme": "投資判断において「買わない理由」を明確にすることの重要性。見送り判断の具体的な基準（バリュエーション・チャート形状・マクロ環境）を、実際の過去事例（銘柄名は仮名）を使って解説する。",
        "tags": ["株式投資", "資産運用"],
    },
    {
        "title_template": "「損切りできない」を治す方法──心理学と実践ルールで解決する",
        "theme": "損失回避バイアス（プロスペクト理論）をわかりやすく説明した上で、機械的な損切りルール（エントリー価格から-7%など）の設定方法と、損切り後の心理的リカバリー方法を解説する。",
        "tags": ["投資", "株式投資"],
    },
    {
        "title_template": "日本株と米国株、どっちで戦うべきか？私の結論",
        "theme": "為替リスク・情報量・流動性・税制の観点から日米株を比較し、自分の状況に応じた選択基準を提示。「どっちが正解か」ではなく「自分にとってどっちが向いているか」という切り口で解説する。",
        "tags": ["日本株", "米国株"],
    },
    {
        "title_template": "チャートを見る前に確認すべき、ファンダメンタルズの3つの指標",
        "theme": "PER・PBR・ROEの3指標を初心者にもわかるように解説し、チャート分析の前にこれらを確認することで「テクニカルのダマシ」に引っかかる確率が下がることを説明する。",
        "tags": ["テクニカル分析", "株式投資"],
    },
    # ── 追加テーマ（PDCAスキTOP分析から：「大きな問い」「長期ストーリー」型） ──
    {
        "title_template": "バフェットが現金を積み上げ続ける理由──私の投資判断に与えた影響",
        "theme": "バフェットのバークシャー・ハサウェイが2024〜2025年にかけて現金保有を大幅に増やした事実を紹介。その理由の考察（割高な市場・次の暴落への備え・絶好の投資機会待ち）と、個人投資家として私がどう行動を変えたかを個人の体験として語る。",
        "tags": ["米国株", "資産運用"],
    },
    {
        "title_template": "10年間S&P500に積み立てた人が経験した「3回の恐怖」と、それでも続けた理由",
        "theme": "2008年リーマンショック、2020年コロナショック、2022年金利急騰という3回の暴落を長期積立で乗り越えた体験談。各局面での具体的な下落率と回復期間、そして「売りたい衝動」をどう抑えたかを実体験的な語りで解説する。",
        "tags": ["資産運用", "NISA"],
    },
    {
        "title_template": "「この株、なぜ上がったのか分からない」を卒業する3つの習慣",
        "theme": "株価の動きを後追いで理解するだけでなく、事前に「どのような条件が揃えば株価が動くか」を予測できるようになるための3つの習慣（①決算前後の過去パターン研究 ②セクターローテーション把握 ③マクロ指標の月次確認）を具体的に解説する。",
        "tags": ["株式投資", "投資"],
    },
]

MEMBERSHIP_URL = "https://note.com/kawasewatson0106/membership"

POSTED_LOG = BASE_DIR / "data" / "evergreen_posted.json"


def load_posted() -> list[str]:
    try:
        return json.loads(POSTED_LOG.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_posted(titles: list[str]) -> None:
    POSTED_LOG.parent.mkdir(exist_ok=True)
    POSTED_LOG.write_text(json.dumps(titles, ensure_ascii=False, indent=2), encoding="utf-8")


def run_gemini(prompt: str) -> str:
    """Gemini APIで本文生成"""
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.85, max_output_tokens=4096),
        )
        return response.text.strip()
    except Exception as e:
        print(f"  [WARN] Gemini失敗: {e}")
        return ""


def run_claude(prompt: str) -> str:
    """Claude CLIで本文生成（stdin=DEVNULL・cwd=/tmp必須）"""
    import shutil, time as _time
    claude_path = shutil.which("claude") or "/opt/homebrew/bin/claude"
    if not os.path.exists(claude_path):
        return ""
    env = {k: v for k, v in os.environ.items()
           if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "/usr/bin:/bin")
    for attempt in range(1, 3):
        if attempt > 1:
            _time.sleep(30)
        proc = None
        try:
            proc = subprocess.Popen(
                [claude_path, "-p", prompt, "--output-format", "text",
                 "--allowedTools", "none", "--dangerously-skip-permissions"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True, env=env, cwd="/tmp",
            )
            stdout, stderr = proc.communicate(timeout=300)
            if proc.returncode == 0 and stdout.strip():
                return stdout.strip()
            print(f"  [WARN] Claude CLI attempt={attempt} rc={proc.returncode}: {(stderr or stdout)[:200]}")
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill(); proc.wait()
        except Exception as e:
            print(f"  [WARN] Claude CLI 例外: {e}")
        finally:
            if proc and proc.poll() is None:
                proc.kill()
    return ""


def pick_theme() -> dict:
    """未投稿のテーマからランダムに1つ選ぶ"""
    posted = load_posted()
    unused = [t for t in EVERGREEN_THEMES if t["title_template"] not in posted]
    if not unused:
        # 全部投稿済みなら最初からリセット
        print("  全テーマ消化済み → リセットして最初から")
        save_posted([])
        unused = EVERGREEN_THEMES[:]
    return random.choice(unused)


def generate_article(theme: dict) -> str:
    """保存版記事を生成"""
    today = datetime.datetime.now(JST).strftime("%Y年%m月%d日")
    prompt = f"""投資ニュースメディア「TATSUJIN TRADE」のnote記事を執筆してください。

【テーマ】
{theme["theme"]}

【タイトル】
{theme["title_template"]}

【執筆ルール】
- 目標文字数：2500〜3500字
- 読者：20〜30代の個人投資家（ある程度投資経験あり、専門家ではない）
- 文体：ブロガー口調（です・ます体）、断定的に書く
- スマホ読者を想定：1段落150〜250字、必ず空行を入れる
- 重要な数字・結論は**太字**で強調
- 具体例・実例を必ず入れる（数値・銘柄名は実在のものを使用可）
- 「正直に言うと」「私の場合は」など一人称の視点を混ぜる
- 冒頭：事実・問い・結論のいずれかで即始める（前置き・謙遜禁止）

【構成（必ずこの順で）】
1. 冒頭フック（2〜3段落）：読者を引き込む問いや事実で始める
2. ## [問題の本質] ← H2見出し（内容に応じて自分で考える）
3. ## [具体的な解説・手法] ← H2見出し（2〜3個）
4. ## 実際にやってみること ← H2見出し（具体的なアクション）
5. まとめ（2〜3行）

【禁止事項】
- 「---」区切り線
- 絵文字
- 「まとめ」「はじめに」「おわりに」見出し
- 有料マガジンへの誘導文（後で別途追加するため不要）
- 架空の数値を実績として書く

記事本文のみ出力してください（前置き・コメント不要）。"""

    print("  記事生成中（Gemini）...")
    body = run_gemini(prompt)
    if not body or len(body) < 1000:
        print("  Gemini失敗 → Claude CLIにフォールバック")
        body = run_claude(prompt)
    return body


def build_final_article(theme: dict, body: str) -> str:
    """中盤CTA + 末尾メンバーシップCTAを追加"""
    # 中盤CTA: 最初のH2見出し（##）の直後に挿入
    mid_cta = (
        "\n\n"
        "> **この記事の内容をもっと深掘りした「私自身の実際の売買判断」は"
        f"[メンバーシップ]({MEMBERSHIP_URL})で毎週公開しています。"
        "最初の1ヶ月は無料です。**\n\n"
    )

    h2_positions = [m.start() for m in re.finditer(r'\n## ', body)]
    if len(h2_positions) >= 2:
        # 2番目のH2の前に挿入（最初のセクションを読み終えたタイミング）
        insert_pos = h2_positions[1]
        body = body[:insert_pos] + mid_cta + body[insert_pos:]

    # 末尾CTA
    end_cta = (
        "\n\n"
        "## 毎週の売買判断を公開中\n\n"
        "このnoteでは投資の考え方や手法を解説していますが、"
        "**実際に私がどの銘柄をいつ買って・いつ売ったか**はメンバーシップで毎週公開しています。\n\n"
        "- 今週注目している銘柄と根拠\n"
        "- エントリーのタイミングの考え方（実戦ベース）\n"
        "- 「これは見送り」と判断した銘柄とその理由\n\n"
        "**最初の1ヶ月は無料**です。気に入らなければすぐ退会できます。\n\n"
        f"{MEMBERSHIP_URL}\n"
    )
    return body + end_cta


def generate_x_post(title: str, body: str) -> str:
    """X告知ポストを生成"""
    prompt = f"""投資ブログのnote記事をXでシェアするための告知ポストを作成してください。

【記事タイトル】
{title}

【記事の要点（先頭400字）】
{body[:400]}

【形式】
- 140字以内（URLは後で追加するので不要）
- 1行目：記事の最も価値ある気づきを1文で凝縮（フック）
- 空行
- ・ベネフィット1
- ・ベネフィット2
- ・ベネフィット3
- ハッシュタグ禁止
- 「ぜひ読んでください」など弱い誘導禁止

本文のみ出力（前置き不要）:"""

    post = run_gemini(prompt)
    if not post or len(post) < 20:
        # フォールバック
        post = f"{title}について書きました。\n\n・知らないと損する投資判断の基準\n・実際の売買に使える考え方\n・プロとの情報格差を埋めるポイント"
    return post


def generate_thumbnail_gemini(title: str, article_text: str) -> str | None:
    """Gemini Imagenでサムネイルを生成（deep_research.generate_thumbnail と同じ品質）"""
    try:
        import hashlib
        # タイトルベースのユニークなファイル名（同日に複数記事でも衝突しない）
        slug = hashlib.md5(title.encode()).hexdigest()[:8]
        suffix = f"_evergreen_{slug}"

        sys.path.insert(0, str(Path(__file__).parent))
        import deep_research
        path = deep_research.generate_thumbnail(title, article_text, suffix=suffix)
        if path:
            print(f"  サムネイル生成（Gemini Imagen）: {path}")
            return path
    except Exception as e:
        print(f"  [WARN] Gemini Imagenサムネイル失敗: {e}")

    # フォールバック: deep_research.get_random_cover_image()
    try:
        import deep_research
        path = deep_research.get_random_cover_image()
        if path:
            print(f"  サムネイル: ランダム画像フォールバック ({path})")
            return path
    except Exception:
        pass

    # 最終フォールバック: Pillowで生成
    try:
        from PIL import Image, ImageDraw, ImageFont
        import textwrap, hashlib

        img = Image.new("RGB", (1920, 1006), color="#0d1117")
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 1920, 10], fill="#e94560")
        draw.rectangle([0, 996, 1920, 1006], fill="#e94560")
        draw.rectangle([80, 50, 310, 115], fill="#e94560")
        try:
            badge_font = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc", 36)
            title_font = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc", 72)
            sub_font   = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc", 40)
        except Exception:
            badge_font = title_font = sub_font = ImageFont.load_default()
        draw.text((90, 65), "保 存 版", fill="white", font=badge_font)
        clean_title = re.sub(r"【保存版】", "", title).strip()
        lines = textwrap.wrap(clean_title, width=18)
        y = 200
        for line in lines[:4]:
            draw.text((80, y), line, fill="white", font=title_font)
            y += 90
        draw.text((80, 920), "TATSUJIN TRADE", fill="#e94560", font=sub_font)

        slug = hashlib.md5(title.encode()).hexdigest()[:8]
        out_dir = BASE_DIR / "output" / "images"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / f"evergreen_{slug}.png")
        img.save(out_path)
        print(f"  サムネイル生成（Pillow）: {out_path}")
        return out_path
    except Exception as e:
        print(f"  [WARN] サムネイル生成失敗: {e}")
        return None


def post_to_note(title: str, body: str, tags: list[str], cover_path: str | None) -> str:
    """note.comに下書き保存して URLを返す"""
    import post_to_note as ptr

    article_data = {
        "title": title,
        "article": body,
        "tags": tags + ["投資", "資産運用"],
        "image_paths": [],
        "cover_path": cover_path,
    }

    # 一時ファイルに保存してpost_to_note.mainを呼ぶ
    tmp_path = str(BASE_DIR / "output" / "evergreen_tmp.json")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(article_data, f, ensure_ascii=False, indent=2)

    result = ptr.main(article_file=tmp_path)
    return result.get("url", "")


def main():
    now = datetime.datetime.now(JST)
    print(f"=== 保存版記事パイプライン 開始 {now.strftime('%Y-%m-%d %H:%M JST')} ===")

    # テーマ選択
    theme = pick_theme()
    print(f"  テーマ: {theme['title_template']}")

    # 記事生成
    body = generate_article(theme)
    if not body or len(body) < 500:
        print("❌ 記事生成失敗")
        sys.exit(1)
    print(f"  生成完了: {len(body)}文字")

    # CTA追加
    final_body = build_final_article(theme, body)

    # ── 公開前QAチェック & 自動修正 ──
    print("  公開前QAチェック中...")
    sys.path.insert(0, str(Path(__file__).parent))
    from pre_publish_check import check_and_auto_fix
    qa_ok, final_body = check_and_auto_fix(theme["title_template"], final_body)
    if not qa_ok:
        print("❌ QAチェック失敗 → 記事を再生成します")
        body = generate_article(theme)
        if not body or len(body) < 500:
            print("❌ 再生成も失敗")
            sys.exit(1)
        final_body = build_final_article(theme, body)
        qa_ok, final_body = check_and_auto_fix(theme["title_template"], final_body)
        if not qa_ok:
            print("⚠️ 2回目もQA失敗 → 手動確認が必要です。下書き保存は続行します")

    # X告知ポスト生成
    print("  X告知ポスト生成中...")
    x_post = generate_x_post(theme["title_template"], final_body)

    # サムネイル生成（Gemini Imagen → ランダム → Pillow の優先順）
    print("  サムネイル生成中...")
    cover_path = generate_thumbnail_gemini(theme["title_template"], final_body)

    # note投稿
    print("  note下書き保存中...")
    try:
        url = post_to_note(
            title=theme["title_template"],
            body=final_body,
            tags=theme.get("tags", []),
            cover_path=cover_path,
        )
        print(f"  ✅ 下書き保存完了: {url}")
    except Exception as e:
        print(f"  ❌ note投稿失敗: {e}")
        sys.exit(1)

    # 投稿済みとして記録
    posted = load_posted()
    posted.append(theme["title_template"])
    save_posted(posted)

    # PDCAに記録
    try:
        import pdca_tracker
        note_key_m = re.search(r"/n/([a-zA-Z0-9]+)$", url)
        if note_key_m:
            pdca_tracker.record_posted_article(
                note_key=note_key_m.group(1),
                title=theme["title_template"],
                source_news=[],
                is_paid=False,
                price=0,
            )
    except Exception as e:
        print(f"  [WARN] PDCA登録失敗: {e}")

    # X告知ポストを出力
    print("\n" + "─"*50)
    print("📢 X告知ポスト（コピペ用）:")
    print("─"*50)
    print(x_post)
    print(f"\n全文はこちら→ {url}")
    print("─"*50)

    print(f"\n✅ 保存版記事投稿完了: {url}")
    return url


if __name__ == "__main__":
    main()
