"""
マガジン自動管理
- 投稿済み高スキ記事をマガジンに自動追加
- マガジン説明文・価格をAPIで更新
- 毎日パイプライン実行後に自動で動く
"""
from __future__ import annotations

import json
import os
import re
import time

NOTE_EMAIL    = os.environ["NOTE_EMAIL"]
NOTE_PASSWORD = os.environ["NOTE_PASSWORD"]

_BASE = os.path.join(os.path.dirname(__file__), "..")
MAGAZINE_STATUS_PATH = os.path.join(_BASE, "data", "magazine_status.json")

# マガジン設定
MAGAZINE_ID          = None   # 初回実行時に自動取得・保存
MAGAZINE_DESCRIPTION = """毎週火・金曜日更新。個人投資家「私」の実際の売買判断を公開するマガジンです。

【収録内容】
・私が実際に取ったポジションと根拠
・楽観・中立・悲観の3シナリオ別の行動計画
・今週中に確認すべき具体的チェックリスト
・週次の私のポートフォリオ状況

「何を買うか」より「私がなぜそう判断したか」を重視した内容です。"""

# 自動追加する最低スキ数の閾値
AUTO_ADD_LIKES_THRESHOLD = 5


def _load_status() -> dict:
    try:
        with open(MAGAZINE_STATUS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"magazine_id": None, "added_note_keys": []}


def _save_status(status: dict) -> None:
    os.makedirs(os.path.dirname(MAGAZINE_STATUS_PATH), exist_ok=True)
    with open(MAGAZINE_STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def get_magazine_id_via_api(driver) -> str | None:
    """note APIでマガジンIDを取得"""
    driver.set_script_timeout(15)
    result = driver.execute_async_script("""
        var done = arguments[arguments.length - 1];
        fetch('/api/v1/me/magazines', {
            credentials: 'same-origin',
            headers: {'x-requested-with': 'XMLHttpRequest'}
        })
        .then(r => r.json().then(d => done({status: r.status, data: d})))
        .catch(e => done({error: e.toString()}));
    """)
    if result and result.get("status") == 200:
        magazines = result.get("data", {}).get("data", {}).get("magazines", [])
        if magazines:
            mag = magazines[0]
            mag_id = mag.get("id") or mag.get("key")
            print(f"  マガジン取得: id={mag_id} name={mag.get('name','')}")
            return str(mag_id)
    print(f"  [WARN] マガジンID取得失敗: {result}")
    return None


def add_note_to_magazine(driver, magazine_id: str, note_key: str) -> bool:
    """note APIで記事をマガジンに追加"""
    driver.set_script_timeout(15)
    result = driver.execute_async_script(f"""
        var done = arguments[arguments.length - 1];
        fetch('/api/v1/magazines/{magazine_id}/notes', {{
            method: 'POST',
            credentials: 'same-origin',
            headers: {{
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'x-requested-with': 'XMLHttpRequest'
            }},
            body: JSON.stringify({{key: '{note_key}'}})
        }})
        .then(r => r.json().then(d => done({{status: r.status, data: d}})))
        .catch(e => done({{error: e.toString()}}));
    """)
    if result and result.get("status") in (200, 201):
        return True
    print(f"  [WARN] マガジン追加失敗 ({note_key}): status={result.get('status') if result else 'None'}")
    return False


def update_magazine_description(driver, magazine_id: str) -> bool:
    """マガジン説明文を更新"""
    import json as _json
    driver.set_script_timeout(15)
    result = driver.execute_async_script(f"""
        var done = arguments[arguments.length - 1];
        fetch('/api/v1/magazines/{magazine_id}', {{
            method: 'PUT',
            credentials: 'same-origin',
            headers: {{
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'x-requested-with': 'XMLHttpRequest'
            }},
            body: JSON.stringify({{
                description: {_json.dumps(MAGAZINE_DESCRIPTION)}
            }})
        }})
        .then(r => r.json().then(d => done({{status: r.status}})))
        .catch(e => done({{error: e.toString()}}));
    """)
    if result and result.get("status") in (200, 201):
        print("  マガジン説明文更新完了")
        return True
    return False


def auto_add_high_like_articles(driver, magazine_id: str, status: dict) -> int:
    """スキ閾値以上の記事をマガジンに自動追加"""
    from pdca_tracker import load_performance
    perf = load_performance()
    added_keys = set(status.get("added_note_keys", []))
    added_count = 0

    # スキ数が閾値以上 かつ 未追加 かつ 無料記事
    targets = [
        p for p in perf
        if p.get("latest_likes", 0) >= AUTO_ADD_LIKES_THRESHOLD
        and p["note_key"] not in added_keys
        and not p.get("is_paid", False)
    ]
    # スキ数順でソート
    targets.sort(key=lambda x: x["latest_likes"], reverse=True)

    for entry in targets[:10]:  # 1回あたり最大10本
        note_key = entry["note_key"]
        likes = entry["latest_likes"]
        title = entry["title"][:40]
        if add_note_to_magazine(driver, magazine_id, note_key):
            added_keys.add(note_key)
            added_count += 1
            print(f"  ✓ マガジン追加: {title} ({likes}スキ)")
            time.sleep(0.5)

    status["added_note_keys"] = list(added_keys)
    return added_count


def main() -> None:
    print("=== マガジン自動管理 ===")
    import post_to_note
    from selenium.webdriver.support.ui import WebDriverWait

    status = _load_status()
    headless = os.environ.get("HEADLESS", "true").lower() == "true"
    driver = post_to_note.build_driver(headless=headless)
    wait = WebDriverWait(driver, 20)

    try:
        # note.comにログイン
        post_to_note.login(driver, wait)
        driver.get("https://note.com/")
        time.sleep(2)

        # マガジンIDを取得（キャッシュあれば使う）
        magazine_id = status.get("magazine_id")
        if not magazine_id:
            magazine_id = get_magazine_id_via_api(driver)
            if magazine_id:
                status["magazine_id"] = magazine_id
                _save_status(status)

        if not magazine_id:
            print("  [WARN] マガジンIDが取得できませんでした")
            return

        # 説明文を更新（初回のみ）
        if not status.get("description_updated"):
            ok = update_magazine_description(driver, magazine_id)
            if ok:
                status["description_updated"] = True

        # 高スキ記事を自動追加
        added = auto_add_high_like_articles(driver, magazine_id, status)
        print(f"  マガジン追加完了: {added}本追加")

        _save_status(status)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
