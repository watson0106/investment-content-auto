#!/usr/bin/env python3
"""
note.comアカウント収益化分析レポートをGoogle Docsに作成する
"""
import os, sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES           = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = os.path.expanduser("~/kindle_extract/credentials.json")
TOKEN_FILE       = os.path.expanduser("~/kindle_extract/token.json")


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    return creds


def insert_requests(content_lines):
    """
    content_lines: list of (text, style)
      style: "title" | "heading1" | "heading2" | "heading3" | "normal" | "bullet" | "bold_normal"
    Returns: list of batchUpdate requests
    """
    requests = []
    index = 1  # 先頭はドキュメントの既存改行

    for text, style in content_lines:
        full_text = text + "\n"
        length = len(full_text)

        requests.append({
            "insertText": {
                "location": {"index": index},
                "text": full_text
            }
        })

        if style == "title":
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + length},
                    "paragraphStyle": {"namedStyleType": "TITLE"},
                    "fields": "namedStyleType"
                }
            })
        elif style == "heading1":
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + length},
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "fields": "namedStyleType"
                }
            })
        elif style == "heading2":
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + length},
                    "paragraphStyle": {"namedStyleType": "HEADING_2"},
                    "fields": "namedStyleType"
                }
            })
        elif style == "heading3":
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + length},
                    "paragraphStyle": {"namedStyleType": "HEADING_3"},
                    "fields": "namedStyleType"
                }
            })
        elif style == "bullet":
            requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": index, "endIndex": index + length},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
                }
            })
        elif style == "bold_normal":
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + length - 1},
                    "textStyle": {"bold": True},
                    "fields": "bold"
                }
            })

        index += length

    return requests


def main():
    creds = get_credentials()
    docs_service = build('docs', 'v1', credentials=creds)

    # ドキュメント作成
    doc = docs_service.documents().create(
        body={"title": "note.com収益化分析レポート｜TATSUJIN TRADE"}
    ).execute()
    doc_id = doc["documentId"]
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"ドキュメント作成: {doc_url}")

    # ─── コンテンツ定義 ───────────────────────────────
    content = [
        ("note.com 収益化分析レポート", "title"),
        ("TATSUJIN TRADE（kawasewatson0106）　2026年3月25日作成", "normal"),
        ("", "normal"),

        # ========== 1. アカウント現状 ==========
        ("1｜アカウント現状サマリー", "heading1"),
        ("", "normal"),
        ("基本データ", "heading2"),
        ("フォロワー数：191人", "bullet"),
        ("フォロー数：7人", "bullet"),
        ("総記事数：107本（全て無料）", "bullet"),
        ("マガジン数：1冊　「デイトレで月10万円稼ぐためのマガジン」¥19,800（8記事収録）", "bullet"),
        ("メンバーシップ：なし", "bullet"),
        ("有料記事：0本", "bullet"),
        ("Twitterアカウント：@VAKERSTREET", "bullet"),
        ("", "normal"),
        ("エンゲージメント分析", "heading2"),
        ("平均スキ数：約3〜4スキ（107本の分析より）", "bullet"),
        ("最高スキ数：11スキ（「S&P500グレート・ローテーション」記事・2026年1月）", "bullet"),
        ("最近の推移（直近5記事の平均）：約3スキ", "bullet"),
        ("コメント：ほぼなし", "bullet"),
        ("", "normal"),
        ("記事傾向", "heading2"),
        ("毎日投稿：AI自動生成による投資ニュース速報（「新聞よりわかりやすくて早い〜」）", "bullet"),
        ("手書き深掘り記事：週1〜2本（個別銘柄分析・テーマ投資）", "bullet"),
        ("テーマ：日米株式・ETF・個別銘柄・ポートフォリオ戦略", "bullet"),
        ("", "normal"),

        # ========== 2. 収益化できていない7つの理由 ==========
        ("2｜収益化できていない7つの理由", "heading1"),
        ("", "normal"),

        ("① フォロワー数が少なすぎる（191人）", "heading2"),
        ("有料コンテンツの購買率は一般的にフォロワーの1〜3%。191人では購入者は0〜5人にとどまる。", "normal"),
        ("note収益化で月1万円を目指すには最低500〜1,000人のフォロワーが目安。", "normal"),
        ("現在のフォロワー増加ペースが遅い（毎日投稿しているにもかかわらず）。", "bullet"),
        ("Twitterとnoteの相互送客が機能していない可能性。", "bullet"),
        ("", "normal"),

        ("② エンゲージメントが極めて低い（平均3〜4スキ）", "heading2"),
        ("107本の記事で平均スキ3〜4は、読者との関係構築ができていないことを示す。", "normal"),
        ("エンゲージメントが低いと、有料記事を買ってもらえる信頼関係が築けない。", "normal"),
        ("AI自動生成コンテンツはテキストが均質で「誰が書いたか」が伝わらない。", "bullet"),
        ("読者への問いかけ・コメント欄の活用がない。", "bullet"),
        ("Twitterでnote記事のシェアが少ない（または反応が薄い）。", "bullet"),
        ("", "normal"),

        ("③ 107本の記事が全て無料（収益ゼロ）", "heading2"),
        ("現在の収益：¥0（マガジンの購入者数は不明だが、フォロワー数から推測すると極少）。", "normal"),
        ("「まず無料でファンを増やしてから有料化」は一見正しいが、無料コンテンツが多すぎると有料への移行が難しくなる。", "normal"),
        ("有料記事を1本も出していないため、読者が「購入する」という行動を取る接点がない。", "bullet"),
        ("マガジン¥19,800は価格帯が高く（投資系noteの相場は月額¥500〜¥2,000）、購入ハードルが高い。", "bullet"),
        ("", "normal"),

        ("④ AI自動生成コンテンツの「人格の希薄さ」", "heading2"),
        ("毎日の速報記事はタイトルが画一的（「新聞よりわかりやすくて早い〜」シリーズ）。", "normal"),
        ("読者にとって「この人だから読む」という理由がない。AI感が透けると信頼性が低下する。", "normal"),
        ("個人の実体験・失敗談・具体的なポートフォリオ公開など「人間性」が見えるコンテンツがない。", "bullet"),
        ("「投資歴」「実績」「実際に保有している銘柄」の開示がない。", "bullet"),
        ("", "normal"),

        ("⑤ プロフィールが弱い", "heading2"),
        ("現在のプロフィール文：「ツイッターでは公開していないトレードに役立つ情報を更新」のみ。", "normal"),
        ("読者が「なぜこの人を信頼すべきか」がわからない。", "normal"),
        ("投資歴・運用実績・得意分野・経歴が未記載。", "bullet"),
        ("顔写真またはアイコン画像の印象管理が弱い可能性。", "bullet"),
        ("", "normal"),

        ("⑥ SEO・検索流入が弱い（時限性コンテンツ中心）", "heading2"),
        ("毎日の速報記事は投稿日以降に検索されにくい（「3月25日のニュース」は翌日から陳腐化）。", "normal"),
        ("Google・note内検索でヒットし続ける「保存版」コンテンツが少ない。", "normal"),
        ("「〇〇とは？」「〇〇の始め方」「〇〇の選び方」など常緑コンテンツが収益の柱になる。", "bullet"),
        ("タグの最適化・ハッシュタグ戦略が見えない。", "bullet"),
        ("", "normal"),

        ("⑦ YouTube・SNSとの有機的な連携がない", "heading2"),
        ("YouTubeのnote下書きも自動生成しているが、動画が実際に公開されていない。", "normal"),
        ("Twitter（@VAKERSTREET）との相互送客が弱いため、新規流入が少ない。", "normal"),
        ("投資クリエイター同士のコラボ・相互フォローなどコミュニティ形成がない。", "bullet"),
        ("", "normal"),

        # ========== 3. 収益化ロードマップ ==========
        ("3｜収益化ロードマップ", "heading1"),
        ("", "normal"),

        ("Phase 1：土台づくり（〜3ヶ月）　目標フォロワー500人", "heading2"),
        ("プロフィール強化：投資歴・運用実績・得意分野・キャッチコピーを追記", "bullet"),
        ("自己紹介記事の投稿：「なぜnoteを書いているか」「どんな投資をしているか」を1本書く", "bullet"),
        ("Twitter連携強化：note記事公開のたびにTwitterに告知投稿（毎日）", "bullet"),
        ("コメント文化の醸成：他の投資系クリエイターの記事にコメント → 相互フォロー", "bullet"),
        ("週1本「保存版」記事追加：検索で長期間ヒットする記事を週1本追加", "bullet"),
        ("", "normal"),

        ("Phase 2：有料化開始（3〜6ヶ月）　目標月収¥10,000〜", "heading2"),
        ("有料記事を月2〜4本投稿（¥300〜¥500/本）：深掘り銘柄分析・ポートフォリオ公開", "bullet"),
        ("マガジンの価格見直し：¥19,800→月額¥980に変更（継続課金モデルへ）", "bullet"),
        ("無料プレビュー戦略：記事の前半無料・後半有料にして購読意欲を高める", "bullet"),
        ("メンバーシップ導入：月額¥500〜¥1,000（限定記事・質問受付・ポートフォリオ公開）", "bullet"),
        ("", "normal"),

        ("Phase 3：収益最大化（6ヶ月〜）　目標月収¥50,000〜", "heading2"),
        ("フォロワー1,000人達成：月1,000人×購読率5%×¥980=月収¥49,000", "bullet"),
        ("YouTubeチャンネル立ち上げ：動画→note誘導のファネルを構築", "bullet"),
        ("有料コンテンツのラインナップ拡充：入門マガジン¥500・中級¥1,980・プレミアム¥9,800", "bullet"),
        ("スポンサー・アフィリエイト：証券会社・投資サービスのアフィリエイト掲載", "bullet"),
        ("", "normal"),

        # ========== 4. 最優先アクション ==========
        ("4｜今すぐやるべき最優先アクション TOP5", "heading1"),
        ("", "normal"),
        ("1. プロフィール文を書き直す（所要時間：30分）", "bold_normal"),
        ("投資歴・実績・なぜ信頼できるかを明示。読者が「この人から買いたい」と思えるプロフィールに。", "normal"),
        ("", "normal"),
        ("2. 月2本だけ有料記事（¥300〜¥500）を出す（今月中）", "bold_normal"),
        ("「有料記事を買う」という読者体験を作る。最初の1本が最も重要。", "normal"),
        ("", "normal"),
        ("3. マガジン価格を月額制（¥980/月）に変更する", "bold_normal"),
        ("¥19,800は心理的ハードルが高い。月額制にすることで試しやすくなり購読者数が増える。", "normal"),
        ("", "normal"),
        ("4. Twitter→noteの導線を毎日設置する", "bold_normal"),
        ("毎日の自動投稿記事をTwitterで告知。「続きはnoteで」の流れを作る。", "normal"),
        ("", "normal"),
        ("5. 週1本「保存版」深掘り記事を追加する", "bold_normal"),
        ("「〇〇とは？」「〇〇の始め方」系の記事はGoogle検索から長期的に流入する。速報記事だけでは検索流入が増えない。", "normal"),
        ("", "normal"),

        # ========== 5. 収益ポテンシャル試算 ==========
        ("5｜収益ポテンシャル試算", "heading1"),
        ("", "normal"),
        ("フォロワー500人（3ヶ月後の目標）", "heading2"),
        ("有料記事（¥300）× 月4本 × 購入率2%（10人）= ¥12,000/月", "bullet"),
        ("メンバーシップ（¥980）× 購読率3%（15人）= ¥14,700/月", "bullet"),
        ("合計目標：約¥26,700/月", "bold_normal"),
        ("", "normal"),
        ("フォロワー1,000人（6ヶ月後の目標）", "heading2"),
        ("有料記事（¥500）× 月4本 × 購入率2%（20人）= ¥40,000/月", "bullet"),
        ("メンバーシップ（¥980）× 購読率5%（50人）= ¥49,000/月", "bullet"),
        ("アフィリエイト収入（証券口座紹介など）= ¥10,000〜/月", "bullet"),
        ("合計目標：約¥99,000/月", "bold_normal"),
        ("", "normal"),

        # ========== 付録 ==========
        ("付録｜直近の記事スキ数データ（2025年12月〜2026年3月）", "heading1"),
        ("", "normal"),
        ("タイトル　　　　　　　　　　　　　　　　　　公開日　　スキ数", "bold_normal"),
        ("バブル崩壊の予兆？プライベートクレジット〜　2026/3/25　0", "bullet"),
        ("新聞よりわかりやすくて早い3月25日〜　　　　2026/3/25　1", "bullet"),
        ("新聞よりわかりやすくて早い今日〜（3/24）　 2026/3/24　6", "bullet"),
        ("新聞よりわかりやすくて早い3月23日〜　　　　2026/3/23　5", "bullet"),
        ("FOMCが「利下げ拒否」を宣言〜　　　　　　　2026/3/19　3", "bullet"),
        ("NVIDIA株+30%超の裏で日経平均〜　　　　　 2026/3/17　1", "bullet"),
        ("任天堂の株式売り出し〜5つの事実　　　　　　2026/3/10　3", "bullet"),
        ("S&P500グレート・ローテーション〜（最高値）　2026/1/3　 11", "bullet"),
        ("暴落中の任天堂株ここは買い場か〜　　　　　　2026/1/14　6", "bullet"),
        ("2026年、S&P500のリターンを超える〜3選　　  2026/1/20　5", "bullet"),
        ("", "normal"),
        ("※ 全107本中、スキ10超えは1本のみ。平均スキ数：約3.2", "normal"),
    ]

    # ─── リクエスト作成＆送信 ────────────────────────
    reqs = insert_requests(content)

    # 500件ずつに分割して送信
    chunk_size = 100
    for i in range(0, len(reqs), chunk_size):
        chunk = reqs[i:i+chunk_size]
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": chunk}
        ).execute()
        print(f"  {min(i+chunk_size, len(reqs))}/{len(reqs)} リクエスト送信済み")

    print(f"\n✅ Google Docs 作成完了")
    print(f"URL: {doc_url}")
    return doc_url


if __name__ == "__main__":
    main()
