"""
investment-content-auto パイプラインで Mythos 記事を生成・投稿するスクリプト
write_news_section() を直接呼んでフォーマット・画像生成を完全に再現する
"""
import json
import os
import sys
import subprocess
import traceback

# investment-content-auto の src を参照
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR  = os.path.join(BASE_DIR, "src")
sys.path.insert(0, SRC_DIR)
os.chdir(BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

import deep_research
import main as pipeline_main

# ─── Mythos ニュースアイテム ───────────────────────────────────────────────
MYTHOS_NEWS = {
    "title": "Anthropic's 'Mythos' AI Can Automatically Find and Exploit Zero-Day Vulnerabilities—Cybersecurity Stocks Surge as Demand Explodes",
    "source": "TechCrunch / Bloomberg / Fortune",
    "url": "https://techcrunch.com/2026/04/07/anthropic-mythos-ai-model-preview-security/",
    "published": "2026-04-07T09:00:00Z",
    "summary": (
        "Anthropic announced 'Claude Mythos' on April 7, 2026—an AI model capable of "
        "automatically discovering zero-day vulnerabilities across major OSes and browsers, "
        "then generating working exploit code. Engineers with no security training used it "
        "overnight to produce complete exploits. Anthropic launched Project Glasswing with "
        "Amazon, Apple, Microsoft, CrowdStrike, and Palo Alto Networks to use Mythos defensively. "
        "However, Bloomberg reported unauthorized access on April 21. The Trump administration "
        "is blocking expansion, and the Pentagon keeps Anthropic on its supply chain risk "
        "blacklist. Anthropic's IPO is planned for October 2026 at over $60 billion valuation. "
        "Japanese financial regulators warned institutions to urgently review their defenses. "
        "CrowdStrike (CRWD) and Palo Alto Networks (PANW) saw increased investor interest. "
        "In Japan, GlobalSecurityExpert (4417) surged on May 1 on strong earnings outlook. "
        "Separately, software stocks like PLTR and MSFT fell on 'Anthropic Shock' AI-replacement fears."
    ),
}

ARTICLE_NUM = 1
ARTICLE_JSON_PATH = os.path.join(BASE_DIR, f"output/article_{ARTICLE_NUM}.json")


def generate_article():
    print("=" * 50)
    print("Mythos 記事生成 開始")
    print("=" * 50)

    os.makedirs("output", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)

    # _write_article はタイトル生成・サムネイル・X告知ポスト・article_1.json保存まで一括で行う
    print("\n記事執筆中（_write_article）...")
    result = deep_research._write_article(MYTHOS_NEWS, ARTICLE_NUM)

    print(f"\nタイトル: {result['title']}")
    print(f"本文文字数: {len(result['article'])}文字")
    print(f"画像数: {len(result.get('image_paths', []))}枚")

    return result


def run_stock_analysis(article: dict):
    print("\n" + "─" * 40)
    print("  株式短期分析（有料note）")
    print("─" * 40)

    if article.get("skip_stock"):
        print("  [SKIP] skip_stock=True")
        return

    sa_main = os.path.expanduser("~/stock-analysis-auto/src/main.py")
    if not os.path.exists(sa_main):
        print("  [SKIP] ~/stock-analysis-auto が見つかりません")
        return

    sa_env = {k: v for k, v in os.environ.items()
              if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
    sa_env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + sa_env.get("PATH", "/usr/bin:/bin")
    sa_env["PYTHONUNBUFFERED"] = "1"

    result = subprocess.run(
        ["/usr/bin/python3", sa_main, "--article", ARTICLE_JSON_PATH],
        env=sa_env,
        cwd=os.path.expanduser("~/stock-analysis-auto/src"),
        timeout=1800,
    )
    if result.returncode != 0:
        print(f"  [WARN] 非ゼロ終了 (code={result.returncode})")
    else:
        print("  [OK] 株式短期分析 完了")


def post_to_note():
    print("\n" + "─" * 40)
    print("  note 下書き保存")
    print("─" * 40)
    r = pipeline_main.mode_post(ARTICLE_NUM)
    return r


if __name__ == "__main__":
    article = generate_article()
    try:
        run_stock_analysis(article)
    except subprocess.TimeoutExpired:
        print("  [WARN] 株式短期分析タイムアウト")
    except Exception:
        print("  [WARN] 株式短期分析失敗（無料記事は継続）")
        traceback.print_exc()

    # chromedriver 競合防止
    os.system("pkill -f 'undetected_chromedriver|chromedriver' 2>/dev/null; sleep 3")

    url = post_to_note()
    print(f"\n✅ 完了: {url}")
