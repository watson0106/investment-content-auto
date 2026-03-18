"""
⑥ note.com へ自動投稿
Selenium でログインし、画像をAPIでアップロード後、
エディタDOMを直接操作してタイトル・本文（画像URL埋め込み済み）を下書き保存する
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

NOTE_EMAIL    = os.environ["NOTE_EMAIL"]
NOTE_PASSWORD = os.environ["NOTE_PASSWORD"]

NOTE_TAGS = ["投資", "米国株", "日本株", "投資情報", "マーケット", "経済", "株式投資", "AI分析"]

_IS_CI = bool(os.environ.get("GITHUB_ACTIONS"))


def build_driver(headless: bool = True):
    if _IS_CI:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,900")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        if headless:
            options.add_argument("--headless=new")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        from selenium_stealth import stealth
        stealth(driver, languages=["ja-JP", "ja"], vendor="Google Inc.",
                platform="Win32", webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine", fix_hairline=True)
        return driver
    else:
        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,900")
        return uc.Chrome(options=options, headless=headless)


def login(driver, wait: WebDriverWait):
    print("  note にログイン中...")
    driver.get("https://note.com/login")
    time.sleep(3)
    driver.set_script_timeout(15)
    result = driver.execute_async_script(f"""
        var done = arguments[arguments.length - 1];
        fetch('/api/v1/sessions/sign_in', {{
            method: 'POST',
            credentials: 'same-origin',
            headers: {{
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'x-requested-with': 'XMLHttpRequest'
            }},
            body: JSON.stringify({{
                login: {json.dumps(NOTE_EMAIL)},
                password: {json.dumps(NOTE_PASSWORD)},
                redirect_path: ''
            }})
        }})
        .then(function(r) {{
            return r.text().then(function(t) {{ done({{status: r.status, text: t}}); }});
        }})
        .catch(function(e) {{ done({{error: e.toString()}}); }});
    """)

    if result and result.get("status") == 201:
        print("  ログイン成功（API）")
    else:
        print(f"  API login failed (status={result.get('status') if result else 'None'}), フォームで試みる...")
        email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
        email_field.clear()
        email_field.send_keys(NOTE_EMAIL)
        pw_field = driver.find_element(By.ID, "password")
        pw_field.clear()
        pw_field.send_keys(NOTE_PASSWORD)
        pw_field.send_keys(Keys.RETURN)
        for _ in range(10):
            time.sleep(1)
            if "login" not in driver.current_url:
                break
        if "note.com" in driver.current_url and "login" not in driver.current_url:
            print("  ログイン成功（フォーム）")
        else:
            raise Exception("ログイン失敗。メール・パスワードを確認してください")


def paste_image_from_clipboard(driver, editor_el, image_path: str) -> bool:
    """osascriptでクリップボードに画像をセットしてエディタにペースト"""
    try:
        abs_path = os.path.abspath(image_path)
        subprocess.run(
            ["osascript", "-e", f'set the clipboard to POSIX file "{abs_path}"'],
            check=True
        )
        time.sleep(0.8)
        editor_el.send_keys(Keys.COMMAND + "v")
        time.sleep(4)  # アップロード完了を待つ
        return True
    except Exception as e:
        print(f"  [WARN] 画像ペースト失敗: {e}")
        return False


def set_react_textarea(driver, element, value: str):
    """React controlled textareaに値をセット"""
    driver.execute_script("""
        var el = arguments[0];
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value').set;
        setter.call(el, arguments[1]);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    """, element, value)


def clean_inline_markdown(text: str) -> str:
    """**bold** と *italic* のマークアップを除去"""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\*(.+?)\*', r'\1', text, flags=re.DOTALL)
    return text


def insert_section_with_headings(driver, section_text: str):
    """セクションテキストを挿入（##見出し行はh2書式を適用）"""
    lines = section_text.split('\n')
    batch: list[str] = []

    def flush_batch():
        if not batch:
            return
        driver.execute_script(
            "document.execCommand('insertText', false, arguments[0])",
            '\n'.join(batch) + '\n'
        )
        batch.clear()

    for line in lines:
        m = re.match(r'^#{1,3}\s+(.*)', line)
        if m:
            flush_batch()
            heading_text = clean_inline_markdown(m.group(1).strip())
            # 見出しテキストを挿入 → h2書式を適用 → 改行して通常テキストに戻す
            driver.execute_script(
                "document.execCommand('insertText', false, arguments[0])", heading_text
            )
            time.sleep(0.1)
            driver.execute_script("document.execCommand('formatBlock', false, 'h2')")
            time.sleep(0.1)
            driver.execute_script("document.execCommand('insertText', false, '\\n')")
            driver.execute_script("document.execCommand('formatBlock', false, 'p')")
            time.sleep(0.1)
        else:
            batch.append(clean_inline_markdown(line))

    flush_batch()


def set_editor_content(driver, element, text: str):
    """ProseMirrorエディタにテキストをセット"""
    element.click()
    time.sleep(0.5)
    driver.execute_script("document.execCommand('selectAll', false, null)")
    driver.execute_script("document.execCommand('insertText', false, arguments[0])", text)


def post_article(title: str, body: str, image_paths: list[str], tags: list[str], headless: bool = True, cover_path: str | None = None) -> str:
    """note に記事を下書き保存してURLを返す"""
    driver = build_driver(headless=headless)
    wait   = WebDriverWait(driver, 30)

    try:
        login(driver, wait)

        # 新規記事エディタを開く
        print("  エディタを開いています...")
        driver.get("https://note.com/notes/new")
        time.sleep(10)

        current = driver.current_url
        print(f"  エディタURL: {current}")
        m = re.search(r"/notes/([a-zA-Z0-9]+)/edit", current)
        if not m:
            raise Exception(f"エディタにリダイレクトされませんでした: {current}")
        note_key = m.group(1)

        # タイトルを入力
        print(f"  タイトル入力中...")
        title_el = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'textarea[placeholder="記事タイトル"]')
        ))
        title_el.click()
        set_react_textarea(driver, title_el, title)
        time.sleep(1)

        # カバー画像（アイキャッチ）を設定
        if not cover_path:
            cover_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "cover_image.png"))
        if cover_path and os.path.exists(cover_path):
            print("  カバー画像を設定中...")
            try:
                # アイキャッチ画像アップロードボタンを探してクリック
                eyecatch_btn = driver.find_elements(By.XPATH,
                    "//*[contains(@class,'eyecatch') or contains(text(),'アイキャッチ') or contains(@aria-label,'アイキャッチ')]"
                )
                if not eyecatch_btn:
                    # file inputを直接探す
                    file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                    if file_inputs:
                        file_inputs[0].send_keys(cover_path)
                        time.sleep(3)
                        # トリミングダイアログが出た場合は確定ボタンを押す
                        try:
                            confirm = driver.find_element(By.XPATH, "//button[contains(.,'決定') or contains(.,'完了') or contains(.,'OK')]")
                            confirm.click()
                            time.sleep(2)
                        except Exception:
                            pass
                        print("  カバー画像 設定完了")
                else:
                    eyecatch_btn[0].click()
                    time.sleep(2)
                    file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                    if file_inputs:
                        file_inputs[-1].send_keys(cover_path)
                        time.sleep(3)
                        try:
                            confirm = driver.find_element(By.XPATH, "//button[contains(.,'決定') or contains(.,'完了') or contains(.,'OK')]")
                            confirm.click()
                            time.sleep(2)
                        except Exception:
                            pass
                        print("  カバー画像 設定完了")
            except Exception as e:
                print(f"  [WARN] カバー画像設定失敗: {e}")

        # __IMAGE_n__ プレースホルダーで本文を分割して順番に挿入
        body_text = body[:50000]
        parts = re.split(r'(__IMAGE_\d+__)', body_text)

        print(f"  本文入力中（{len(body_text)} 文字）...")
        editor_el = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".ProseMirror")
        ))
        editor_el.click()
        time.sleep(0.5)

        img_count = 0
        for part in parts:
            m2 = re.match(r'__IMAGE_(\d+)__', part.strip())
            if m2:
                idx = int(m2.group(1))
                if idx < len(image_paths) and image_paths[idx]:
                    img_path = image_paths[idx]
                    print(f"  [{img_count+1}/{len(image_paths)}] 画像をペースト中: {os.path.basename(img_path)}")
                    driver.execute_script("document.execCommand('insertText', false, '\\n')")
                    time.sleep(0.3)
                    editor_el = driver.find_element(By.CSS_SELECTOR, ".ProseMirror")
                    ok = paste_image_from_clipboard(driver, editor_el, img_path)
                    if ok:
                        editor_el = driver.find_element(By.CSS_SELECTOR, ".ProseMirror")
                        editor_el.send_keys(Keys.RETURN)
                        time.sleep(0.3)
                        print(f"    ✓ 画像{img_count+1} 挿入完了")
                    img_count += 1
            elif part.strip():
                insert_section_with_headings(driver, part)
                time.sleep(0.3)

        time.sleep(2)

        # 下書き保存
        print("  下書き保存中...")
        try:
            draft_btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(., '下書き保存')]")
            ))
            draft_btn.click()
            time.sleep(3)
            print("  「下書き保存」クリック完了")
        except Exception:
            print("  自動保存待ち（5秒）...")
            time.sleep(5)

        url = f"https://note.com/kawasewatson0106/n/{note_key}"
        print(f"  下書き保存完了: {url}")
        return url

    finally:
        driver.quit()


def main():
    print("=== ⑥ note.com 自動投稿 ===")

    with open("output/final.json", encoding="utf-8") as f:
        data = json.load(f)

    title       = data["title"]
    body        = data["article"]
    image_paths = data.get("image_paths", [])
    cover_path  = data.get("cover_path")

    print(f"  タイトル: {title}")
    print(f"  本文: {len(body)} 文字")
    print(f"  本文画像: {len(image_paths)} 枚")
    print(f"  カバー画像: {cover_path or '固定'}")

    headless = os.environ.get("HEADLESS", "true").lower() == "true"
    url = post_article(title, body, image_paths, NOTE_TAGS, headless=headless, cover_path=cover_path)

    result = {
        "url":   url,
        "title": title,
        "status": "success" if url else "failed",
    }

    out_path = "output/posted.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'✅ 下書き保存成功: ' + url if url else '❌ 保存失敗'}")
    return result


if __name__ == "__main__":
    main()
