"""
note プロフィール自動更新
- 初回のみ（またはPDCA分析で改善が必要な場合）実行
- JS API方式（/api/v1/me）でプロフィールを更新
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


# ─── JS API方式でプロフィール更新 ─────────────────────────────────

def update_profile_with_driver(driver, wait) -> bool:
    """JS API方式でプロフィールを更新する。
    note.comドメインにいる状態で /api/v1/me へPUTリクエストを送る。
    """
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
