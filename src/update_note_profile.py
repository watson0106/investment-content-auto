"""
note プロフィール自動更新
- 初回のみ（またはPDCA分析で改善が必要な場合）実行
- JS API方式（/api/v1/me）でプロフィールを更新
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv

_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
load_dotenv(os.path.join(_BASE, ".env"))

NOTE_EMAIL    = os.environ["NOTE_EMAIL"]
NOTE_PASSWORD = os.environ["NOTE_PASSWORD"]
PROFILE_STATUS_PATH = os.path.join(_BASE, "data", "profile_status.json")

# ─── プロフィール文 ───────────────────────────────────────────────
PROFILE_TEXT = """投資歴15年の個人投資家。米国株×日本株のハイブリッド戦略で資産運用中。

毎日夕方に「今日のマーケットで私が注目したこと」を無料で配信。ニュースの解説だけでなく、なぜそれが重要かまで書いています。

有料メンバーシップ（月980円・初月無料）では、私が実際に「買った銘柄・見送った銘柄・売った銘柄」とその理由をすべて公開しています。「何を買うか」より「なぜ買わないか」の判断こそが投資で負けない鍵だと思っています。

合わなければすぐ退会できます。まず1ヶ月試してみてください。"""

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


# ─── JS API方式でプロフィール更新 ─────────────────────────────────

def update_profile_with_driver(driver, wait) -> bool:
    """プロフィール設定ページのフォームを操作してプロフィールを更新する。"""
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys
        import platform

        print("  プロフィール設定ページに移動中...")
        driver.get("https://note.com/settings/profile")
        time.sleep(4)

        # プロフィール本文のテキストエリアを探す
        profile_area = None
        for sel in [
            'textarea[name="profile"]',
            'textarea[placeholder*="自己紹介"]',
            'textarea[placeholder*="プロフィール"]',
            '.o-creatorEditForm__profile textarea',
            'textarea',
        ]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                profile_area = els[0]
                print(f"  プロフィールエリア発見: {sel}")
                break

        if not profile_area:
            print("  ❌ プロフィールエリアが見つかりません")
            print(f"  現在URL: {driver.current_url}")
            # フォールバック: API経由で試みる
            return _update_profile_via_api(driver)

        # テキスト入力
        driver.execute_script("arguments[0].click();", profile_area)
        time.sleep(0.5)
        # 全選択して削除
        if platform.system() == "Darwin":
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(driver).key_down(Keys.COMMAND).send_keys('a').key_up(Keys.COMMAND).perform()
        else:
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(driver).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
        time.sleep(0.3)
        profile_area.send_keys(Keys.DELETE)
        time.sleep(0.3)
        profile_area.clear()
        profile_area.send_keys(PROFILE_TEXT)
        time.sleep(1)

        # 保存ボタンをクリック
        saved = driver.execute_script("""
            var btns = Array.from(document.querySelectorAll('button[type="submit"], button'));
            for (var b of btns) {
                var t = (b.textContent || '').trim();
                if (t.includes('保存') || t.includes('更新') || t.includes('変更を保存')) {
                    b.click();
                    return t;
                }
            }
            return null;
        """)

        if saved:
            print(f"  「{saved}」ボタンクリック完了")
            time.sleep(3)
            print("  ✅ プロフィール更新成功（Selenium UI方式）")
            return True
        else:
            print("  ❌ 保存ボタンが見つかりません")
            return _update_profile_via_api(driver)

    except Exception as e:
        print(f"  ❌ Selenium UI更新失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


def _update_profile_via_api(driver) -> bool:
    """APIフォールバック（JS fetch）"""
    try:
        # note.comドメインに遷移（ログイン済み状態）
        print("  note.comドメインに遷移中...")
        driver.get("https://note.com/dashboard")
        time.sleep(3)

        # まず現在のプロフィール情報を取得して確認
        print("  現在のプロフィール情報を取得中...")
        driver.set_script_timeout(20)
        get_result = driver.execute_async_script("""
            var done = arguments[arguments.length - 1];
            fetch('/api/v1/me', {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json',
                    'x-requested-with': 'XMLHttpRequest'
                }
            })
            .then(function(r) {
                return r.text().then(function(t) { done({status: r.status, text: t}); });
            })
            .catch(function(e) { done({error: e.toString()}); });
        """)

        if not get_result or get_result.get("status") not in (200, 201):
            print(f"  [WARN] プロフィール取得失敗 (status={get_result.get('status') if get_result else 'None'})")
            # 取得失敗でも更新は試みる
        else:
            import json as _json
            try:
                me_data = _json.loads(get_result["text"])
                current_nick = me_data.get("data", {}).get("nickname", "不明")
                print(f"  現在のニックネーム: {current_nick}")
            except Exception:
                pass

        # プロフィールを更新（JS API方式）
        print(f"  プロフィール更新中（ニックネーム: {PROFILE_NICKNAME}）...")
        import json as _json
        update_payload = _json.dumps({
            "nickname": PROFILE_NICKNAME,
            "profile": PROFILE_TEXT,
        }, ensure_ascii=False)

        update_result = driver.execute_async_script("""
            var done = arguments[arguments.length - 1];
            var payload = arguments[0];
            fetch('/api/v1/me', {
                method: 'PUT',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'x-requested-with': 'XMLHttpRequest'
                },
                body: payload
            })
            .then(function(r) {
                return r.text().then(function(t) { done({status: r.status, text: t}); });
            })
            .catch(function(e) { done({error: e.toString()}); });
        """, update_payload)

        if update_result and update_result.get("status") in (200, 201):
            print("  プロフィール更新成功（API）")
            return True

        # /api/v1/me が失敗した場合、設定ページ経由のAPIを試す
        print(f"  [WARN] /api/v1/me PUT失敗 (status={update_result.get('status') if update_result else 'None'})")
        print(f"  レスポンス: {str(update_result.get('text', ''))[:300]}")

        # 設定ページに遷移してCSRFトークン付きで再試行
        print("  設定ページ経由で再試行中...")
        driver.get("https://note.com/settings/profile")
        time.sleep(3)

        update_result2 = driver.execute_async_script("""
            var done = arguments[arguments.length - 1];
            var payload = arguments[0];
            var csrfMeta = document.querySelector('meta[name="csrf-token"]');
            var csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
            var headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'x-requested-with': 'XMLHttpRequest'
            };
            if (csrfToken) { headers['x-csrf-token'] = csrfToken; }
            fetch('/api/v1/me', {
                method: 'PUT',
                credentials: 'same-origin',
                headers: headers,
                body: payload
            })
            .then(function(r) {
                return r.text().then(function(t) { done({status: r.status, text: t}); });
            })
            .catch(function(e) { done({error: e.toString()}); });
        """, update_payload)

        if update_result2 and update_result2.get("status") in (200, 201):
            print("  プロフィール更新成功（CSRF付きAPI）")
            return True

        print(f"  [WARN] プロフィール更新失敗 (status={update_result2.get('status') if update_result2 else 'None'})")
        print(f"  レスポンス: {str(update_result2.get('text', ''))[:300]}")
        return False

    except Exception as e:
        print(f"  [WARN] プロフィール更新失敗: {e}")
        return False


def main() -> None:
    print("=== プロフィール更新 ===")

    if not should_update_profile():
        print("  プロフィールは最近更新済み。スキップします")
        if "--force" not in __import__("sys").argv:
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
