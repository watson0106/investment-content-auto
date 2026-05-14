"""
monitor_members.py
noteのメンバーシップ会員数を定期取得して増減をトラッキングする。
- note非公開APIを使って会員数を取得
- data/member_count_log.json に履歴保存
- 増減があればターミナルにアラート

実行: python3 src/monitor_members.py
cron: 毎日8:00に自動実行
"""
from __future__ import annotations

import json
import os
import datetime
import time
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

NOTE_EMAIL = os.environ.get("NOTE_EMAIL", "")
NOTE_PASSWORD = os.environ.get("NOTE_PASSWORD", "")
DATA_FILE = BASE_DIR / "data" / "member_count_log.json"
JST = datetime.timezone(datetime.timedelta(hours=9))

NOTE_USER = "kawasewatson0106"
MEMBERSHIP_URL = f"https://note.com/{NOTE_USER}/membership"


def get_member_count_via_api() -> int | None:
    """note API経由でメンバーシップの会員数を取得する。"""
    import requests

    # まずログインしてセッションを取得
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Referer": "https://note.com/",
    })

    # CSRF tokenを取得
    try:
        r = session.get("https://note.com/", timeout=10)
        csrf = None
        for line in r.text.split("\n"):
            if "csrf-token" in line and "content=" in line:
                import re
                m = re.search(r'content="([^"]+)"', line)
                if m:
                    csrf = m.group(1)
                    break
    except Exception:
        pass

    # ログイン
    try:
        login_data = {"login": NOTE_EMAIL, "password": NOTE_PASSWORD}
        headers = {}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        r = session.post(
            "https://note.com/api/v1/sessions",
            json=login_data,
            headers=headers,
            timeout=15
        )
        if r.status_code not in (200, 201):
            print(f"  ログイン失敗: {r.status_code}")
            return None
        print("  ログイン成功")
    except Exception as e:
        print(f"  ログインエラー: {e}")
        return None

    # 会員数取得（複数エンドポイントを試す）
    endpoints = [
        f"https://note.com/api/v1/circles/{NOTE_USER}",
        f"https://note.com/api/v2/creators/{NOTE_USER}/circles",
        f"https://note.com/api/v1/creators/{NOTE_USER}",
        f"https://note.com/api/v2/users/{NOTE_USER}",
    ]

    for url in endpoints:
        try:
            r = session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                print(f"  {url}: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                # 会員数を探す
                for key in ["member_count", "memberCount", "members_count",
                            "circle_member_count", "subscriber_count"]:
                    val = _deep_get(data, key)
                    if val is not None:
                        print(f"  会員数発見 ({key}): {val}")
                        return int(val)
            else:
                print(f"  {url}: {r.status_code}")
        except Exception as e:
            print(f"  {url} エラー: {e}")

    # creators APIから探す
    try:
        r = session.get(f"https://note.com/api/v2/creators/{NOTE_USER}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            # hasCircle等を確認
            print(f"  creators API keys: {list(data.get('data', {}).keys())}")
    except Exception:
        pass

    return None


def _deep_get(obj, key: str):
    """ネストされたdictから特定キーを再帰的に取得する。"""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            result = _deep_get(v, key)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _deep_get(item, key)
            if result is not None:
                return result
    return None


def get_member_count_via_selenium() -> int | None:
    """Seleniumでメンバーシップページを開き会員数を取得する。"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        print("  selenium 未インストール")
        return None

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 20)

        # ログイン（post_to_note.pyと同じ方式）
        import sys
        sys.path.insert(0, str(BASE_DIR / "src"))
        from post_to_note import login as _login
        _login(driver, wait)

        # メンバーシップページを取得
        driver.get(MEMBERSHIP_URL)
        time.sleep(4)

        # 会員数を示すテキストを探す
        count = driver.execute_script("""
            var allText = document.body.innerText;
            var patterns = [
                /([0-9]+)人のメンバー/,
                /メンバー\\s*([0-9]+)\\s*人/,
                /([0-9]+)\\s*人が参加/,
                /([0-9]+)\\s*subscribers/i,
                /([0-9]+)\\s*members/i,
            ];
            for (var p of patterns) {
                var m = allText.match(p);
                if (m) return parseInt(m[1]);
            }
            return null;
        """)

        if count is not None:
            print(f"  会員数取得: {count}人")
            return count

        # ページソースも確認
        page_source = driver.page_source
        import re
        for pattern in [r'"member_count":(\d+)', r'"memberCount":(\d+)', r'(\d+)人のメンバー']:
            m = re.search(pattern, page_source)
            if m:
                print(f"  会員数（ソース）: {m.group(1)}人")
                return int(m.group(1))

        print(f"  会員数を特定できませんでした。URL: {driver.current_url}")
        print("  ページテキスト（最初の500字）:", driver.find_element(By.TAG_NAME, "body").text[:500])
        return None

    except Exception as e:
        print(f"  エラー: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def load_log() -> list[dict]:
    if DATA_FILE.exists():
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_log(log: list[dict]):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def check_and_log():
    """会員数を取得して増減をチェック・ログ保存する。"""
    print("=== メンバーシップ会員数チェック ===")
    now = datetime.datetime.now(JST)

    # まずAPI経由を試みる
    count = get_member_count_via_api()

    if count is None:
        print("  API取得失敗 → Selenium試行...")
        count = get_member_count_via_selenium()

    log = load_log()

    if count is not None:
        entry = {
            "timestamp": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "count": count,
        }
        log.append(entry)
        save_log(log)

        # 増減チェック
        if len(log) >= 2:
            prev = log[-2]["count"]
            diff = count - prev
            if diff > 0:
                print(f"  🎉 会員数増加！ {prev} → {count} (+{diff}人)")
            elif diff < 0:
                print(f"  ⚠️ 会員数減少: {prev} → {count} ({diff}人)")
            else:
                print(f"  → 変化なし: {count}人")
        else:
            print(f"  初回記録: {count}人")
    else:
        print("  会員数を取得できませんでした。手動確認が必要です。")
        print(f"  URL: {MEMBERSHIP_URL}")

    # サマリー表示
    if log and all(isinstance(e.get("count"), int) for e in log):
        print("\n=== 会員数推移 ===")
        for entry in log[-7:]:
            print(f"  {entry['date']}: {entry['count']}人")
        if len(log) >= 2:
            first = log[0]["count"]
            last = log[-1]["count"]
            print(f"  合計増加: {last - first}人 ({log[0]['date']} 〜 {log[-1]['date']})")
    else:
        print("\n=== 会員数確認 ===")
        print(f"  手動確認URL: {MEMBERSHIP_URL}")
        print("  note.com の「メンバーシップ管理」ページで会員数を確認してください。")

    return count


if __name__ == "__main__":
    check_and_log()
