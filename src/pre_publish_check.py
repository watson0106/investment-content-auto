"""
pre_publish_check.py
note投稿前に記事品質を自動チェック・自動修正する。

返り値:
  {"ok": True, "article": 修正後本文}  → 投稿OK
  {"ok": False, "errors": [...]}        → 重大問題あり、要再生成
"""
from __future__ import annotations

import re
import subprocess
import os


# ── チェック定義 ─────────────────────────────────────────────────

BANNED_PHRASES = [
    "ぜひ最後まで読んでください",
    "ぜひ最後まで",
    "最後までお読みください",
    "ちょっと待ってください",
    "ちょっと待ってほしい",
    "少し立ち止まって",
    "実はお伝えしたいことが",
    "今回は特別に",
]

WEAK_HOOKS = [
    "最高ですよね",
    "最高ですね",
    "いかがでしょうか",
    "〜ではないでしょうか",
    "皆さんは",
    "あなたはどう思いますか",
]

AI_PHRASES = [
    "いかがでしたか",
    "まとめると以下",
    "解説しました",
]

REPEAT_PHRASES = [
    "私の場合は",
    "正直に言うと",
    "実は",
]


def check_and_fix(title: str, article: str) -> dict:
    """
    記事をチェックして自動修正できるものは修正する。
    修正不能な重大問題がある場合は ok=False を返す。
    """
    errors = []
    warnings = []
    body = article

    # ── 自動修正 ─────────────────────────────────────────────────

    # 1. 冒頭のタイトル重複を削除
    first_line = body.strip().split("\n")[0].strip()
    if first_line == title or first_line == title.strip():
        body = body.strip()[len(first_line):].lstrip("\n").strip()
        print("  [FIX] 冒頭のタイトル重複を削除しました")

    # 2. 「ぜひ最後まで読んでください」等を削除
    for phrase in BANNED_PHRASES:
        if phrase in body:
            # 含む文全体を削除
            body = re.sub(r"[^。\n]*" + re.escape(phrase) + r"[^。\n]*。?", "", body)
            body = re.sub(r"\n{3,}", "\n\n", body)
            print(f"  [FIX] 禁止フレーズ「{phrase}」を削除しました")

    # 3. 「解説します」→「解説する」（AI感を下げる）
    body = body.replace("解説します", "解説する")
    body = body.replace("説明します", "説明する")
    body = body.replace("紹介します", "紹介する")

    # ── 重大エラーチェック（修正不能） ────────────────────────────

    # 4. 文章が途中で切れているか（末尾が句点・感嘆符・「。」で終わっていない）
    last_meaningful = body.rstrip().rstrip("\n")
    # メンバーシップURL行以外の最後の実質的な行
    content_lines = [l for l in last_meaningful.split("\n") if l.strip() and "note.com" not in l and not l.startswith("#")]
    if content_lines:
        last_content = content_lines[-1].strip()
        # 途切れ判定：1文字で終わっている、または句点なしで終わっている短い行
        if len(last_content) < 10 and not last_content.endswith(("。", ".", "！", "!","？","?")):
            errors.append(f"記事が途中で切れている可能性: 末尾が「{last_content}」")

    # 5. タイトルと内容の乖離
    title_num_match = re.search(r"たった(\d+|一|1)つ", title)
    if title_num_match:
        body_nums = re.findall(r"(\d+)つの(理由|方法|ポイント|コツ)", body)
        for num, _ in body_nums:
            if int(num) > 1:
                warnings.append(f"タイトル「たった1つ」なのに本文に「{num}つの」が含まれている（タイトルと内容の乖離）")

    # 6. 弱いフックチェック
    first_200 = body[:200]
    for phrase in WEAK_HOOKS:
        if phrase in first_200:
            warnings.append(f"冒頭に弱いフック「{phrase}」が含まれている（結論か事実で始めるべき）")

    # 7. AIっぽいフレーズ
    for phrase in AI_PHRASES:
        if phrase in body:
            warnings.append(f"AI感のある表現「{phrase}」が含まれている")

    # 8. 同じフレーズの繰り返し
    for phrase in REPEAT_PHRASES:
        count = body.count(phrase)
        if count >= 4:
            warnings.append(f"「{phrase}」が{count}回繰り返されている（3回以下が望ましい）")

    # 9. 文字数チェック
    if len(body) < 1500:
        errors.append(f"文字数が少なすぎる: {len(body)}文字（最低2000文字必要）")

    # 10. H2見出しが存在するか
    h2s = re.findall(r'^## .+', body, re.MULTILINE)
    if len(h2s) < 2:
        errors.append(f"H2見出しが少なすぎる: {len(h2s)}個（最低2個必要）")

    # 11. メンバーシップURL・CTAが存在するか
    if "note.com/kawasewatson0106/membership" not in body:
        warnings.append("メンバーシップURLが含まれていない（CTAが機能しない）")

    # ── 結果出力 ─────────────────────────────────────────────────
    print(f"  [QA] エラー: {len(errors)}件 / 警告: {len(warnings)}件")
    for e in errors:
        print(f"  [QA ERROR] {e}")
    for w in warnings:
        print(f"  [QA WARN] {w}")

    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "article": body}
    return {"ok": True, "errors": [], "warnings": warnings, "article": body}


def fix_with_claude(title: str, article: str, errors: list[str]) -> str:
    """重大エラーをClaude CLIで修正する"""
    import shutil
    claude_path = shutil.which("claude")
    if not claude_path:
        return article

    error_desc = "\n".join(f"- {e}" for e in errors)
    prompt = f"""以下の投資記事に問題があります。指示通りに修正してください。

【タイトル】
{title}

【問題点】
{error_desc}

【修正指示】
- 記事が途中で切れている場合は、最後の段落から自然に続きを書いて完成させる
- タイトルと内容が乖離している場合は、タイトルに合うよう内容を調整する
- 修正後の記事全文を出力すること（前置き・コメント不要）
- 文体・構成・H2見出しは変えない

【現在の記事（最後の1000文字）】
...（前略）...
{article[-1000:]}

【記事全文を修正後に出力してください】
記事全文のみ出力（前置き・コメント不要）:"""

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    result = subprocess.run(
        [claude_path, "-p", prompt, "--output-format", "text",
         "--allowedTools", "none", "--dangerously-skip-permissions"],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=180, env=env,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return article


def check_and_auto_fix(title: str, article: str, max_retries: int = 2) -> tuple[bool, str]:
    """
    チェック → 自動修正 → 再チェック を最大max_retries回繰り返す。
    Returns: (ok: bool, fixed_article: str)
    """
    for attempt in range(max_retries + 1):
        result = check_and_fix(title, article)
        article = result["article"]  # 自動修正適用済み

        if result["ok"]:
            return True, article

        if attempt < max_retries and result["errors"]:
            print(f"  [QA] 重大エラーあり → Claude CLIで修正中（試行{attempt+1}/{max_retries}）...")
            article = fix_with_claude(title, article, result["errors"])
        else:
            print(f"  [QA] {max_retries}回試行後もエラー残存 → 手動確認が必要")
            return False, article

    return False, article


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) < 2:
        print("使用法: python3 pre_publish_check.py <article_json_path>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    title = data.get("title", "")
    article = data.get("article", "")

    print(f"=== 公開前QAチェック ===")
    print(f"タイトル: {title}")
    ok, fixed = check_and_auto_fix(title, article)

    if ok:
        print("✅ QAチェック通過")
        data["article"] = fixed
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"修正済みファイルを保存: {sys.argv[1]}")
    else:
        print("❌ QAチェック失敗 - 手動確認が必要")
        sys.exit(1)
