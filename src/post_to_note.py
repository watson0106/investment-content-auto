"""
⑥ note.com へ自動投稿
Selenium でログインし、画像をAPIでアップロード後、
エディタDOMを直接操作してタイトル・本文（画像URL埋め込み済み）を下書き保存する
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

NOTE_EMAIL    = os.environ["NOTE_EMAIL"]
NOTE_PASSWORD = os.environ["NOTE_PASSWORD"]

# デフォルトタグ（固定5つ）。記事ごとのtopic_tagsが加わり計7つになる。
NOTE_TAGS_DEFAULT = ["投資", "株式投資", "資産運用", "米国株", "日本株"]

# 有料マガジンURL（埋め込みカードとして単独行に挿入するため、本文中の重複を除去する）
MAGAZINE_URL = "https://note.com/kawasewatson0106/m/me3bdb7d529fc"

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
        return uc.Chrome(options=options, headless=headless, version_main=146)


def login(driver, wait: WebDriverWait):
    print("  note にログイン中...")
    driver.get("https://note.com/login")
    time.sleep(3)
    driver.set_script_timeout(30)
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


def _copy_image_to_clipboard(abs_path: str) -> None:
    """OS に応じて画像ファイルをクリップボードにコピーする"""
    system = platform.system()
    if system == "Darwin":
        # macOS
        subprocess.run(
            ["osascript", "-e", f'set the clipboard to POSIX file "{abs_path}"'],
            check=True,
        )
    elif system == "Windows":
        # Windows: PowerShell で画像をクリップボードにコピー
        ps_script = (
            f'Add-Type -AssemblyName System.Windows.Forms;'
            f'[System.Windows.Forms.Clipboard]::SetImage('
            f'[System.Drawing.Image]::FromFile("{abs_path}"))'
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            check=True,
        )
    else:
        # Linux (GitHub Actions 等): xclip を使用
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-i", abs_path],
            check=True,
        )


def insert_image_to_editor(driver, image_path: str) -> bool:
    """
    画像をnoteのProseMirrorエディタに挿入する。
    方法: Base64 → File → drop/pasteイベントで ProseMirror のアップロードハンドラを起動
    挿入後にimgタグがDOMに実際に存在するか検証する。
    """
    import base64
    abs_path = os.path.abspath(image_path)
    if not os.path.exists(abs_path):
        print(f"    [FAIL] 画像ファイルが存在しない: {abs_path}")
        return False

    with open(abs_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    fname = os.path.basename(abs_path)
    mime = "image/png" if fname.endswith(".png") else "image/jpeg"

    # 挿入前のimg数を記録
    before_count = len(driver.find_elements(By.CSS_SELECTOR, ".ProseMirror img"))

    # paste イベントでProseMirrorのアップロードハンドラを起動
    driver.set_script_timeout(30)
    try:
        paste_result = driver.execute_async_script("""
        var done = arguments[arguments.length - 1];
        var b64 = arguments[0];
        var fname = arguments[1];
        var mime = arguments[2];

        var byteChars = atob(b64);
        var byteArr = new Uint8Array(byteChars.length);
        for (var i = 0; i < byteChars.length; i++) {
            byteArr[i] = byteChars.charCodeAt(i);
        }
        var blob = new Blob([byteArr], {type: mime});
        var file = new File([blob], fname, {type: mime});

        var editor = document.querySelector('.ProseMirror');
        if (!editor) { done('no_editor'); return; }
        editor.focus();

        var dt = new DataTransfer();
        dt.items.add(file);

        var pasteEvt = new ClipboardEvent('paste', {
            bubbles: true,
            cancelable: true,
            clipboardData: dt
        });
        editor.dispatchEvent(pasteEvt);

        var attempts = 0;
        var beforeImgs = editor.querySelectorAll('img').length;
        var checkInterval = setInterval(function() {
            attempts++;
            var currentImgs = editor.querySelectorAll('img').length;
            if (currentImgs > beforeImgs) {
                clearInterval(checkInterval);
                done('paste_ok');
            } else if (attempts > 20) {
                clearInterval(checkInterval);
                done('paste_timeout');
            }
        }, 500);
    """, img_b64, fname, mime)

    except Exception as e:
        paste_result = f"exception: {e}"

    if paste_result == "paste_ok":
        time.sleep(1)
        return True

    # フォールバック: file input を探して直接送信
    print(f"    paste方式失敗({paste_result})、file input方式を試行...")
    try:
        # エディタ内の "+" ボタンまたは画像追加ボタンをクリック
        plus_btns = driver.find_elements(By.CSS_SELECTOR,
            "button[data-testid='add-block'], .ProseMirror + button, "
            "[class*='add'], [class*='plus'], [aria-label*='追加']"
        )
        for btn in plus_btns:
            try:
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(1)
                break
            except Exception:
                continue

        # file input を探してファイルパスを送信
        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file'][accept*='image']")
        if not file_inputs:
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")

        if file_inputs:
            file_inputs[-1].send_keys(abs_path)
            time.sleep(5)
            after_count = len(driver.find_elements(By.CSS_SELECTOR, ".ProseMirror img"))
            if after_count > before_count:
                return True
            print(f"    file input方式: img数変化なし ({before_count} → {after_count})")
        else:
            print(f"    file input が見つからない")
    except Exception as e:
        print(f"    file input方式失敗: {e}")

    print(f"    [FAIL] 全方式で画像挿入に失敗")
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


def insert_url_as_embed(driver, url: str):
    """URLをnoteの埋め込みカードとして挿入（ペーストイベント経由）"""
    # クリップボードAPIでURLをセットしてペーストイベントを発火
    driver.execute_script("""
        const url = arguments[0];
        const dt = new DataTransfer();
        dt.setData('text/plain', url);
        const ev = new ClipboardEvent('paste', {
            bubbles: true,
            cancelable: true,
            clipboardData: dt,
        });
        document.activeElement.dispatchEvent(ev);
    """, url)
    time.sleep(2.0)  # 埋め込みポップアップの出現を待つ
    # 「埋め込む」ボタンが出たらクリック
    try:
        from selenium.webdriver.common.by import By
        embed_btn = driver.find_element(
            By.XPATH,
            "//button[contains(text(),'埋め込む') or contains(@aria-label,'埋め込')]"
        )
        embed_btn.click()
        time.sleep(1.5)
        return
    except Exception:
        pass
    # フォールバック: プレーンテキストで挿入
    driver.execute_script(
        "document.execCommand('insertText', false, arguments[0])", url + '\n'
    )


def insert_section_with_headings(driver, section_text: str):
    """セクションテキストを挿入（## → h2、### → h3、URL単独行 → 埋め込み）"""
    # 3連続以上の改行を2連続に圧縮してスペース過多を防ぐ
    section_text = re.sub(r'\n{3,}', '\n\n', section_text)
    lines = section_text.split('\n')
    batch: list[str] = []
    skip_leading_blanks = False  # 見出し直後の空行をスキップするフラグ

    def flush_batch():
        # 末尾の空行を除去してスペースが大量に入るのを防ぐ
        while batch and not batch[-1].strip():
            batch.pop()
        if not batch:
            return
        text = '\n'.join(batch)
        # 連続空行（\n\n以上）を単一改行に圧縮してProseMirrorでの余分なスペースを防ぐ
        text = re.sub(r'\n{2,}', '\n', text)
        driver.execute_script(
            "document.execCommand('insertText', false, arguments[0])",
            text + '\n'
        )
        batch.clear()

    for line in lines:
        # ## または ### の見出し行
        m = re.match(r'^(#{2,3})\s+(.*)', line)
        if m:
            flush_batch()
            level = len(m.group(1))  # 2 → h2、3 → h3
            heading_tag = 'h2' if level == 2 else 'h3'
            heading_text = clean_inline_markdown(m.group(2).strip())
            # 見出しテキストを挿入 → 書式を適用 → 改行して通常テキストに戻す
            driver.execute_script(
                "document.execCommand('insertText', false, arguments[0])", heading_text
            )
            time.sleep(0.1)
            driver.execute_script(f"document.execCommand('formatBlock', false, '{heading_tag}')")
            time.sleep(0.1)
            driver.execute_script("document.execCommand('insertText', false, '\\n')")
            driver.execute_script("document.execCommand('formatBlock', false, 'p')")
            time.sleep(0.1)
            skip_leading_blanks = True  # 見出し直後の空行をスキップ
        # URL単独行 → 埋め込みカード
        elif re.match(r'^https?://\S+$', line.strip()):
            flush_batch()
            insert_url_as_embed(driver, line.strip())
            skip_leading_blanks = False
        else:
            # 見出し直後の空行はスキップ（スペース過多を防ぐ）
            if skip_leading_blanks and not line.strip():
                continue
            skip_leading_blanks = False
            cleaned = clean_inline_markdown(line)
            # マガジンURLが文中に混入している場合は除去（単独行で埋め込みカードとして表示するため）
            cleaned = cleaned.replace(MAGAZINE_URL, '').strip()
            if cleaned:
                batch.append(cleaned)

    flush_batch()


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
        driver.execute_script("arguments[0].scrollIntoView(true);", editor_el)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", editor_el)
        time.sleep(0.5)

        img_count = 0
        img_success = 0
        for part in parts:
            m2 = re.match(r'__IMAGE_(\d+)__', part.strip())
            if m2:
                idx = int(m2.group(1))
                if idx < len(image_paths) and image_paths[idx]:
                    img_path = image_paths[idx]
                    img_count += 1
                    print(f"  [{img_count}/{len(image_paths)}] 画像挿入中: {os.path.basename(img_path)}")
                    ok = insert_image_to_editor(driver, img_path)
                    if ok:
                        img_success += 1
                        print(f"    [OK] 画像{img_count} 挿入確認済み（DOM上にimgタグあり）")
                        # キャプション入力モードを抜けるためにEnterを2回押す
                        editor_el = driver.find_element(By.CSS_SELECTOR, ".ProseMirror")
                        editor_el.send_keys(Keys.RETURN)
                        time.sleep(0.3)
                        editor_el.send_keys(Keys.RETURN)
                        time.sleep(0.3)
                    else:
                        print(f"    [FAIL] 画像{img_count} 挿入失敗（DOM上にimgタグ増えず）")
            elif part.strip():
                insert_section_with_headings(driver, part.strip())
                time.sleep(0.3)

        # 最終検証: エディタ内のimg数を確認
        final_img_count = len(driver.find_elements(By.CSS_SELECTOR, ".ProseMirror img"))
        print(f"\n  画像挿入結果: {img_success}/{img_count} 成功（エディタ内img数: {final_img_count}）")
        if img_count > 0 and img_success == 0:
            print("  [WARN] 画像が1枚も挿入できませんでした")

        time.sleep(2)

        if price > 0:
            # 有料公開: note API で price を設定して公開
            print(f"  有料記事として公開中（{price}円）...")
            driver.set_script_timeout(20)
            # まず下書き保存
            try:
                draft_btn = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(., '下書き保存')]")
                ))
                driver.execute_script("arguments[0].click();", draft_btn)
                time.sleep(3)
                print("  下書き保存完了")
            except Exception:
                time.sleep(3)

            # 有料設定: エディタUIの「公開設定」から有料を設定
            print(f"  有料設定中（{price}円）...")
            try:
                # 「公開設定」や「販売設定」ボタンを探す
                setting_btns = driver.find_elements(By.XPATH,
                    "//button[contains(., '公開設定') or contains(., '販売設定') or contains(., '有料')]"
                )
                if not setting_btns:
                    # 「…」メニューや歯車アイコンを試す
                    setting_btns = driver.find_elements(By.CSS_SELECTOR,
                        "[aria-label*='設定'], [class*='setting'], [class*='menu']"
                    )

                if setting_btns:
                    driver.execute_script("arguments[0].click();", setting_btns[0])
                    time.sleep(2)

                # 有料ラジオボタン/チェックボックスを探す
                paid_opts = driver.find_elements(By.XPATH,
                    "//*[contains(text(), '有料') or contains(text(), '販売')]"
                )
                for opt in paid_opts:
                    try:
                        driver.execute_script("arguments[0].click();", opt)
                        time.sleep(1)
                        break
                    except Exception:
                        continue

                # 価格入力フィールドを探して入力
                price_inputs = driver.find_elements(By.CSS_SELECTOR,
                    "input[name*='price'], input[placeholder*='価格'], input[type='number']"
                )
                if price_inputs:
                    price_inputs[0].clear()
                    price_inputs[0].send_keys(str(price))
                    time.sleep(1)
                    print(f"  価格 {price}円 を入力")

                # note API経由で有料設定（エディタページに戻ってからAPIを叩く）
                driver.get(f"https://editor.note.com/notes/{note_key}/edit/")
                time.sleep(3)
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
                            price: {price}
                        }})
                    }})
                    .then(function(r) {{
                        return r.text().then(function(t) {{ done({{status: r.status, text: t}}); }});
                    }})
                    .catch(function(e) {{ done({{error: e.toString()}}); }});
                """)
                if pub_result and pub_result.get("status") in (200, 201):
                    print(f"  有料設定成功 ({price}円)")
                else:
                    print(f"  [WARN] 有料設定: status={pub_result.get('status') if pub_result else 'None'}")
                    print(f"  noteのエディタから手動で{price}円に設定してください")
            except Exception as e:
                print(f"  [WARN] 有料設定失敗: {e}")
                print(f"  noteのエディタから手動で{price}円に設定してください")
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


def update_article_body(note_key: str, append_text: str, headless: bool = True) -> bool:
    """既存記事の本文末尾にテキストを追記する。

    note API で記事を取得し、本文末尾に append_text を追加して PUT する。
    """
    driver = build_driver(headless=headless)
    wait = WebDriverWait(driver, 30)

    try:
        login(driver, wait)

        # エディタページに遷移してAPIを叩く
        driver.get(f"https://editor.note.com/notes/{note_key}/edit/")
        time.sleep(5)

        # 現在の記事データを取得
        driver.set_script_timeout(20)
        get_result = driver.execute_async_script(f"""
            var done = arguments[arguments.length - 1];
            fetch('/api/v1/text_notes/{note_key}', {{
                method: 'GET',
                credentials: 'include',
                headers: {{
                    'Accept': 'application/json',
                    'x-requested-with': 'XMLHttpRequest'
                }}
            }})
            .then(function(r) {{
                return r.text().then(function(t) {{ done({{status: r.status, text: t}}); }});
            }})
            .catch(function(e) {{ done({{error: e.toString()}}); }});
        """)

        if not get_result or get_result.get("status") not in (200, 201):
            print(f"  [WARN] 記事取得失敗 (status={get_result.get('status') if get_result else 'None'})")
            return False

        note_data = json.loads(get_result["text"])
        current_body = (note_data.get("data", {}).get("body")
                        or note_data.get("body", ""))

        # 末尾に追記
        new_body = current_body.rstrip() + "\n\n" + append_text

        # 記事を更新
        update_payload = json.dumps({"body": new_body}, ensure_ascii=False)
        update_result = driver.execute_async_script(f"""
            var done = arguments[arguments.length - 1];
            fetch('/api/v1/text_notes/{note_key}', {{
                method: 'PUT',
                credentials: 'include',
                headers: {{
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'x-requested-with': 'XMLHttpRequest'
                }},
                body: arguments[0]
            }})
            .then(function(r) {{
                return r.text().then(function(t) {{ done({{status: r.status, text: t}}); }});
            }})
            .catch(function(e) {{ done({{error: e.toString()}}); }});
        """, update_payload)

        if update_result and update_result.get("status") in (200, 201):
            print(f"  記事更新成功: {note_key}")
            return True
        else:
            print(f"  [WARN] 記事更新失敗 (status={update_result.get('status') if update_result else 'None'})")
            return False

    finally:
        driver.quit()


def main(article_file: str = "output/final.json"):
    print(f"=== ⑥ note.com 下書き保存 ({article_file}) ===")

    with open(article_file, encoding="utf-8") as f:
        data = json.load(f)

    title       = data["title"]
    body        = data["article"]
    image_paths = data.get("image_paths", [])
    cover_path  = data.get("cover_path")
    # 記事ごとのタグ（固定5 + トピック2 = 計7）
    tags = data.get("tags", NOTE_TAGS_DEFAULT)

    print(f"  タイトル: {title}")
    print(f"  本文: {len(body)} 文字")
    print(f"  タグ: {tags}")
    print(f"  カバー画像: {cover_path or '固定'}")

    headless = os.environ.get("HEADLESS", "true").lower() == "true"
    url = post_article(title, body, image_paths, tags, headless=headless, cover_path=cover_path)

    result = {
        "url":   url,
        "title": title,
        "status": "success" if url else "failed",
    }

    # 投稿済みログに追記
    import datetime
    out_path = "output/posted.json"
    result["saved_at"] = datetime.datetime.now().isoformat()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'下書き保存成功: ' + url if url else '保存失敗'}")
    return result


if __name__ == "__main__":
    main()
