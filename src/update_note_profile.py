"""
note プロフィール自動更新
- 初回のみ（またはPDCA分析で改善が必要な場合）実行
- Seleniumでプロフィールページにアクセスして更新
"""
from __future__ import annotations

import json
import os
import time

NOTE_EMAIL    = os.environ["NOTE_EMAIL"]
NOTE_PASSWORD = os.environ["NOTE_PASSWORD"]

_BASE = os.path.join(os.path.dirname(__file__), "..")
PROFILE_STATUS_PATH = os.path.join(_BASE, "data", "profile_status.json")

# ─── プロフィール文 ───────────────────────────────────────────────
PROFILE_TEXT = """投資歴15年の個人投資家。米国株×日本株のハイブリッド戦略で資産運用中。

インデックス投資をベースに、決算・マクロを読んで個別株を上乗せするスタイルです。

毎朝7時に「今日のマーケットで私が注目したこと」を配信。ニュースの解説だけでなく、私自身の判断・ポジション・売買の考え方まで書いています。

週2回の有料記事では、私の実際の売買計画とシナリオ別の行動方針を公開しています（¥500/本）。

「新聞よりも速く、証券会社のレポートよりも人間らしい投資情報を」をモットーに書いています。"""

PROFILE_NICKNAME = "TATSUJIN TRADE"


# ─── 更新チェック ────────────────────────────────────────────────

def should_update_profile() -> bool:
    """未更新 or 30日以上経過していれば True"""
    try:
        with open(PROFILE_STATUS_PATH, encoding="utf-8") as f:
            status = json.load(f)
        from datetime import datetime, timezone, timedelta
        JST = timezone(timedelta(hours=9))
        last = datetime.fromisoformat(status.get("updated_at", "2000-01-01"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=JST)
        return (datetime.now(JST) - last).days >= 30
    except Exception:
        return True  # ファイルがなければ更新する


def mark_profile_updated() -> None:
    from datetime import datetime, timezone, timedelta
    JST = timezone(timedelta(hours=9))
    os.makedirs(os.path.dirname(PROFILE_STATUS_PATH), exist_ok=True)
    with open(PROFILE_STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump({"updated_at": datetime.now(JST).isoformat()}, f)


# ─── Selenium でプロフィール更新 ─────────────────────────────────

def update_profile_with_driver(driver, wait) -> bool:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC

    try:
        print("  プロフィールページを開いています...")
        driver.get("https://note.com/settings/profile")
        time.sleep(3)

        # ニックネーム
        try:
            nick = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'input[name="nickname"], input[placeholder*="ニックネーム"], input[placeholder*="名前"]')
            ))
            driver.execute_script("""
                var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(arguments[0], arguments[1]);
                arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
            """, nick, PROFILE_NICKNAME)
            time.sleep(0.5)
        except Exception as e:
            print(f"  [WARN] ニックネーム設定失敗: {e}")

        # 自己紹介文
        try:
            bio = driver.find_element(By.CSS_SELECTOR,
                'textarea[name="profile"], textarea[placeholder*="自己紹介"], textarea[name="description"]'
            )
            driver.execute_script("""
                var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                setter.call(arguments[0], arguments[1]);
                arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
            """, bio, PROFILE_TEXT)
            time.sleep(0.5)
        except Exception as e:
            print(f"  [WARN] 自己紹介文設定失敗: {e}")

        # 保存ボタン
        try:
            save_btn = driver.find_element(By.XPATH,
                "//button[contains(.,'保存') or contains(.,'更新') or contains(.,'変更')]"
            )
            driver.execute_script("arguments[0].click();", save_btn)
            time.sleep(2)
            print("  プロフィール保存完了")
            return True
        except Exception as e:
            print(f"  [WARN] 保存ボタン見つからず: {e}")
            return False

    except Exception as e:
        print(f"  [WARN] プロフィール更新失敗: {e}")
        return False


def main() -> None:
    print("=== プロフィール更新 ===")

    if not should_update_profile():
        print("  プロフィールは最近更新済み。スキップします")
        return

    import post_to_note
    from selenium.webdriver.support.ui import WebDriverWait

    headless = os.environ.get("HEADLESS", "true").lower() == "true"
    driver = post_to_note.build_driver(headless=headless)
    wait = WebDriverWait(driver, 20)

    try:
        post_to_note.login(driver, wait)
        ok = update_profile_with_driver(driver, wait)
        if ok:
            mark_profile_updated()
            print("  プロフィール更新完了")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
