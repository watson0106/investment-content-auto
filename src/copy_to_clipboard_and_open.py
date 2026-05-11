"""
post_now.md の本文をクリップボードに置き、note の新規記事エディタを開く。

使い方:
  python copy_to_clipboard_and_open.py

これを実行すると:
  1. 既に開いているChromeで note.com/notes/new が開く
  2. 本文（タイトル＋本体＋ハッシュタグ）がクリップボードに入る
  3. ユーザーはエディタにフォーカスして Ctrl+V → 公開ボタン

数十秒で投稿完了する。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "output" / "post_now.md"


def parse(md_text: str) -> dict:
    """post_now.md からタイトル・本文・ハッシュタグを抜き出す"""
    lines = md_text.split("\n")
    # タイトル: 「# タイトル」セクションの直後の最初の非空行
    title = ""
    body_lines = []
    hashtags = ""
    mode = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# タイトル"):
            mode = "title"
            continue
        if stripped.startswith("# 本文"):
            mode = "body"
            continue
        if stripped.startswith("# ハッシュタグ"):
            mode = "hashtag"
            continue
        if stripped.startswith("---") and mode in ("title", "body"):
            # セクション区切り。タイトル選択肢を1つに絞る
            if mode == "title" and title:
                mode = None
            continue
        if mode == "title" and not title and stripped and not stripped.startswith("#"):
            # 最初の候補を採用
            if stripped.startswith("- "):
                title = stripped[2:].strip()
            else:
                title = stripped
        elif mode == "body":
            body_lines.append(line)
        elif mode == "hashtag":
            if stripped.startswith("#"):
                hashtags += " " + stripped
    body = "\n".join(body_lines).strip()
    hashtags = hashtags.strip()
    return {"title": title, "body": body, "hashtags": hashtags}


def set_clipboard(text: str):
    """Windowsクリップボードにテキストをセット"""
    # PowerShell経由でセット（pyperclip非依存）
    encoded = text.replace("'", "''")
    cmd = f"$t = @'\n{text}\n'@\nSet-Clipboard -Value $t"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    return result.returncode == 0


def open_url(url: str):
    """既定のブラウザでURLを開く"""
    subprocess.run(["cmd.exe", "/c", "start", "", url], shell=False)


def main():
    if not SOURCE.exists():
        print(f"見つかりません: {SOURCE}")
        sys.exit(1)
    with open(SOURCE, encoding="utf-8") as f:
        md = f.read()
    parsed = parse(md)

    # クリップボードには「タイトル」と「本文」を別タイミングで貼れるよう
    # 1段階目: タイトルをセット → ユーザーがタイトル欄にCtrl+V
    # 2段階目: 本文をセット → ユーザーが本文欄にCtrl+V
    # まず本文だけクリップボードに置く（タイトルは画面で見ながら手入力でも10秒）
    full_body = parsed["body"]
    if parsed["hashtags"]:
        full_body += "\n\n" + parsed["hashtags"]

    print("=" * 60)
    print("=== クリップボードに本文をセット ===")
    print("=" * 60)
    ok = set_clipboard(full_body)
    if ok:
        print(f"  [OK] 本文（{len(full_body)}字）をクリップボードに入れました")
    else:
        print("  [WARN] クリップボードセット失敗")

    print()
    print("=== noteの新規記事ページを開きます ===")
    open_url("https://note.com/notes/new")
    print("  → ブラウザで note エディタが開きます")

    print()
    print("=" * 60)
    print("【あなたがやること（合計1分）】")
    print("=" * 60)
    print()
    print("1. 開いた note エディタで「タイトル」欄をクリック")
    print(f"   → 以下をコピペで入力:")
    print()
    print(f"   ┌─ タイトル ──────────────────")
    print(f"   │ {parsed['title']}")
    print(f"   └─────────────────")
    print()
    print("2. 本文エリアをクリック")
    print("3. Ctrl+V で貼り付け（本文＋ハッシュタグが入ります）")
    print("4. 右上の「公開」ボタン → 「公開設定」→ 「投稿する」")
    print()
    print("これで完了です。")


if __name__ == "__main__":
    main()
