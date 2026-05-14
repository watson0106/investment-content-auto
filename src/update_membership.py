"""
update_membership.py
noteのメンバーシッププランの説明文を更新するスクリプト。
post_to_note.login()でログイン → メンバーシップ設定ページのUIを操作して説明文を書き換える。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")
sys.path.insert(0, str(Path(__file__).parent))

NOTE_EMAIL    = os.environ["NOTE_EMAIL"]
NOTE_PASSWORD = os.environ["NOTE_PASSWORD"]

# ── 新しいメンバーシップ説明文 ──────────────────────────────────
NEW_DESCRIPTION = """毎週、私が実際に判断した「買った銘柄・見送った銘柄・売った銘柄」とその理由を公開しています。

【メンバーだけが読めるコンテンツ】
・今週注目している銘柄と、そう判断した根拠
・「これは見送り」と決めた銘柄の理由（買わない理由を知ることが一番重要）
・エントリーのタイミングと、どこで損切りするかの考え方
・毎日の投資ニュース解説（有料版・詳細分析つき）

【こんな人に向いています】
・個別株を始めたいけど何を買えばいいかわからない
・ニュースは読んでいるが、自分の投資判断に自信が持てない
・他人の実際の売買判断を見て、自分の考え方と比較したい

月980円、最初の1ヶ月は無料です。
合わなければすぐに退会できます。まず試してみてください。"""


def update_membership_description(headless: bool = True) -> bool:
    """メンバーシップ説明文を更新する。成功したらTrueを返す。"""
    try:
        import post_to_note
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys
        import platform
    except ImportError as e:
        print(f"❌ インポートエラー: {e}")
        return False

    driver = None
    try:
        driver = post_to_note.build_driver(headless=headless)
        wait = WebDriverWait(driver, 20)

        # ── post_to_note の login() を使う（動作実績あり） ──
        post_to_note.login(driver, wait)
        print("  ✅ ログイン完了")

        # ── メンバーシップのプラン編集ページへ直接遷移 ──
        # /membership/info で確認済みの正しいURL
        PLAN_EDIT_URL = "https://note.com/membership/settings/plans/7cc979c536a7/edit"
        print(f"  プラン編集ページへ移動: {PLAN_EDIT_URL}")
        driver.get(PLAN_EDIT_URL)
        time.sleep(4)

        # textareaを探す
        desc_area = None
        textareas = driver.find_elements(By.CSS_SELECTOR, 'textarea')
        if textareas:
            print(f"  textarea {len(textareas)}個を発見 (URL: {driver.current_url})")
            # 説明文らしいtextareaを選ぶ（最も文字数が多いもの）
            desc_area = max(textareas, key=lambda el: len(el.get_attribute('value') or ''))

        if not desc_area:
            # infoページから「編集する」リンクをクリック
            print("  /membership/info から「編集する」リンクを探す...")
            driver.get("https://note.com/kawasewatson0106/membership/info")
            time.sleep(3)
            edit_link = driver.find_element(By.PARTIAL_LINK_TEXT, "編集する")
            if edit_link:
                edit_link.click()
                time.sleep(3)
                textareas = driver.find_elements(By.CSS_SELECTOR, 'textarea')
                if textareas:
                    desc_area = max(textareas, key=lambda el: len(el.get_attribute('value') or ''))

        if not desc_area:
            print(f"  ❌ 説明文エリアが見つかりません (URL: {driver.current_url})")
            print(f"  ページタイトル: {driver.title}")

            # ページ上の全テキストを確認
            body_text = driver.find_element(By.TAG_NAME, 'body').text[:300]
            print(f"  ページテキスト: {body_text}")
            return False

        print(f"  説明文エリア発見。現在の値: {(desc_area.get_attribute('value') or '')[:80]}...")

        # テキスト入力
        driver.execute_script("arguments[0].click();", desc_area)
        time.sleep(0.5)
        desc_area.send_keys(Keys.COMMAND + "a" if platform.system() == "Darwin" else Keys.CONTROL + "a")
        time.sleep(0.3)
        desc_area.send_keys(Keys.DELETE)
        time.sleep(0.3)
        desc_area.clear()
        desc_area.send_keys(NEW_DESCRIPTION)
        time.sleep(1)

        # 保存ボタンをクリック
        saved = driver.execute_script("""
            var btns = Array.from(document.querySelectorAll('button[type="submit"], button'));
            for (var b of btns) {
                var t = (b.textContent || '').trim();
                if (t.includes('保存') || t.includes('更新') || t.includes('変更')) {
                    b.click();
                    return t;
                }
            }
            return null;
        """)
        if saved:
            print(f"  「{saved}」ボタンをクリック")
            time.sleep(3)
            print("  ✅ 説明文更新完了")
            return True
        else:
            print("  ❌ 保存ボタンが見つかりません")
            return False

    except Exception as e:
        print(f"  ❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    print("=== メンバーシップ説明文更新 ===")
    print(f"新しい説明文 ({len(NEW_DESCRIPTION)}文字):")
    print(NEW_DESCRIPTION[:200] + "...")
    print()
    ok = update_membership_description(headless=True)
    if ok:
        print("✅ 完了")
    else:
        print("❌ 自動更新失敗 → 手動で以下を設定してください:")
        print(f"URL: https://note.com/kawasewatson0106/membership")
        print(f"説明文:\n{NEW_DESCRIPTION}")
