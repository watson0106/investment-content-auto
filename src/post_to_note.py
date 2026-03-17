"""
⑥ note.com へ自動投稿
Selenium + JS API で note にログインして記事を投稿する
（エディタDOM操作ではなく内部APIを直接呼び出す方式）
"""

from __future__ import annotations


import json
import os
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

NOTE_EMAIL    = os.environ["NOTE_EMAIL"]
NOTE_PASSWORD = os.environ["NOTE_PASSWORD"]

NOTE_TAGS = ["投資", "米国株", "日本株", "投資情報", "マーケット", "経済", "株式投資", "AI分析"]


def build_driver(headless: bool = True) -> uc.Chrome:
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    return uc.Chrome(options=options, headless=headless)


def login(driver: uc.Chrome, wait: WebDriverWait):
    print("  note にログイン中...")
    # まず note.com を開いてCookieを初期化
    driver.get("https://note.com/login")
    time.sleep(3)

    # JS fetch で直接セッションAPIを呼び出す（フォーム操作をバイパス）
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
        # フォールバック：通常のフォームログイン
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
            print(f"  現在URL: {driver.current_url}")
            raise Exception("ログイン失敗。メール・パスワードを確認してください")


def api_call(driver: uc.Chrome, url: str, method: str = "GET", body: dict | None = None) -> dict:
    """ブラウザのJS fetchでnote APIを呼び出す（認証Cookie自動付与）"""
    driver.set_script_timeout(30)
    body_str = json.dumps(body) if body else "null"
    script = f"""
        var done = arguments[arguments.length - 1];
        var opts = {{
            method: '{method}',
            credentials: 'include',
            headers: {{
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'x-requested-with': 'XMLHttpRequest'
            }}
        }};
        var bodyData = {body_str};
        if (bodyData !== null) {{
            opts.body = JSON.stringify(bodyData);
        }}
        fetch('{url}', opts)
            .then(function(r) {{
                return r.text().then(function(t) {{ done({{status: r.status, text: t}}); }});
            }})
            .catch(function(e) {{ done({{error: e.toString()}}); }});
    """
    return driver.execute_async_script(script)


def create_draft(driver: uc.Chrome) -> tuple[int, str]:
    """ドラフト記事を作成してID・keyを返す"""
    print("  ドラフト作成中...")
    # editor.note.com へ移動（ここからのfetchが許可される）
    driver.get("https://note.com/notes/new")
    time.sleep(6)

    r = api_call(driver, "https://note.com/api/v1/text_notes", "POST", {"template_key": None})
    if r.get("error"):
        raise Exception(f"ドラフト作成失敗: {r['error']}")
    if r.get("status") not in (200, 201):
        raise Exception(f"ドラフト作成失敗: status={r.get('status')}, body={r.get('text', '')[:200]}")

    data = json.loads(r["text"])["data"]
    note_id  = data["id"]
    note_key = data["key"]
    print(f"  ドラフト作成完了: id={note_id}, key={note_key}")
    return note_id, note_key


def update_note(driver: uc.Chrome, note_id: int, title: str, body_html: str,
               status: str = "draft", tags: list[str] | None = None) -> dict:
    """記事タイトル・本文・ステータスを更新"""
    payload: dict = {
        "name": title,
        "body": body_html,
        "status": status,
    }
    if tags:
        # note は最大5タグ、スペース区切り文字列で渡す
        payload["hashtag_list"] = " ".join(tags[:5])
    r = api_call(
        driver,
        f"https://note.com/api/v1/text_notes/{note_id}",
        "PUT",
        payload
    )
    if r.get("error"):
        raise Exception(f"記事更新失敗: {r['error']}")
    return json.loads(r["text"]) if r.get("text") else {}


def markdown_to_html(text: str) -> str:
    """マークダウンテキストをnote用のシンプルなHTMLに変換"""
    lines = text.split("\n")
    html_lines = []
    for line in lines:
        if line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.strip() == "":
            html_lines.append("<br>")
        else:
            html_lines.append(f"<p>{line}</p>")
    return "".join(html_lines)


def post_article(title: str, body: str, image_paths: list[str], tags: list[str], headless: bool = True) -> str:
    """note に記事を投稿してURLを返す"""
    driver = build_driver(headless=headless)
    wait   = WebDriverWait(driver, 20)

    try:
        login(driver, wait)

        note_id, note_key = create_draft(driver)

        # 本文をHTML変換してドラフト保存
        body_html = markdown_to_html(body[:50000])
        print(f"  本文更新中（{len(body)} 文字）...")
        update_note(driver, note_id, title, body_html, status="draft")

        # 公開（タグも含めて一緒に設定）
        print("  公開中...")
        pub_result = update_note(driver, note_id, title, body_html, status="published", tags=tags)

        # URLを構築
        urlname = None
        if pub_result.get("data"):
            urlname = pub_result["data"].get("user", {}).get("urlname") or "kawasewatson0106"
        else:
            urlname = "kawasewatson0106"

        url = f"https://note.com/{urlname}/n/{note_key}"
        print(f"  公開完了: {url}")
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

    print(f"  タイトル: {title}")
    print(f"  本文: {len(body)} 文字")
    print(f"  画像: {len(image_paths)} 枚")

    headless = os.environ.get("HEADLESS", "true").lower() == "true"
    url = post_article(title, body, image_paths, NOTE_TAGS, headless=headless)

    result = {
        "url":   url,
        "title": title,
        "status": "success" if url else "failed",
    }

    out_path = "output/posted.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'✅ 投稿成功: ' + url if url else '❌ 投稿失敗'}")
    return result


if __name__ == "__main__":
    main()
