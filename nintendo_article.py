"""
investment-content-auto パイプラインで Nintendo/Switch 2 記事を生成・投稿するスクリプト
"""
import json
import os
import sys
import subprocess
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR  = os.path.join(BASE_DIR, "src")
sys.path.insert(0, SRC_DIR)
os.chdir(BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

import deep_research
import main as pipeline_main

# ─── Nintendo ニュースアイテム ─────────────────────────────────────────────
NINTENDO_NEWS = {
    "title": "Nintendo Switch 2 Sells 5.15 Million Units in Japan—All-Time High Stock Price of ¥11,855 as 2.2 Million Apply for First Lottery—May 8 Earnings Report Is the Key Catalyst",
    "source": "日本経済新聞 / Nintendo IR",
    "url": "https://www.nikkei.com/article/DGXZQOUF302YL0Q5A430C2000000/",
    "published": "2026-04-30T09:00:00Z",
    "summary": (
        "Nintendo Switch 2 launched June 5, 2025 at ¥69,980 in Japan. It sold 3.5 million units "
        "worldwide in the first 4 days—the fastest-selling Nintendo console ever. In Japan alone, "
        "sales reached 5.15 million units through March 2026 (vs. Switch 1's 3.32 million in "
        "the same period). The first domestic lottery received 2.2 million applications, "
        "far exceeding expectations. Nintendo's stock hit an all-time high of ¥11,855 on "
        "April 30, 2026 (+4% in a day), driven by the lottery news. "
        "However, a critical paradox looms: despite record sales, Nintendo maintained its full-year "
        "earnings forecast without upgrading, triggering a -12.6% single-day drop in February 2026. "
        "The reason: the ¥69,980 domestic price is not profitable due to soaring NAND flash and "
        "LPDDR5 memory chip costs (DRAM price up ~40% YoY). Nintendo earns more on overseas sales "
        "(US price $449.99), but US tariff risk on Vietnam manufacturing weighs on the outlook. "
        "FY2026 guidance: revenue ¥2.25 trillion (+93% YoY), operating profit ¥370 billion (+31%). "
        "The May 8, 2026 full-year earnings announcement is the make-or-break catalyst. "
        "Key watchpoints: FY2027 unit sales guidance, software attach rate, and any comment on "
        "whether domestic hardware profitability will recover as chip prices stabilize. "
        "President Furukawa needs to show a credible roadmap from 'loss on hardware' to "
        "'profit via software ecosystem.' The stock is pricing in optimism—if guidance disappoints, "
        "another sharp selloff is possible."
    ),
}

ARTICLE_NUM = 1
ARTICLE_JSON_PATH = os.path.join(BASE_DIR, f"output/article_{ARTICLE_NUM}.json")


def generate_article():
    print("=" * 50)
    print("Nintendo / Switch 2 記事生成 開始")
    print("=" * 50)

    os.makedirs("output", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)

    print("\n記事執筆中（_write_article）...")
    result = deep_research._write_article(NINTENDO_NEWS, ARTICLE_NUM)

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

    os.system("pkill -f 'undetected_chromedriver|chromedriver' 2>/dev/null; sleep 3")

    url = post_to_note()
    print(f"\n✅ 完了: {url}")
