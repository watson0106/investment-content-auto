"""
note 管理画面に Selenium でアクセスして以下を取得・保存:
  1. メンバーシップ加入者数
  2. 直近10記事のスキ数・PV
  3. プロフィール現在の状態
  4. 各画面のスクリーンショット (output/note_inspect/)

使い方:
  python inspect_note_dashboard.py
"""
from __future__ import annotations

import json
import os
import time
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "src"))

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from post_to_note import build_driver

OUTPUT_DIR = ROOT / "output" / "note_inspect"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

NOTE_EMAIL = os.environ["NOTE_EMAIL"]
NOTE_PASSWORD = os.environ["NOTE_PASSWORD"]


def save_screenshot(driver, name: str):
    path = OUTPUT_DIR / f"{name}_{datetime.now().strftime('%H%M%S')}.png"
    driver.save_screenshot(str(path))
    return path


def form_login(driver, wait):
    """フォーム式ログイン（API式は失敗を検出できないため）"""
    print("  ログインページを開く...")
    driver.get("https://note.com/login")
    time.sleep(3)

    print("  メール入力...")
    email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
    driver.execute_script("""
        var el = arguments[0];
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, arguments[1]);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    """, email_field, NOTE_EMAIL)
    time.sleep(1)

    print("  パスワード入力...")
    pw_field = driver.find_element(By.ID, "password")
    driver.execute_script("""
        var el = arguments[0];
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, arguments[1]);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    """, pw_field, NOTE_PASSWORD)
    time.sleep(1)

    print("  ログインボタン押下...")
    try:
        login_btn = driver.find_element(
            By.XPATH,
            "//button[contains(.,'ログイン') and not(contains(.,'Google')) and not(contains(.,'Apple')) and not(contains(.,'X'))]"
        )
        driver.execute_script("arguments[0].click();", login_btn)
    except Exception:
        pw_field.send_keys(Keys.RETURN)

    # ログイン完了を待つ
    for i in range(25):
        time.sleep(1)
        cur = driver.current_url
        if "login" not in cur:
            print(f"  ログイン完了（{cur}）")
            return True
    print(f"  ログイン未完了。現在URL: {driver.current_url}")
    return False


def is_logged_in(driver) -> bool:
    """ヘッダに「アカウント」アイコンがあるかでログイン状態を判定"""
    try:
        # ログイン後のヘッダには .o-headerAvatarUser や img.avatar が出る。
        # 一方ログアウト中は「ログイン」「会員登録」ボタンが出る。
        page_text = driver.execute_script("return document.body.innerText.slice(0, 800);")
        if "会員登録" in page_text and "ログイン" in page_text:
            return False
        return True
    except Exception:
        return False


def inspect():
    print("=== note 管理画面 検査開始 ===")
    headless = os.environ.get("HEADLESS", "false").lower() == "true"
    print(f"  headless: {headless}")

    driver = build_driver(headless=headless)
    wait = WebDriverWait(driver, 20)

    findings = {"timestamp": datetime.now().isoformat()}

    try:
        # ── ログイン ──
        print("\n[1/5] フォームログイン...")
        form_login(driver, wait)
        time.sleep(2)
        save_screenshot(driver, "01_after_login")
        findings["logged_in_after_login"] = is_logged_in(driver)
        print(f"  ログイン状態: {findings['logged_in_after_login']}")

        # ── 自分のプロフィールページ ──
        print("\n[2/5] 自分のプロフィール...")
        driver.get("https://note.com/kawasewatson0106")
        time.sleep(5)
        save_screenshot(driver, "02_my_profile")
        findings["logged_in_at_profile"] = is_logged_in(driver)

        # プロフィール文取得
        try:
            profile_text = driver.execute_script("""
                var sels = ['[class*="profileText"]', '[class*="o-userIntroduction"]',
                           '[class*="description"]', 'p[class*="intro"]'];
                for (var i=0; i<sels.length; i++) {
                    var el = document.querySelector(sels[i]);
                    if (el && el.innerText.length > 20) return el.innerText;
                }
                return '';
            """)
            findings["profile_description"] = profile_text[:500]
            print(f"  プロフィール文: {profile_text[:120]}...")
        except Exception as e:
            findings["profile_description_error"] = str(e)

        # フォロワー数
        try:
            follower_text = driver.execute_script("""
                var t = document.body.innerText;
                var m = t.match(/フォロワー\\s*[:\\s]*\\s*([0-9,]+)/);
                return m ? m[1] : '';
            """)
            findings["follower_count"] = follower_text
            print(f"  フォロワー数: {follower_text}")
        except Exception:
            pass

        # 直近記事リスト＋スキ数
        try:
            articles = driver.execute_script("""
                var cards = document.querySelectorAll('article, [class*="m-largeNoteWrapper"], a[href*="/n/"]');
                var seen = new Set();
                var out = [];
                cards.forEach(function(c) {
                    var t = c.innerText.trim();
                    if (t && t.length > 20 && !seen.has(t.slice(0, 80))) {
                        seen.add(t.slice(0, 80));
                        out.push(t.slice(0, 300));
                    }
                });
                return out.slice(0, 15);
            """)
            findings["recent_articles_with_likes"] = articles
            print(f"  記事カード {len(articles)} 件取得")
        except Exception as e:
            findings["articles_error"] = str(e)

        # ── アクセス解析ページを探す ──
        print("\n[3/5] アクセス解析...")
        # 設定メニューから入る方が確実
        analytics_urls = [
            "https://note.com/sitesettings/stats",
            "https://note.com/sitesettings/analytics",
            "https://note.com/notes",  # 自分の記事一覧（編集者ビュー）
        ]
        for url in analytics_urls:
            driver.get(url)
            time.sleep(4)
            cur = driver.current_url
            print(f"  {url} → {cur}")
            if "login" in cur:
                continue
            save_screenshot(driver, f"03_analytics_{analytics_urls.index(url)}")
            text = driver.execute_script("return document.body.innerText.slice(0, 4000);")
            if any(k in text for k in ["PV", "ビュー数", "スキ数", "閲覧数", "全体ビュー"]):
                findings["analytics_url"] = cur
                findings["analytics_text"] = text[:3000]
                print(f"  解析ページ検出: {cur}")
                break

        # ── メンバーシップ管理 ──
        print("\n[4/5] メンバーシップ加入者数...")
        membership_urls = [
            "https://note.com/sitesettings/membership",
            "https://note.com/membership/dashboard",
            "https://note.com/circles",
            "https://note.com/kawasewatson0106/membership",
        ]
        for url in membership_urls:
            driver.get(url)
            time.sleep(5)
            cur = driver.current_url
            print(f"  {url} → {cur}")
            if "login" in cur or "404" in cur:
                continue
            save_screenshot(driver, f"04_membership_{membership_urls.index(url)}")
            text = driver.execute_script("return document.body.innerText.slice(0, 5000);")
            # 加入者・メンバー数を探す
            import re
            patterns = [
                r"メンバー(?:数)?[\s:：]*([0-9,]+)\s*人",
                r"加入者[\s:：]*([0-9,]+)\s*人",
                r"登録者[\s:：]*([0-9,]+)\s*人",
                r"([0-9]+)\s*人(?:のメンバー|が登録|が参加)",
            ]
            for pat in patterns:
                m = re.search(pat, text)
                if m:
                    findings["membership_count"] = m.group(1)
                    findings["membership_pattern_matched"] = pat
                    findings["membership_page_url"] = cur
                    print(f"  メンバー数検出: {m.group(1)}人")
                    break
            findings.setdefault("membership_page_texts", {})[cur] = text[:2000]
            if "membership_count" in findings:
                break

        # ── ダッシュボード（クリエイター向け） ──
        print("\n[5/5] クリエイターダッシュボード...")
        for url in ["https://note.com/sitesettings/dashboard", "https://note.com/sitesettings/profile"]:
            driver.get(url)
            time.sleep(4)
            cur = driver.current_url
            save_screenshot(driver, f"05_creator_{['dashboard','profile'].index(url.split('/')[-1])}")
            text = driver.execute_script("return document.body.innerText.slice(0, 5000);")
            findings[f"page_{url.split('/')[-1]}"] = text[:2500]

    except Exception as e:
        import traceback
        findings["exception"] = traceback.format_exc()
        print(f"\n例外: {e}")

    finally:
        with open(OUTPUT_DIR / "findings.json", "w", encoding="utf-8") as f:
            json.dump(findings, f, ensure_ascii=False, indent=2)
        print(f"\n保存: {OUTPUT_DIR / 'findings.json'}")
        print(f"スクリーンショット: {OUTPUT_DIR}")
        time.sleep(2)
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    inspect()
