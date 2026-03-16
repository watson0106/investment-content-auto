"""
⑥ note.com へ自動投稿
Selenium で note にログインして記事を投稿する
"""

import json
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

NOTE_EMAIL    = os.environ["NOTE_EMAIL"]
NOTE_PASSWORD = os.environ["NOTE_PASSWORD"]

NOTE_TAGS = ["投資", "米国株", "日本株", "投資情報", "マーケット", "経済", "株式投資", "AI分析"]


def build_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def login(driver: webdriver.Chrome, wait: WebDriverWait):
    print("  note にログイン中...")
    driver.get("https://note.com/login")
    time.sleep(2)

    # メールアドレス入力
    email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
    email_field.clear()
    email_field.send_keys(NOTE_EMAIL)

    # パスワード入力
    pw_field = driver.find_element(By.NAME, "password")
    pw_field.clear()
    pw_field.send_keys(NOTE_PASSWORD)
    pw_field.send_keys(Keys.RETURN)

    time.sleep(3)

    if "note.com" in driver.current_url and "login" not in driver.current_url:
        print("  ログイン成功")
    else:
        raise Exception("ログイン失敗。メール・パスワードを確認してください")


def create_new_article(driver: webdriver.Chrome, wait: WebDriverWait):
    """新規テキスト記事を作成"""
    print("  新規記事作成中...")
    driver.get("https://note.com/notes/new")
    time.sleep(3)


def set_title(driver: webdriver.Chrome, wait: WebDriverWait, title: str):
    """タイトルを入力"""
    try:
        title_el = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, '[placeholder="タイトル"], .o-noteTitle__input, [data-placeholder="タイトル"]')
        ))
        title_el.click()
        title_el.clear()
        title_el.send_keys(title)
        print(f"  タイトル設定: {title[:30]}...")
    except Exception as e:
        print(f"  [WARN] タイトル設定エラー: {e}")


def set_body(driver: webdriver.Chrome, wait: WebDriverWait, body: str):
    """本文を入力"""
    try:
        # note エディタの本文エリア
        body_el = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, '.ProseMirror, [contenteditable="true"].DraftEditor-content, .o-bodyNote__content')
        ))
        body_el.click()
        time.sleep(0.5)

        # 長いテキストは JavaScript で挿入
        driver.execute_script(
            "arguments[0].innerText = arguments[1];",
            body_el,
            body[:10000]  # note の文字数制限を考慮
        )
        print(f"  本文設定完了（{len(body)} 文字）")
    except Exception as e:
        print(f"  [WARN] 本文設定エラー: {e}")


def upload_images(driver: webdriver.Chrome, wait: WebDriverWait, image_paths: list[str]):
    """画像をアップロード（サムネイル）"""
    if not image_paths:
        return
    try:
        # サムネイル設定ボタンを探す
        thumb_btn = driver.find_elements(By.CSS_SELECTOR, '[data-test="thumbnail-upload"], .o-thumbnail__upload')
        if thumb_btn:
            thumb_btn[0].click()
            time.sleep(1)
            file_input = driver.find_element(By.CSS_SELECTOR, 'input[type="file"]')
            file_input.send_keys(os.path.abspath(image_paths[0]))
            time.sleep(2)
            print(f"  サムネイル設定: {image_paths[0]}")
    except Exception as e:
        print(f"  [WARN] 画像アップロードエラー: {e}")


def set_tags(driver: webdriver.Chrome, wait: WebDriverWait, tags: list[str]):
    """タグを設定"""
    try:
        # 公開設定モーダルのタグ入力欄
        tag_inputs = driver.find_elements(By.CSS_SELECTOR, '[placeholder*="タグ"], .o-tag__input')
        if tag_inputs:
            for tag in tags[:5]:  # note は最大5タグ
                tag_inputs[0].send_keys(tag)
                time.sleep(0.3)
                tag_inputs[0].send_keys(Keys.RETURN)
                time.sleep(0.3)
            print(f"  タグ設定: {tags[:5]}")
    except Exception as e:
        print(f"  [WARN] タグ設定エラー: {e}")


def publish(driver: webdriver.Chrome, wait: WebDriverWait) -> str:
    """公開を実行して URL を返す"""
    try:
        # 公開ボタンをクリック
        publish_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, '[data-test="publish-button"], .o-publish__button, button.m-button--primary')
        ))
        publish_btn.click()
        time.sleep(2)

        # 公開設定モーダルが出たら「公開する」ボタンを押す
        confirm_btns = driver.find_elements(By.XPATH, "//button[contains(text(), '公開する')]")
        if confirm_btns:
            confirm_btns[0].click()
            time.sleep(3)

        url = driver.current_url
        print(f"  公開完了: {url}")
        return url

    except Exception as e:
        print(f"  [WARN] 公開エラー: {e}")
        return ""


def post_article(title: str, body: str, image_paths: list[str], tags: list[str], headless: bool = True) -> str:
    """note に記事を投稿してURLを返す"""
    driver = build_driver(headless=headless)
    wait   = WebDriverWait(driver, 20)

    try:
        login(driver, wait)
        create_new_article(driver, wait)
        set_title(driver, wait, title)
        set_body(driver, wait, body)

        if image_paths:
            upload_images(driver, wait, image_paths)

        # 公開ボタンをクリックして設定モーダルへ
        pub_btns = driver.find_elements(By.XPATH, "//button[contains(text(), '公開設定')]")
        if pub_btns:
            pub_btns[0].click()
            time.sleep(1)
            set_tags(driver, wait, tags)

        url = publish(driver, wait)
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
