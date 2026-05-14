#!/usr/bin/env python3
"""
note.com セッション保存ツール（手動実行・一度だけ）
使い方: python3 src/save_note_session.py
ブラウザが開くので note.com にログインし、ログイン後に Enter を押す。
"""
import os, sys, pickle, time
sys.path.insert(0, os.path.dirname(__file__))

from selenium import webdriver as _wd
from selenium.webdriver.chrome.options import Options as _Opts
from selenium.webdriver.chrome.service import Service as _Svc
from webdriver_manager.chrome import ChromeDriverManager as _CDM

SESSION_PATH = os.path.expanduser("~/.note_session.pkl")


def save_session():
    options = _Opts()
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # headless=False で実際のブラウザを開く
    service = _Svc(_CDM().install())
    driver = _wd.Chrome(service=service, options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    print("ブラウザを開いています...")
    driver.get("https://note.com/login")
    print("\n" + "="*50)
    print("note.com のログインページが開きました。")
    print("メールアドレスとパスワードでログインしてください。")
    print("ログイン完了を自動検知します（最大120秒待機）...")
    print("="*50)

    # ログイン完了を自動検知（ログインページを離れるまで待つ）
    for i in range(120):
        time.sleep(1)
        current_url = driver.current_url
        if "login" not in current_url and "note.com" in current_url:
            print(f"  ログイン完了を検知: {current_url}")
            break
        if i % 10 == 9:
            print(f"  待機中... {i+1}秒 / 120秒")
    else:
        print("[WARNING] タイムアウト。現在のURLでセッションを保存します。")

    time.sleep(2)

    cookies = driver.get_cookies()
    cookie_names = [c["name"] for c in cookies]
    print(f"\nCookies 取得: {cookie_names}")

    if "_note_session_v5" not in cookie_names and "note_gql_auth_token" not in cookie_names:
        print("[ERROR] セッションクッキーが見つかりません。ログインできていない可能性があります。")
        driver.quit()
        return False

    # 保存
    with open(SESSION_PATH, "wb") as f:
        pickle.dump(cookies, f)
    print(f"\n✅ セッション保存完了: {SESSION_PATH}")
    print(f"   有効なクッキー: {len(cookies)} 件")
    driver.quit()
    return True


if __name__ == "__main__":
    save_session()
