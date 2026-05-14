"""
専用 Chrome プロファイル経由で note に投稿する

なぜ専用プロファイルか:
- 通常 Chrome は既にユーザーが起動中でロック中
- 通常 Selenium (undetected_chromedriver) は note の anti-bot にブロックされる
- 専用プロファイルに1回だけ手動ログインしてもらえば、以降はそのプロファイルで
  Selenium を起動しても「ログイン済みのブラウザ」として扱われ note も受け入れる

使い方:
  ① 初回（ログインのみ）:
     python post_via_persistent_chrome.py --setup
     → ブラウザが開く。手動でnoteにログイン → ブラウザを閉じる

  ② 投稿 (post_now.md を投稿):
     python post_via_persistent_chrome.py --post output/post_now.md

  ③ ヘルパー API (他スクリプトから呼ぶ):
     from post_via_persistent_chrome import post_markdown
     url = post_markdown(title, body)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "src"))

PROFILE_DIR = ROOT / "chrome_profile_note"
PROFILE_DIR.mkdir(exist_ok=True)


def build_persistent_driver(headless: bool = False):
    """専用プロファイルで undetected_chromedriver を起動"""
    import undetected_chromedriver as uc

    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=ja-JP")
    options.add_argument("--window-size=1280,900")
    if headless:
        options.add_argument("--headless=new")

    return uc.Chrome(options=options, version_main=147)


def parse_md(md_path: Path) -> dict:
    """post_now.md から タイトル・本文・ハッシュタグを抽出"""
    text = md_path.read_text(encoding="utf-8")
    title = ""
    body_lines = []
    hashtags = ""
    mode = None
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("# タイトル"):
            mode = "title"; continue
        if s.startswith("# 本文"):
            mode = "body"; continue
        if s.startswith("# ハッシュタグ"):
            mode = "hashtag"; continue
        if s.startswith("---") and mode in ("title", "body"):
            if mode == "title" and title:
                mode = None
            continue
        if mode == "title" and not title and s and not s.startswith("#"):
            title = s[2:].strip() if s.startswith("- ") else s
        elif mode == "body":
            body_lines.append(line)
        elif mode == "hashtag":
            if s.startswith("#"):
                hashtags += " " + s
    return {
        "title": title,
        "body": "\n".join(body_lines).strip(),
        "hashtags": hashtags.strip(),
    }


def setup_login(auto_credentials: bool = False):
    """初回セットアップ: ブラウザを開いてログイン
    auto_credentials=True なら .env から認証情報を自動入力（reCAPTCHAだけ手動）"""
    print("=" * 60)
    print("初回セットアップ: Chrome を起動して note にログインします")
    print("=" * 60)

    driver = build_persistent_driver(headless=False)
    try:
        driver.get("https://note.com/login")
        time.sleep(5)

        if auto_credentials:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            try:
                email = os.environ.get("NOTE_EMAIL", "")
                pw = os.environ.get("NOTE_PASSWORD", "")
                if email and pw:
                    print("  認証情報を自動入力...")
                    email_field = driver.find_element(By.ID, "email")
                    driver.execute_script("""
                        var el = arguments[0];
                        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(el, arguments[1]);
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    """, email_field, email)
                    time.sleep(0.5)
                    pw_field = driver.find_element(By.ID, "password")
                    driver.execute_script("""
                        var el = arguments[0];
                        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(el, arguments[1]);
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    """, pw_field, pw)
                    time.sleep(0.5)
                    # ログインボタン押下
                    try:
                        btn = driver.find_element(
                            By.XPATH,
                            "//button[contains(.,'ログイン') and not(contains(.,'Google')) and not(contains(.,'Apple')) and not(contains(.,'X'))]"
                        )
                        driver.execute_script("arguments[0].click();", btn)
                    except Exception:
                        pw_field.send_keys(Keys.RETURN)
                    print("  認証情報入力済 → reCAPTCHA があれば手動で解いてください")
            except Exception as e:
                print(f"  自動入力失敗: {e}")

        print()
        print("=" * 60)
        print("ブラウザでログインを完了したら、自分のプロフィールページが見えるはず。")
        print("そこまで進んだら、Chrome ウィンドウを × で閉じてください。")
        print("=" * 60)

        # ブラウザが閉じられるまで待つ
        while True:
            try:
                _ = driver.current_url
                time.sleep(2)
            except Exception:
                print("\nブラウザが閉じられました。セットアップ完了。")
                break
    except KeyboardInterrupt:
        print("中断されました")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def post_markdown(title: str, body: str, tags: list[str] = None) -> str:
    """専用プロファイルで note に記事を投稿してURLを返す"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    if tags is None:
        tags = ["個別株投資", "日本株", "投資ニュース", "デイトレ", "投資戦略", "メンバーシップ", "兼業投資家"]

    print(f"\n[投稿] {title[:60]}")
    print(f"  本文: {len(body)} 字")

    driver = build_persistent_driver(headless=False)
    wait = WebDriverWait(driver, 30)

    try:
        # ログイン済みであることを確認
        driver.get("https://note.com/")
        time.sleep(4)
        page_text = driver.execute_script("return document.body.innerText.slice(0, 800);")
        if "会員登録" in page_text and "ログイン" in page_text:
            raise RuntimeError(
                "ログインしていません。先に `python post_via_persistent_chrome.py --setup` を実行してください"
            )
        print("  ログイン状態OK")

        # 新規記事ページへ
        driver.get("https://note.com/notes/new")
        time.sleep(6)

        # タイトル入力
        print("  タイトル入力中...")
        title_el = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "textarea[placeholder*='タイトル']"))
        )
        title_el.click()
        time.sleep(0.5)
        title_el.send_keys(title)
        time.sleep(1)

        # 本文入力
        print("  本文入力中...")
        body_el = driver.find_element(
            By.CSS_SELECTOR, "[contenteditable='true'], div[role='textbox']"
        )
        body_el.click()
        time.sleep(0.5)

        # クリップボード経由で貼り付け（大量テキストの高速入力）
        import subprocess
        clipboard_text = body
        if tags:
            clipboard_text += "\n\n" + " ".join(f"#{t}" for t in tags)
        try:
            ps_cmd = f"Set-Clipboard -Value @'\n{clipboard_text}\n'@"
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                check=True, capture_output=True,
            )
            time.sleep(0.5)
            body_el.send_keys(Keys.CONTROL + "v")
            time.sleep(3)
            print(f"  本文ペースト完了")
        except Exception as e:
            print(f"  クリップボード失敗、send_keys にフォールバック: {e}")
            for line in body.split("\n"):
                if line.strip():
                    body_el.send_keys(line)
                body_el.send_keys(Keys.ENTER)
                time.sleep(0.02)

        # 下書き保存 (Ctrl+S)
        print("  下書き保存...")
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(driver).key_down(Keys.CONTROL).send_keys("s").key_up(Keys.CONTROL).perform()
        time.sleep(5)

        # URL取得
        current = driver.current_url
        m = re.search(r"/n/([a-zA-Z0-9]+)", current)
        if m:
            url = f"https://note.com/kawasewatson0106/n/{m.group(1)}"
            print(f"  下書き保存OK: {url}")
        else:
            url = current
            print(f"  URL不明: {current}")

        print()
        print("=" * 60)
        print("下書き保存完了。ブラウザが開いたまま残ります。")
        print("公開ボタンを押すかどうか確認してから、ブラウザを閉じてください")
        print("=" * 60)
        # ユーザーに確認のため15秒待つ
        time.sleep(15)
        return url

    finally:
        try:
            driver.quit()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true", help="初回ログインセットアップ（手動）")
    parser.add_argument("--auto-setup", action="store_true", help="認証自動入力＋reCAPTCHAだけ手動")
    parser.add_argument("--post", type=str, help="post_now.md などのパス")
    args = parser.parse_args()

    if args.setup or args.auto_setup:
        setup_login(auto_credentials=args.auto_setup)
        return

    if args.post:
        md = parse_md(Path(args.post))
        if not md["title"]:
            print("タイトル抽出失敗"); sys.exit(1)
        url = post_markdown(
            title=md["title"],
            body=md["body"],
            tags=None,  # post_now.md 内のハッシュタグを使うので関数側のデフォルトを使う
        )
        print(f"\n結果URL: {url}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
