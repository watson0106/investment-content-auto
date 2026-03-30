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
    """セクションテキストを挿入（# → h1、## → h2 書式を適用）"""
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
        m = re.match(r'^(#{1,3})\s+(.*)', line)
        if m:
            flush_batch()
            level = len(m.group(1))
            heading_text = clean_inline_markdown(m.group(2).strip())
            tag = 'h1' if level == 1 else 'h2'
            driver.execute_script(
                "document.execCommand('insertText', false, arguments[0])", heading_text
            )
            time.sleep(0.1)
            driver.execute_script(f"document.execCommand('formatBlock', false, '{tag}')")
            time.sleep(0.1)
            driver.execute_script("document.execCommand('insertText', false, '\\n')")
            driver.execute_script("document.execCommand('formatBlock', false, 'p')")
            time.sleep(0.1)
        else:
            batch.append(clean_inline_markdown(line))

    flush_batch()


def insert_magazine_embed(driver, magazine_url: str):
    """有料マガジンURLを note.com の埋め込みブロックとして挿入"""
    try:
        editor_el = driver.find_element(By.CSS_SELECTOR, ".ProseMirror")
        editor_el.click()
        time.sleep(0.5)

        # カーソルを末尾に移動して空行を作る
        driver.execute_script("window.getSelection().collapseToEnd()")
        driver.execute_script("document.execCommand('insertText', false, '\\n')")
        time.sleep(0.8)

        # ＋ボタン（追加ブロックメニュー）を探す
        add_btn = None
        selectors = [
            "[class*='AddButton']",
            "[class*='add-button']",
            "[class*='addButton']",
            "button[aria-label*='追加']",
            "button[data-tooltip*='追加']",
            "[class*='insertButton']",
        ]
        for sel in selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                add_btn = els[-1]  # 末尾（最新行）のボタンを使う
                break

        if add_btn:
            driver.execute_script("arguments[0].scrollIntoView(true);", add_btn)
            driver.execute_script("arguments[0].click();", add_btn)
            time.sleep(1.0)

            # 埋め込みボタンを探してクリック
            embed_btn = None
            for xpath in [
                "//*[contains(text(),'埋め込み')]",
                "//*[contains(@aria-label,'埋め込み')]",
                "//*[contains(@title,'埋め込み')]",
            ]:
                els = driver.find_elements(By.XPATH, xpath)
                if els:
                    embed_btn = els[0]
                    break

            if embed_btn:
                driver.execute_script("arguments[0].click();", embed_btn)
                time.sleep(1.0)

                # URL入力欄を探して入力
                url_input = None
                for sel in ["input[type='url']", "input[placeholder*='URL']",
                            "input[placeholder*='url']", "input[placeholder*='https']"]:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    if els:
                        url_input = els[0]
                        break

                if url_input:
                    url_input.clear()
                    url_input.send_keys(magazine_url)
                    time.sleep(0.5)

                    # 「適用」ボタンをクリック
                    apply_btn = None
                    for xpath in [
                        "//button[contains(.,'適用')]",
                        "//button[contains(.,'OK')]",
                        "//button[contains(.,'確定')]",
                    ]:
                        els = driver.find_elements(By.XPATH, xpath)
                        if els:
                            apply_btn = els[0]
                            break

                    if apply_btn:
                        driver.execute_script("arguments[0].click();", apply_btn)
                        time.sleep(3)
                        print(f"  マガジン埋め込み完了: {magazine_url}")
                        return
                    else:
                        from selenium.webdriver.common.keys import Keys as K
                        url_input.send_keys(K.RETURN)
                        time.sleep(3)
                        print(f"  マガジン埋め込み（Enterで適用）: {magazine_url}")
                        return

        # フォールバック: URLをテキストとして直接ペースト（note.comが自動embed化する場合がある）
        print(f"  [WARN] ＋ボタン見つからず。URLをテキストとして挿入: {magazine_url}")
        driver.execute_script(
            "document.execCommand('insertText', false, arguments[0])", magazine_url + "\n"
        )
        time.sleep(2)

    except Exception as e:
        print(f"  [WARN] マガジン埋め込み失敗: {e}")
        try:
            driver.execute_script(
                "document.execCommand('insertText', false, arguments[0])", magazine_url + "\n"
            )
        except Exception:
            pass


def set_editor_content(driver, element, text: str):
    """ProseMirrorエディタにテキストをセット"""
    element.click()
    time.sleep(0.5)
    driver.execute_script("document.execCommand('selectAll', false, null)")
    driver.execute_script("document.execCommand('insertText', false, arguments[0])", text)


def post_article(title: str, body: str, image_paths: list[str], tags: list[str], headless: bool = True, cover_path: str | None = None, price: int = 0) -> str:
    """note に記事を保存してURLを返す。price>0の場合は有料公開する"""
    driver = build_driver(headless=headless)
    wait   = WebDriverWait(driver, 30)

    try:
        login(driver, wait)

        # 新規記事エディタを開く
        print("  エディタを開いています...")
        driver.get("https://note.com/notes/new")

        # 方法1: URLが /notes/XXXX/edit に変わるまで最大30秒待つ
        note_key = None
        for i in range(30):
            time.sleep(1)
            current = driver.current_url
            m = re.search(r"/notes/([a-zA-Z0-9]+)/edit", current)
            if m:
                note_key = m.group(1)
                break

        # 方法2: URLが変わらない場合、editor.note.com から API 経由で作成
        if not note_key:
            print(f"  URL未遷移 ({driver.current_url})、editor API で note 作成を試みる...")
            # editor.note.com ドメインにいる状態で API を叩く
            driver.set_script_timeout(20)
            create_result = driver.execute_async_script("""
                var done = arguments[arguments.length - 1];
                // CSRF トークンを meta から取得
                var csrfMeta = document.querySelector('meta[name="csrf-token"]');
                var csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
                fetch('/api/v1/text_notes', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'x-requested-with': 'XMLHttpRequest',
                        'x-csrf-token': csrfToken
                    },
                    body: JSON.stringify({status: 'draft'})
                })
                .then(function(r) {
                    return r.text().then(function(t) { done({status: r.status, text: t}); });
                })
                .catch(function(e) { done({error: e.toString()}); });
            """)
            if create_result and create_result.get("status") in (200, 201):
                try:
                    note_data = json.loads(create_result["text"])
                    note_key = (note_data.get("data", {}).get("key")
                                or note_data.get("key"))
                    if note_key:
                        print(f"  editor API 作成成功: {note_key}")
                        driver.get(f"https://editor.note.com/notes/{note_key}/edit/")
                        time.sleep(5)
                except Exception as e:
                    print(f"  [WARN] API レスポンス解析失敗: {e}")
            else:
                print(f"  editor API 失敗 (status={create_result.get('status') if create_result else 'None'}, text={str(create_result)[:200]})")

        # 方法3: note.com ドメインから API 経由で作成
        if not note_key:
            print("  note.com ドメインで API 作成を試みる...")
            driver.get("https://note.com/")
            time.sleep(2)
            driver.set_script_timeout(20)
            create_result2 = driver.execute_async_script("""
                var done = arguments[arguments.length - 1];
                fetch('/api/v1/text_notes', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'x-requested-with': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({status: 'draft'})
                })
                .then(function(r) {
                    return r.text().then(function(t) { done({status: r.status, text: t}); });
                })
                .catch(function(e) { done({error: e.toString()}); });
            """)
            if create_result2 and create_result2.get("status") in (200, 201):
                try:
                    note_data2 = json.loads(create_result2["text"])
                    note_key = (note_data2.get("data", {}).get("key")
                                or note_data2.get("key"))
                    if note_key:
                        print(f"  note.com API 作成成功: {note_key}")
                        driver.get(f"https://editor.note.com/notes/{note_key}/edit/")
                        time.sleep(5)
                except Exception as e:
                    print(f"  [WARN] レスポンス解析失敗: {e}")
            else:
                print(f"  note.com API 失敗 (status={create_result2.get('status') if create_result2 else 'None'}, text={str(create_result2)[:300]})")

        if not note_key:
            raise Exception(f"ノート作成に失敗しました: {driver.current_url}")

        print(f"  エディタURL: {driver.current_url}")

        # タイトルを入力
        print(f"  タイトル入力中...")
        title_el = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'textarea[placeholder="記事タイトル"]')
        ))
        driver.execute_script("arguments[0].scrollIntoView(true);", title_el)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", title_el)
        set_react_textarea(driver, title_el, title)
        time.sleep(1)

        # カバー画像（サムネイル）を設定
        if not cover_path:
            cover_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "cover_image.png"))
        if cover_path and os.path.exists(cover_path):
            abs_cover = os.path.abspath(cover_path)
            print(f"  カバー画像を設定中: {os.path.basename(abs_cover)}")
            try:
                # JS でhidden な file input を表示してから send_keys
                driver.execute_script("""
                    var inputs = document.querySelectorAll('input[type="file"]');
                    inputs.forEach(function(el) {
                        el.style.display = 'block';
                        el.style.visibility = 'visible';
                        el.style.opacity = '1';
                        el.style.width = '1px';
                        el.style.height = '1px';
                    });
                """)
                time.sleep(0.5)
                file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                if file_inputs:
                    file_inputs[0].send_keys(abs_cover)
                    time.sleep(5)  # アップロード完了待ち（5秒）
                    # トリミングダイアログが出た場合は確定ボタンを押す
                    try:
                        confirm = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(
                            (By.XPATH, "//button[contains(.,'決定') or contains(.,'完了') or contains(.,'保存') or contains(.,'OK')]")
                        ))
                        driver.execute_script("arguments[0].click();", confirm)
                        time.sleep(2)
                    except Exception:
                        pass
                    print("  カバー画像 設定完了")
                else:
                    print("  [WARN] file input 見つからず")
            except Exception as e:
                print(f"  [WARN] カバー画像設定失敗: {e}")

        MAGAZINE_URL = "https://note.com/kawasewatson0106/m/me3bdb7d529fc"

        # __IMAGE_n__, __MAGAZINE_EMBED__ プレースホルダーで本文を分割して順番に挿入
        body_text = body[:50000]
        parts = re.split(r'(__IMAGE_\d+__|__MAGAZINE_EMBED__)', body_text)

        print(f"  本文入力中（{len(body_text)} 文字）...")
        editor_el = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".ProseMirror")
        ))
        driver.execute_script("arguments[0].scrollIntoView(true);", editor_el)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", editor_el)
        time.sleep(0.5)

        img_count = 0
        for part in parts:
            stripped = part.strip()
            m2 = re.match(r'__IMAGE_(\d+)__', stripped)
            if m2:
                idx = int(m2.group(1))
                if idx < len(image_paths) and image_paths[idx]:
                    img_path = image_paths[idx]
                    print(f"  [{img_count+1}/{len(image_paths)}] 画像をペースト中: {os.path.basename(img_path)}")
                    editor_el = driver.find_element(By.CSS_SELECTOR, ".ProseMirror")
                    ok = paste_image_from_clipboard(driver, editor_el, img_path)
                    if ok:
                        editor_el = driver.find_element(By.CSS_SELECTOR, ".ProseMirror")
                        editor_el.send_keys(Keys.RETURN)
                        time.sleep(0.3)
                        print(f"    ✓ 画像{img_count+1} 挿入完了")
                    img_count += 1
            elif stripped == "__MAGAZINE_EMBED__":
                print("  マガジン埋め込みを挿入中...")
                insert_magazine_embed(driver, MAGAZINE_URL)
            elif stripped:
                insert_section_with_headings(driver, stripped)
                time.sleep(0.3)

        time.sleep(2)

        if price > 0:
            # 有料公開: note API で price を設定して公開
            print(f"  有料記事として公開中（¥{price}）...")
            driver.set_script_timeout(20)
            pub_result = driver.execute_async_script(f"""
                var done = arguments[arguments.length - 1];
                fetch('/api/v1/text_notes/{note_key}', {{
                    method: 'PUT',
                    credentials: 'include',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'x-requested-with': 'XMLHttpRequest'
                    }},
                    body: JSON.stringify({{
                        status: 'public',
                        price: {price},
                        hashtag_list: {json.dumps(tags)}
                    }})
                }})
                .then(function(r) {{
                    return r.text().then(function(t) {{ done({{status: r.status, text: t}}); }});
                }})
                .catch(function(e) {{ done({{error: e.toString()}}); }});
            """)
            if pub_result and pub_result.get("status") in (200, 201):
                print(f"  有料公開成功 (¥{price})")
            else:
                print(f"  [WARN] 有料公開API失敗 (status={pub_result.get('status') if pub_result else 'None'})。下書き保存にフォールバック")
                try:
                    draft_btn = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(., '下書き保存')]")
                    ))
                    driver.execute_script("arguments[0].click();", draft_btn)
                    time.sleep(3)
                except Exception:
                    time.sleep(5)
        else:
            # 無料記事: 下書き保存
            print("  下書き保存中...")
            try:
                draft_btn = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(., '下書き保存')]")
                ))
                driver.execute_script("arguments[0].scrollIntoView(true);", draft_btn)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", draft_btn)
                time.sleep(3)
                print("  「下書き保存」クリック完了")
            except Exception:
                print("  自動保存待ち（5秒）...")
                time.sleep(5)

        url = f"https://note.com/kawasewatson0106/n/{note_key}"
        print(f"  {'公開' if price > 0 else '下書き保存'}完了: {url}")
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
