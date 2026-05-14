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
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
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
        options.add_argument("--no-first-run")
        if headless:
            options.add_argument("--headless=new")
        driver = uc.Chrome(options=options, headless=headless)
        time.sleep(2)
        return driver


SESSION_PATH = os.path.expanduser("~/.note_session.pkl")


def _load_session_cookies(driver) -> bool:
    """保存済みセッションクッキーを Selenium ドライバに注入する。成功時 True を返す。"""
    import pickle
    if not os.path.exists(SESSION_PATH):
        return False
    try:
        with open(SESSION_PATH, "rb") as f:
            cookies = pickle.load(f)
        driver.get("https://note.com/")
        time.sleep(2)
        for cookie in cookies:
            cookie.pop("expiry", None)
            cookie.pop("sameSite", None)
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
        driver.refresh()
        time.sleep(3)
        driver.get("https://note.com/notes/new")
        time.sleep(5)
        if "login" not in driver.current_url:
            return True
        print("  [INFO] 保存セッションが期限切れ。再ログインが必要です。")
        os.remove(SESSION_PATH)
        return False
    except Exception as e:
        print(f"  [WARN] セッション読み込みエラー: {e}")
        return False


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
        resp_text = result.get("text", "")
        if "required_recaptcha" in resp_text:
            print("  [WARN] reCAPTCHA要求を検知。フォームログインに切り替えます...")
            _form_login(driver, wait)
        else:
            print("  ログイン成功（API）")
    else:
        print(f"  API login failed (status={result.get('status') if result else 'None'}), フォームで試みる...")
        _form_login(driver, wait)


def _form_login(driver, wait: WebDriverWait):
    """フォームベースログイン（uc環境向け）"""
    from selenium.webdriver.common.by import By
    driver.get("https://note.com/login")
    time.sleep(3)
    try:
        email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
        email_field.clear()
        email_field.send_keys(NOTE_EMAIL)
        pw_field = driver.find_element(By.ID, "password")
        pw_field.clear()
        pw_field.send_keys(NOTE_PASSWORD)
        # ログインボタンをクリック
        try:
            btn = driver.find_element(By.XPATH, "//button[contains(., 'ログイン')]")
            btn.click()
        except Exception:
            pw_field.send_keys(Keys.RETURN)
        for _ in range(15):
            time.sleep(1)
            if "login" not in driver.current_url:
                break
        if "login" not in driver.current_url:
            print("  ログイン成功（フォーム）")
        else:
            raise Exception("フォームログイン失敗。メール・パスワードを確認してください")
    except Exception as e:
        raise Exception(f"ログイン失敗: {e}")


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
    # 拡張子ではなく実際のファイルフォーマットでMIMEを決定（JPEG圧縮後も正しく処理するため）
    try:
        from PIL import Image as _pil_detect
        with _pil_detect.open(abs_path) as _img_detect:
            _fmt = _img_detect.format
        mime = "image/jpeg" if _fmt == "JPEG" else "image/png"
    except Exception:
        mime = "image/png" if fname.endswith(".png") else "image/jpeg"

    # 挿入前のimg数を記録
    before_count = len(driver.find_elements(By.CSS_SELECTOR, ".ProseMirror img"))

    # paste イベントでProseMirrorのアップロードハンドラを起動
    driver.set_script_timeout(90)
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
            } else if (attempts > 80) {  // 80 × 500ms = 40秒（大画像対応）
                clearInterval(checkInterval);
                done('paste_timeout');
            }
        }, 500);
    """, img_b64, fname, mime)

    except Exception as e:
        paste_result = f"exception: {e}"

    if paste_result == "paste_ok":
        time.sleep(2)  # caption がアクティブになるまで待機
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
    """URLをnoteの埋め込みカードとして挿入（メニューを開く → 埋め込み → URL入力）"""
    # エディタにフォーカスして末尾にキャレットを置く
    try:
        editor_el = driver.find_element(By.CSS_SELECTOR, ".ProseMirror")
        driver.execute_script("arguments[0].click(); arguments[0].focus();", editor_el)
        time.sleep(0.4)
    except Exception:
        pass

    # 空行を1行挿入（埋め込みブロックは独立した段落に挿入する必要がある）
    try:
        driver.execute_script("document.execCommand('insertText', false, arguments[0])", '\n')
        time.sleep(0.2)
    except Exception:
        pass

    # 「メニューを開く」ボタンをクリック
    menu_opened = False
    for selector in [
        "//button[@aria-label='メニューを開く']",
        "//button[contains(@aria-label,'メニュー')]",
        "//button[contains(normalize-space(),'メニューを開く')]",
    ]:
        try:
            btn = driver.find_element(By.XPATH, selector)
            driver.execute_script("arguments[0].click()", btn)
            time.sleep(0.8)
            menu_opened = True
            print(f"    [OK] メニューを開くをクリック")
            break
        except Exception:
            continue

    if not menu_opened:
        print(f"    [WARN] メニューを開くボタンが見つからない → テキストリンクで挿入: {url[:60]}")
        try:
            driver.execute_script(
                "document.execCommand('insertHTML', false, arguments[0])",
                f'<a href="{url}">{url}</a>'
            )
        except Exception:
            pass
        return

    # メニュー内の「埋め込み」をクリック
    embed_menu_clicked = False
    for selector in [
        "//button[normalize-space()='埋め込み']",
        "//li[normalize-space()='埋め込み']",
        "//*[normalize-space()='埋め込み' and (@role='menuitem' or @role='button' or self::button or self::li)]",
        "//*[normalize-space()='埋め込み']",
    ]:
        try:
            item = driver.find_element(By.XPATH, selector)
            driver.execute_script("arguments[0].click()", item)
            time.sleep(0.8)
            embed_menu_clicked = True
            print(f"    [OK] 埋め込みメニュー項目をクリック")
            break
        except Exception:
            continue

    if not embed_menu_clicked:
        print(f"    [WARN] 埋め込みメニュー項目が見つからない → テキストリンクで挿入: {url[:60]}")
        # メニューを閉じるためにEscキー
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        except Exception:
            pass
        try:
            driver.execute_script(
                "document.execCommand('insertHTML', false, arguments[0])",
                f'<a href="{url}">{url}</a>'
            )
        except Exception:
            pass
        return

    # 埋め込みダイアログが出現するまで待つ（最大8秒ポーリング）
    time.sleep(3.0)
    input_sent = False

    # ダイアログ内のinput/textareaを探す（広いセレクタから順に試行）
    embed_input_selectors = [
        # ダイアログ/モーダル内のinput
        "//*[@role='dialog']//input",
        "//*[@role='dialog']//textarea",
        "//dialog//input",
        "//dialog//textarea",
        # placeholder="URL" を含むinput
        "//input[contains(@placeholder,'URL') or contains(@placeholder,'url') or contains(@placeholder,'http')]",
        "//input[@type='url']",
        # 表示中のinputのうちvalue属性が空のもの（タイトル入力欄は除外）
        "//input[@type='text' and not(@id) and not(@name='title')]",
        "//textarea[contains(@placeholder,'URL') or contains(@placeholder,'url') or contains(@placeholder,'http')]",
    ]

    for sel in embed_input_selectors:
        try:
            inp = WebDriverWait(driver, 8).until(
                EC.visibility_of_element_located((By.XPATH, sel))
            )
            inp.clear()
            inp.send_keys(url)
            time.sleep(0.3)
            inp.send_keys(Keys.RETURN)
            time.sleep(3.0)  # 埋め込みカード生成を待つ
            input_sent = True
            print(f"    [OK] URL埋め込み完了 (selector={sel[:50]}): {url[:60]}")
            break
        except Exception:
            continue

    if not input_sent:
        # デバッグ：全input/textarea要素の状態を出力
        try:
            debug_info = []
            for tag in ['input', 'textarea']:
                elems = driver.find_elements(By.TAG_NAME, tag)
                for e in elems:
                    try:
                        debug_info.append({
                            'tag': tag,
                            'type': e.get_attribute('type'),
                            'placeholder': e.get_attribute('placeholder'),
                            'visible': e.is_displayed(),
                            'role': e.get_attribute('role'),
                        })
                    except Exception:
                        pass
            print(f"    [DEBUG] 全input/textarea: {debug_info[:15]}")
        except Exception:
            pass
        # Escでメニューを閉じてからフォールバック
        try:
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.3)
        except Exception:
            pass
        print(f"    [WARN] URL入力フィールドが見つからない → テキストリンクで挿入: {url[:60]}")
        try:
            driver.execute_script(
                "document.execCommand('insertHTML', false, arguments[0])",
                f'<a href="{url}">{url}</a>'
            )
        except Exception:
            pass


def insert_section_with_headings(driver, section_text: str):
    """セクションテキストを挿入（# → h2大見出し、## → h2大見出し、### → h3小見出し、URL単独行 → 埋め込み）"""
    # 3連続以上の改行を2連続に圧縮してスペース過多を防ぐ
    section_text = re.sub(r'\n{3,}', '\n\n', section_text)
    lines = section_text.split('\n')
    batch: list[str] = []
    skip_leading_blanks = False  # 見出し直後の空行をスキップするフラグ
    last_was_paragraph_break = False  # 連続空行で二重スペースを防ぐフラグ

    def flush_batch():
        # 末尾の空行を除去
        while batch and not batch[-1].strip():
            batch.pop()
        if not batch:
            return
        text = '\n'.join(batch)
        # 「。」の後に\nを挿入（後でShift+Enterに変換）
        text = re.sub(r'。(?!\n)', '。\n', text)
        # 連続\nを単一に圧縮
        text = re.sub(r'\n{2,}', '\n', text)
        text = text.rstrip('\n')

        # \nごとにShift+Enterで挿入（段落内行変え：スペースなし）
        segments = text.split('\n')
        for i, seg in enumerate(segments):
            if seg:
                driver.execute_script(
                    "document.execCommand('insertText', false, arguments[0])", seg
                )
            if i < len(segments) - 1:
                ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.RETURN).key_up(Keys.SHIFT).perform()
                time.sleep(0.03)
        batch.clear()

    for line in lines:
        # # / ## / ### の見出し行（# が1〜3個）
        m = re.match(r'^(#{1,3})\s+(.*)', line)
        if m:
            flush_batch()
            last_was_paragraph_break = False
            level = len(m.group(1))  # 1〜2 → h2（大見出し）、3 → h3（小見出し）
            heading_tag = 'h3' if level >= 3 else 'h2'
            heading_text = clean_inline_markdown(m.group(2).strip())
            # insertHTML で h2/h3 を挿入し、直後に空段落を作ってカーソルを確実に見出し外へ
            driver.execute_script(
                "document.execCommand('insertHTML', false, arguments[0])",
                f'<{heading_tag}>{heading_text}</{heading_tag}>'
            )
            time.sleep(0.5)
            # JS で見出し直後に空段落を挿入してカーソルをそこへ移動
            driver.execute_script("""
                var editor = document.querySelector('.ProseMirror');
                var last = editor.lastElementChild;
                if (last && (last.tagName === 'H2' || last.tagName === 'H3')) {
                    // 見出しが末尾 → insertParagraph で段落を作成
                    document.execCommand('insertParagraph', false, null);
                } else if (last) {
                    // 既に段落がある → そこにカーソルを移動
                    var range = document.createRange();
                    range.setStart(last, 0);
                    range.collapse(true);
                    var sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                }
                editor.focus();
            """)
            time.sleep(0.3)
            skip_leading_blanks = True  # 見出し直後の空行をスキップ
        # URL単独行 → 埋め込みカード
        elif re.match(r'^https?://\S+$', line.strip()):
            flush_batch()
            insert_url_as_embed(driver, line.strip())
            skip_leading_blanks = False
            last_was_paragraph_break = False
        else:
            # 見出し直後の空行はスキップ（スペース過多を防ぐ）
            if skip_leading_blanks and not line.strip():
                continue
            skip_leading_blanks = False

            if not line.strip():
                # 空行 = 段落区切り → flush後にEnter1回で段落を区切る（1行スペース）
                if not last_was_paragraph_break:
                    flush_batch()
                    driver.execute_script("document.execCommand('insertText', false, arguments[0])", '\n')
                    last_was_paragraph_break = True
            else:
                last_was_paragraph_break = False
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


def post_article(title: str, body: str, image_paths: list[str], tags: list[str], headless: bool = True, cover_path: str | None = None, price: int = 0, auto_publish: bool = False) -> str:
    """note に記事を保存してURLを返す。price>0の場合は有料公開する。auto_publish=Trueで無料公開する"""
    # cover_path を早期に解決（後でドメインをまたがずに使えるよう）
    if not cover_path:
        cover_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "cover_image.png"))
    driver = build_driver(headless=headless)
    wait   = WebDriverWait(driver, 30)

    try:
        login(driver, wait)

        # 新規記事エディタを開く
        print("  エディタを開いています...")

        # 方法0: Python requests で直接 API 呼び出し（CloudFront JS fetch WAF 回避）
        note_key = None
        print("  Python requests でノート作成を試みる...")
        try:
            import requests as _req
            _session = _req.Session()
            for _c in driver.get_cookies():
                _session.cookies.set(_c['name'], _c['value'], domain='.note.com')
            _session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'x-requested-with': 'XMLHttpRequest',
                'Origin': 'https://note.com',
                'Referer': 'https://note.com/',
            })
            _r = _session.post('https://note.com/api/v1/text_notes', json={'status': 'draft'}, timeout=15)
            if _r.status_code in (200, 201):
                _data = _r.json()
                note_key = _data.get('data', {}).get('key') or _data.get('key')
                if note_key:
                    print(f"  Python requests でノート作成成功: {note_key}")
                    driver.get(f"https://editor.note.com/notes/{note_key}/edit/")
                    time.sleep(5)
            else:
                print(f"  Python requests 失敗 (status={_r.status_code}): {_r.text[:100]}")
        except Exception as _e:
            print(f"  Python requests エラー: {_e}")

        # 方法1: /notes/new に遷移してURLが変わるまで最大60秒待つ
        if not note_key:
            driver.get("https://note.com/notes/new")
            for i in range(90):
                time.sleep(1)
                current = driver.current_url
                m = re.search(r"/notes/([a-zA-Z0-9]+)/edit", current)
                if m:
                    note_key = m.group(1)
                    break
            # editor.note.com/new に遷移した場合もそこでリダイレクトを待つ
            if not note_key and "editor.note.com" in driver.current_url:
                for i in range(90):
                    time.sleep(1)
                    current = driver.current_url
                    m = re.search(r"/notes/([a-zA-Z0-9]+)/edit", current)
                    if m:
                        note_key = m.group(1)
                        break
                    # /new のまま止まっていたらボタンをクリック試行
                    if i == 5 and "/new" in current:
                        try:
                            btn = driver.find_element("css selector", "button[class*='create'], button[class*='new'], a[href*='/notes/']")
                            btn.click()
                        except Exception:
                            pass

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

        # ── カバー画像（アイキャッチ）設定 ──
        # クリック操作はすべて純粋な JS（document.querySelector().click()）で行う。
        # find_element → execute_script(arguments[0].click()) のパターンは
        # StaleElementReferenceException を起こすため使用禁止。
        if cover_path and os.path.exists(cover_path):
            print("  カバー画像を設定中...")
            cover_set = False
            for _attempt in range(3):
                try:
                    time.sleep(3 + _attempt * 3)
                    # 前の試行で開いたモーダルをESCでリセット
                    if _attempt > 0:
                        try:
                            from selenium.webdriver.common.keys import Keys as _Keys
                            driver.find_element(By.TAG_NAME, "body").send_keys(_Keys.ESCAPE)
                            time.sleep(1)
                        except Exception:
                            pass

                    # 既存のアイキャッチがある場合は先に削除ボタン（×）を押す
                    driver.execute_script("""
                        // alt="eyecatch" の画像が存在する場合、その近傍の削除ボタンを探してクリック
                        var existing = document.querySelector('img[alt="eyecatch"]');
                        if (existing) {
                            var container = existing.closest('[data-dragging]');
                            if (container) {
                                var delBtn = container.querySelector('button');
                                if (delBtn) { delBtn.click(); }
                            }
                        }
                    """)
                    time.sleep(1.5)

                    # 「画像を追加」ボタンをJS querySelector で直接クリック（stale 回避）
                    clicked = False
                    for _ in range(20):
                        result = driver.execute_script("""
                            var selectors = [
                                'button[aria-label="画像を追加"]',
                                'button[aria-label="Add image"]',
                                'button[class*="eyecatch"]',
                                'label[for="note-editor-eyecatch-input"]'
                            ];
                            for (var s of selectors) {
                                var el = document.querySelector(s);
                                if (el) { el.click(); return s; }
                            }
                            // 画像を追加エリア全体をクリック（テキスト"サムネイル"などがある場合）
                            var allBtns = Array.from(document.querySelectorAll('button'));
                            for (var b of allBtns) {
                                var t = (b.textContent || '').trim();
                                if (t.includes('サムネイル') || t.includes('画像を設定')) {
                                    b.click(); return 'サムネイルボタン';
                                }
                            }
                            return null;
                        """)
                        if result:
                            clicked = True
                            break
                        time.sleep(0.5)
                    if not clicked:
                        raise Exception("「画像を追加」ボタンが見つかりません")
                    time.sleep(1.5)

                    # 「アップロード」ボタンがある場合はJSでクリック
                    driver.execute_script("""
                        var btns = Array.from(document.querySelectorAll('button'));
                        for (var b of btns) {
                            var t = b.textContent || '';
                            if (t.includes('アップロード') && t.includes('画像')) { b.click(); break; }
                            if (t.includes('Upload') || t.includes('upload')) { b.click(); break; }
                        }
                    """)
                    time.sleep(1)

                    # ファイル入力欄を待機（send_keys はWebDriver要素が必要なため最短で取得）
                    eyecatch_input = None
                    for _ in range(20):
                        els = driver.find_elements(By.ID, "note-editor-eyecatch-input")
                        if not els:
                            els = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"][accept*="image"]')
                        if els:
                            eyecatch_input = els[0]
                            break
                        time.sleep(0.4)
                    if not eyecatch_input:
                        raise Exception("eyecatch-input が見つかりません")
                    driver.execute_script(
                        "arguments[0].removeAttribute('style'); arguments[0].removeAttribute('hidden');",
                        eyecatch_input,
                    )
                    eyecatch_input.send_keys(os.path.abspath(cover_path))
                    time.sleep(5)  # ファイル読み込みとクロップモーダル表示を待つ

                    # 「保存」「完了」「確定」ボタンをJSで探してクリック（stale 回避）
                    # 「下書き保存」「一時保存」「公開に進む」は除外する
                    found_label = None
                    for _ in range(25):
                        time.sleep(0.5)
                        found_label = driver.execute_script("""
                            var keywords = ['保存', '完了', '確定', 'Save', 'Done'];
                            var excludes = ['下書き', '一時', '公開'];
                            var btns = Array.from(document.querySelectorAll('button'));
                            for (var btn of btns) {
                                var txt = (btn.textContent || '').trim();
                                var skip = false;
                                for (var ex of excludes) { if (txt.includes(ex)) { skip=true; break; } }
                                if (skip) continue;
                                for (var kw of keywords) {
                                    if (txt.includes(kw)) { btn.click(); return txt; }
                                }
                            }
                            return null;
                        """)
                        if found_label:
                            cover_set = True
                            print(f"  カバー画像 設定完了（「{found_label}」クリック）")
                            time.sleep(3)
                            break
                    if cover_set:
                        break
                except Exception as _e2:
                    print(f"  [WARN] カバー画像設定失敗（試行{_attempt+1}/3）: {type(_e2).__name__}: {_e2}")
            if not cover_set:
                print("  [WARN] カバー画像を設定できませんでした（手動設定が必要）")

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
        prev_ended_with_heading = False
        for part in parts:
            m2 = re.match(r'__IMAGE_(\d+)__', part.strip())
            if m2:
                idx = int(m2.group(1))
                if idx < len(image_paths) and image_paths[idx]:
                    img_path = image_paths[idx]
                    img_count += 1
                    print(f"  [{img_count}/{len(image_paths)}] 画像挿入中: {os.path.basename(img_path)}")
                    # 見出し直後の場合は BACKSPACE を使わず JS で空段落を除去する
                    # （BACKSPACE だとカーソルが h2/h3 内に戻ってしまうため）
                    if prev_ended_with_heading:
                        try:
                            driver.execute_script("""
                                var editor = document.querySelector('.ProseMirror');
                                if (!editor) return;
                                var last = editor.lastChild;
                                if (last && last.nodeName === 'P' && !last.textContent.trim()) {
                                    var prev = last.previousSibling;
                                    if (prev && (prev.nodeName === 'H2' || prev.nodeName === 'H3')) {
                                        last.remove();
                                        var range = document.createRange();
                                        range.selectNodeContents(editor);
                                        range.collapse(false);
                                        var sel = window.getSelection();
                                        sel.removeAllRanges();
                                        sel.addRange(range);
                                        editor.focus();
                                    }
                                }
                            """)
                            time.sleep(0.15)
                        except Exception:
                            pass
                    else:
                        try:
                            editor_el = driver.find_element(By.CSS_SELECTOR, ".ProseMirror")
                            editor_el.send_keys(Keys.BACK_SPACE)
                            time.sleep(0.1)
                        except Exception:
                            pass
                    prev_ended_with_heading = False
                    ok = insert_image_to_editor(driver, img_path)
                    if ok:
                        img_success += 1
                        print(f"    [OK] 画像{img_count} 挿入確認済み（DOM上にimgタグあり）")
                        # キャプション欄から確実に抜け出す（Escape→ArrowDown×2）
                        try:
                            from selenium.webdriver.common.action_chains import ActionChains
                            editor_el = driver.find_element(By.CSS_SELECTOR, ".ProseMirror")
                            # Escape でキャプション編集モードを終了
                            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                            time.sleep(0.15)
                            # ArrowDown で figure ブロックの外へ移動
                            editor_el.send_keys(Keys.ARROW_DOWN)
                            time.sleep(0.1)
                            editor_el.send_keys(Keys.ARROW_DOWN)
                            time.sleep(0.1)
                            # figcaption がまだアクティブなら JS で強制移動
                            still_in_caption = driver.execute_script("""
                                var sel = window.getSelection();
                                if (!sel || !sel.anchorNode) return false;
                                var node = sel.anchorNode;
                                while (node) {
                                    if (node.nodeName === 'FIGCAPTION') return true;
                                    node = node.parentElement;
                                }
                                return false;
                            """)
                            if still_in_caption:
                                driver.execute_script("""
                                    var editor = document.querySelector('.ProseMirror');
                                    var p = document.createElement('p');
                                    p.innerHTML = '<br>';
                                    editor.appendChild(p);
                                    var range = document.createRange();
                                    range.setStart(p, 0);
                                    range.collapse(true);
                                    var sel = window.getSelection();
                                    sel.removeAllRanges();
                                    sel.addRange(range);
                                    editor.focus();
                                """)
                        except Exception:
                            pass
                        time.sleep(0.3)
                    else:
                        print(f"    [FAIL] 画像{img_count} 挿入失敗（DOM上にimgタグ増えず）")
            elif part.strip():
                insert_section_with_headings(driver, part.strip())
                # テキストパートが見出し（H2/H3）で終わっているか確認
                stripped_lines = [l for l in part.strip().split('\n') if l.strip()]
                prev_ended_with_heading = bool(stripped_lines and re.match(r'^#{1,3}\s', stripped_lines[-1]))
                time.sleep(0.3)

        # 最終検証: エディタ内のimg数を確認
        final_img_count = len(driver.find_elements(By.CSS_SELECTOR, ".ProseMirror img"))
        print(f"\n  画像挿入結果: {img_success}/{img_count} 成功（エディタ内img数: {final_img_count}）")
        if img_count > 0 and img_success == 0:
            print("  [WARN] 画像が1枚も挿入できませんでした")

        # 全画像挿入後にキャプション欄をクリア（残留キャプション対策）
        try:
            # まず Escape でキャプション入力モードを解除
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.3)
        except Exception:
            pass
        try:
            driver.execute_script("""
                var editor = document.querySelector('.ProseMirror');
                if (!editor) return;
                // 末尾に確実に空段落を追加してキャレットをそこへ移動
                var anchor = document.createElement('p');
                anchor.innerHTML = '<br>';
                editor.appendChild(anchor);
                var range = document.createRange();
                var sel = window.getSelection();
                range.setStart(anchor, 0);
                range.collapse(true);
                sel.removeAllRanges();
                sel.addRange(range);
                editor.focus();
            """)
            time.sleep(0.2)
            # さらに矢印キーで確実にfigcaptionの外へ
            editor_el = driver.find_element(By.CSS_SELECTOR, ".ProseMirror")
            editor_el.send_keys(Keys.ARROW_DOWN)
            editor_el.send_keys(Keys.ARROW_DOWN)
            time.sleep(0.2)
        except Exception:
            pass

        time.sleep(2)

        if price > 0:
            # 有料記事: 下書き保存のみ（価格設定・公開は手動で行う）
            print(f"  有料記事（{price}円）を下書き保存中...")
            _paid_published = False
            try:
                draft_btn = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(., '下書き保存')]")
                ))
                driver.execute_script("arguments[0].click();", draft_btn)
                time.sleep(3)
                print("  下書き保存完了")
            except Exception:
                time.sleep(5)
            print(f"  ✏️  手動で {price}円 に設定して公開してください: https://editor.note.com/notes/{note_key}/edit/")
        elif auto_publish:
            # 無料記事を公開: まず下書き保存 → API で status を publish に変更
            print("  無料記事を公開中...")
            try:
                draft_btn = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(., '下書き保存')]")
                ))
                driver.execute_script("arguments[0].click();", draft_btn)
                time.sleep(3)
                print("  下書き保存完了")
            except Exception:
                time.sleep(3)

            # まず UI で「公開に進む」→「公開する」を試みる
            _published = False
            try:
                pub_btn = None
                for _ in range(20):
                    # text() と normalize-space() の両方で検索
                    btns = driver.find_elements(
                        By.XPATH,
                        "//button[contains(normalize-space(),'公開に進む') or contains(normalize-space(),'公開する')]"
                    )
                    # 「下書き保存」を除外
                    btns = [b for b in btns if "下書き" not in (b.text or "")]
                    if btns:
                        pub_btn = btns[0]
                        break
                    time.sleep(1)
                if pub_btn:
                    btn_text = (pub_btn.text or "").strip()
                    driver.execute_script("arguments[0].click();", pub_btn)
                    time.sleep(3)
                    print(f"  「{btn_text}」クリック完了")
                    if "進む" in btn_text:
                        # 公開設定画面の「投稿する」ボタンをクリック
                        for _ in range(20):
                            time.sleep(0.5)
                            final_btns = driver.find_elements(
                                By.XPATH,
                                "//button[normalize-space()='投稿する' or normalize-space()='公開する' or normalize-space()='公開']"
                            )
                            final_btns = [b for b in final_btns if "下書き" not in (b.text or "")]
                            if final_btns:
                                driver.execute_script("arguments[0].click();", final_btns[0])
                                time.sleep(3)
                                _published = True
                                print(f"  「{(final_btns[0].text or '').strip()}」クリック完了")
                                break
                    else:
                        _published = True
                else:
                    print("  [WARN] 「公開に進む」ボタンが見つかりません、API公開を試みます...")
            except Exception as e:
                print(f"  [WARN] UI公開失敗: {e}")

            # UI公開失敗時: API で公開（複数エンドポイントを試す）
            if not _published and note_key:
                for _ep in [
                    f"/api/v2/text_notes/{note_key}",
                    f"/api/v1/text_notes/{note_key}",
                ]:
                    try:
                        driver.get("https://note.com/")
                        time.sleep(2)
                        pub_result = driver.execute_async_script("""
                            var done = arguments[arguments.length - 1];
                            var ep = arguments[0];
                            fetch(ep, {
                                method: 'PUT',
                                credentials: 'same-origin',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/json',
                                    'x-requested-with': 'XMLHttpRequest'
                                },
                                body: JSON.stringify({status: 'publish'})
                            })
                            .then(function(r) {
                                return r.text().then(function(t) { done({status: r.status, text: t}); });
                            })
                            .catch(function(e) { done({error: e.toString()}); });
                        """, _ep)
                        if pub_result and pub_result.get("status") in (200, 201):
                            _published = True
                            print(f"  API公開完了 ({_ep}): status={pub_result['status']}")
                            break
                        else:
                            print(f"  [WARN] API失敗 ({_ep}): status={pub_result.get('status') if pub_result else 'None'}")
                    except Exception as e:
                        print(f"  [WARN] API公開例外 ({_ep}): {e}")

            if not _published:
                print("  [WARN] 公開失敗（下書き保存のまま）")
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
        status_label = "下書き保存"
        print(f"  {status_label}完了: {url}")
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


def set_eyecatch(note_key: str, cover_path: str, headless: bool = False) -> bool:
    """既存記事のカバー画像（アイキャッチ）だけを設定する。"""
    if not os.path.exists(cover_path):
        print(f"  [ERROR] カバー画像が見つかりません: {cover_path}")
        return False

    driver = build_driver(headless=headless)
    wait = WebDriverWait(driver, 30)
    try:
        login(driver, wait)
        driver.get(f"https://editor.note.com/notes/{note_key}/edit/")
        time.sleep(6)

        cover_set = False
        for _attempt in range(3):
            try:
                time.sleep(3 + _attempt * 3)
                if _attempt > 0:
                    try:
                        from selenium.webdriver.common.keys import Keys as _Keys
                        driver.find_element(By.TAG_NAME, "body").send_keys(_Keys.ESCAPE)
                        time.sleep(1)
                    except Exception:
                        pass

                # 既存のアイキャッチがある場合は削除ボタン（×）を先に押す
                driver.execute_script("""
                    var existing = document.querySelector('img[alt="eyecatch"]');
                    if (existing) {
                        var container = existing.closest('[data-dragging]');
                        if (container) {
                            var delBtn = container.querySelector('button');
                            if (delBtn) { delBtn.click(); }
                        }
                    }
                """)
                time.sleep(1.5)

                clicked = False
                for _ in range(20):
                    result = driver.execute_script("""
                        var selectors = [
                            'button[aria-label="画像を追加"]',
                            'button[aria-label="Add image"]',
                            'button[class*="eyecatch"]',
                            'label[for="note-editor-eyecatch-input"]'
                        ];
                        for (var s of selectors) {
                            var el = document.querySelector(s);
                            if (el) { el.click(); return s; }
                        }
                        var allBtns = Array.from(document.querySelectorAll('button'));
                        for (var b of allBtns) {
                            var t = (b.textContent || '').trim();
                            if (t.includes('サムネイル') || t.includes('画像を設定')) {
                                b.click(); return 'サムネイルボタン';
                            }
                        }
                        return null;
                    """)
                    if result:
                        clicked = True
                        break
                    time.sleep(0.5)
                if not clicked:
                    raise Exception("「画像を追加」ボタンが見つかりません")
                time.sleep(1.5)

                driver.execute_script("""
                    var btns = Array.from(document.querySelectorAll('button'));
                    for (var b of btns) {
                        var t = b.textContent || '';
                        if (t.includes('アップロード') && t.includes('画像')) { b.click(); break; }
                        if (t.includes('Upload') || t.includes('upload')) { b.click(); break; }
                    }
                """)
                time.sleep(1)

                eyecatch_input = None
                for _ in range(20):
                    els = driver.find_elements(By.ID, "note-editor-eyecatch-input")
                    if not els:
                        els = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"][accept*="image"]')
                    if els:
                        eyecatch_input = els[0]
                        break
                    time.sleep(0.4)
                if not eyecatch_input:
                    raise Exception("eyecatch-input が見つかりません")
                driver.execute_script(
                    "arguments[0].removeAttribute('style'); arguments[0].removeAttribute('hidden');",
                    eyecatch_input,
                )
                eyecatch_input.send_keys(os.path.abspath(cover_path))
                time.sleep(5)

                found_label = None
                for _ in range(25):
                    time.sleep(0.5)
                    found_label = driver.execute_script("""
                        var keywords = ['保存', '完了', '確定', 'Save', 'Done'];
                        var excludes = ['下書き', '一時', '公開'];
                        var btns = Array.from(document.querySelectorAll('button'));
                        for (var btn of btns) {
                            var txt = (btn.textContent || '').trim();
                            var skip = false;
                            for (var ex of excludes) { if (txt.includes(ex)) { skip=true; break; } }
                            if (skip) continue;
                            for (var kw of keywords) {
                                if (txt.includes(kw)) { btn.click(); return txt; }
                            }
                        }
                        return null;
                    """)
                    if found_label:
                        cover_set = True
                        print(f"  カバー画像 設定完了（「{found_label}」クリック）: {note_key}")
                        time.sleep(3)
                        break
                if cover_set:
                    break
            except Exception as _e2:
                print(f"  [WARN] カバー画像設定失敗（試行{_attempt+1}/3）: {type(_e2).__name__}: {_e2}")

        if not cover_set:
            print(f"  [WARN] カバー画像を設定できませんでした: {note_key}")
        return cover_set
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
    url = post_article(title, body, image_paths, tags, headless=headless, cover_path=cover_path, auto_publish=False)

    result = {
        "url":   url,
        "title": title,
        "status": "success" if url else "failed",
    }

    # 投稿済みログに追記
    import datetime
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(_base, "output", "posted.json")
    result["posted_at"] = datetime.datetime.now().isoformat()
    result["saved_at"] = result["posted_at"]  # backward compat
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'下書き保存成功: ' + url if url else '保存失敗'}")
    return result


if __name__ == "__main__":
    import sys
    article_file = sys.argv[1] if len(sys.argv) > 1 else "output/final.json"
    main(article_file=article_file)
