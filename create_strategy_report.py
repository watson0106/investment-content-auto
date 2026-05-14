#!/usr/bin/env python3
"""
TATSUJIN TRADE 収益化戦略レポート Google Docs 作成
"""
import os, json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = os.path.expanduser("~/kindle_extract/credentials.json")
TOKEN_FILE = os.path.expanduser("~/kindle_extract/token.json")

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
    requests = []
    index = 1
    for text, style in content_lines:
        full_text = text + "\n"
        length = len(full_text)
        requests.append({"insertText": {"location": {"index": index}, "text": full_text}})
        if style == "title":
            requests.append({"updateParagraphStyle": {"range": {"startIndex": index, "endIndex": index+length}, "paragraphStyle": {"namedStyleType": "TITLE"}, "fields": "namedStyleType"}})
        elif style == "heading1":
            requests.append({"updateParagraphStyle": {"range": {"startIndex": index, "endIndex": index+length}, "paragraphStyle": {"namedStyleType": "HEADING_1"}, "fields": "namedStyleType"}})
        elif style == "heading2":
            requests.append({"updateParagraphStyle": {"range": {"startIndex": index, "endIndex": index+length}, "paragraphStyle": {"namedStyleType": "HEADING_2"}, "fields": "namedStyleType"}})
        elif style == "heading3":
            requests.append({"updateParagraphStyle": {"range": {"startIndex": index, "endIndex": index+length}, "paragraphStyle": {"namedStyleType": "HEADING_3"}, "fields": "namedStyleType"}})
        elif style == "bullet":
            requests.append({"createParagraphBullets": {"range": {"startIndex": index, "endIndex": index+length}, "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}})
        elif style == "bold":
            requests.append({"updateTextStyle": {"range": {"startIndex": index, "endIndex": index+length-1}, "textStyle": {"bold": True}, "fields": "bold"}})
        elif style == "red_bold":
            requests.append({"updateTextStyle": {"range": {"startIndex": index, "endIndex": index+length-1}, "textStyle": {"bold": True, "foregroundColor": {"color": {"rgbColor": {"red": 0.8, "green": 0.0, "blue": 0.0}}}}, "fields": "bold,foregroundColor"}})
        index += length
    return requests

def main():
    creds = get_credentials()
    docs_service = build('docs', 'v1', credentials=creds)

    doc = docs_service.documents().create(body={"title": "TATSUJIN TRADE 収益化戦略レポート Ver.2｜2026-03-25"}).execute()
    doc_id = doc["documentId"]
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"ドキュメント作成: {doc_url}")

    content = [
        ("TATSUJIN TRADE 収益化戦略レポート Ver.2", "title"),
        ("作成日：2026年3月25日　by 収益化戦略ディレクター（AI）", "normal"),
        ("", "normal"),

        ("【宣告】現在の運用は収益化の設計が根本的に間違っている", "heading1"),
        ("", "normal"),
        ("結論から言う。日次速報スタイルは「スキも集まらず有料も売れない」最悪の構造だ。", "bold"),
        ("", "normal"),
        ("データが証明する事実", "heading2"),
        ("個別銘柄の深掘り記事：平均12〜17スキ（サンリオ17スキ、高市13スキ、レーザーテック12スキ）", "bullet"),
        ("保存版・手法系記事：平均11〜13スキ", "bullet"),
        ("日次速報（現在の主力）：平均1〜3スキ ← これが問題の核心", "bullet"),
        ("スキ0記事：107本中5本（4%）", "bullet"),
        ("", "normal"),
        ("つまり、毎日時間とコストをかけて生成している速報記事は、深掘り記事の1/5以下の反応しか得ていない。", "normal"),
        ("自動化の方向性は正しいが、自動化している内容が間違っている。", "bold"),
        ("", "normal"),

        ("1｜競合の「勝ちパターン」解剖", "heading1"),
        ("", "normal"),
        ("noteで月10万円以上稼いでいる投資系クリエイターの共通構造", "heading2"),
        ("", "normal"),
        ("① 「保存・拡散したい」記事を軸にする", "heading3"),
        ("タイトルパターン：【保存版】、完全解説、〇〇が6倍になった理由", "bullet"),
        ("Googleで何度も検索される「常緑コンテンツ」が収益の柱", "bullet"),
        ("速報性より「この記事は来週・来月も価値がある」と思わせる内容", "bullet"),
        ("", "normal"),
        ("② 無料記事は「95%の価値」を提供し、残り5%で有料を売る", "heading3"),
        ("無料：「なぜサンリオ株が6倍になったか（背景・構造）」", "bullet"),
        ("有料：「では私は今どのタイミングで何株を買うか（具体的な売買計画）」", "bullet"),
        ("無料で十分な価値を渡した後だから、読者は有料を買う", "bullet"),
        ("", "normal"),
        ("③ 価格はしごが存在する", "heading3"),
        ("無料 → ¥500（個別記事）→ ¥980/月（メンバーシップ）→ ¥9,800（プレミアム）", "bullet"),
        ("現在のTATSUJIN TRADEは：無料 → ¥19,800 の断崖絶壁", "red_bold"),
        ("", "normal"),

        ("2｜¥19,800のマガジンが売れない構造的理由", "heading1"),
        ("", "normal"),
        ("読者心理のフェーズ分析", "heading2"),
        ("", "normal"),
        ("【現状の設計：機能しない】", "bold"),
        ("無料速報（信頼形成なし）→→→→→→→→→→→→→→→ ¥19,800（誰も買えない）", "normal"),
        ("", "normal"),
        ("【正しい設計】", "bold"),
        ("無料深掘り（認知・興味）→ ¥500体験（信頼形成）→ ¥980/月継続（習慣化）→ ¥9,800プレミアム（ロイヤル）", "normal"),
        ("", "normal"),
        ("¥19,800は「信頼が完全に形成されたロイヤル読者」だけが買う価格だ。", "normal"),
        ("フォロワー191人の現時点で、その読者は存在しない。", "normal"),
        ("", "normal"),
        ("CVR（購入転換率）の現実", "heading2"),
        ("191フォロワー × 0%購買率 = ¥0収益（推定）", "bullet"),
        ("無料→有料の中間ステップがなく、読者が「試す」方法がない", "bullet"),
        ("各記事末尾にCTA（有料記事への誘導文）が存在しない", "bullet"),
        ("有料記事を1本も出していないため読者が購買体験できていない", "bullet"),
        ("", "normal"),

        ("3｜今すぐ実行した改修内容（AI側で実装済み）", "heading1"),
        ("", "normal"),
        ("① 記事フォーマットを「深掘り1テーマ完全解説」に変更 ✅ 実装済み", "heading2"),
        ("3本のニュース速報 → 1テーマの徹底解剖に切り替え", "bullet"),
        ("記事冒頭に「結論」を置く（読者が最初の2秒で価値判断できる構造）", "bullet"),
        ("「強気・中立・弱気の3シナリオ＋私の行動計画」を毎回明記", "bullet"),
        ("「保存版」「完全解説」レベルの密度を自動生成プロンプトで実現", "bullet"),
        ("", "normal"),
        ("② 全記事末尾にCTAを自動挿入 ✅ 実装済み", "heading2"),
        ("「続きは有料記事で」 + 有料記事へのリンクを全記事末尾に追加", "bullet"),
        ("毎回の無料記事が有料記事への導線になる設計", "bullet"),
        ("", "normal"),
        ("③ タイトル生成を「高スキパターン優先」に変更 ✅ 実装済み", "heading2"),
        ("銘柄名・逆張り・保存版パターンを優先するプロンプトに変更", "bullet"),
        ("「新聞よりわかりやすくて早い〜」型の汎用タイトルを完全禁止", "bullet"),
        ("", "normal"),
        ("④ 週2回（火・金）の有料記事（¥500）自動生成・投稿 ✅ 実装済み", "heading2"),
        ("毎週火・金曜日に「私の実際の売買計画」を有料記事で公開", "bullet"),
        ("無料記事の「続き」として位置づけ、CVRを最大化", "bullet"),
        ("", "normal"),
        ("⑤ PDCAトラッカー稼働 ✅ 実装済み（108本のデータで初期分析完了）", "heading2"),
        ("毎日：スキ数をnote APIで自動取得・蓄積", "bullet"),
        ("毎週月曜：高スキトピック・タイトルパターンを分析 → プロンプトに自動反映", "bullet"),
        ("データが増えるほど精度が上がる自己改善ループ", "bullet"),
        ("", "normal"),

        ("4｜あなた（人間）に今すぐやってほしい3つの指示", "heading1"),
        ("", "normal"),
        ("これはAIにはできない。本日中に実行すること。", "red_bold"),
        ("", "normal"),
        ("【最重要】指示①：マガジン価格を月額¥980に変更する", "heading2"),
        ("現在の¥19,800は誰も試し読みできない断崖絶壁の価格設定だ。", "bold"),
        ("今日中に月額¥980の定期購読マガジンに変更してほしい。", "normal"),
        ("¥980/月 × フォロワーの3%（6人）= ¥5,880/月 → これが現実的な最初の収益", "bullet"),
        ("変更URL: https://note.com/kawasewatson0106/magazines", "bullet"),
        ("", "normal"),
        ("指示②：プロフィールに投資実績の数字を入れる", "heading2"),
        ("「投資歴〇年・累積利益〇万円（または含み益〇%）」という数字がないと信頼されない。", "normal"),
        ("AIが生成したプロフィール文はすでにセットされているが、実績数字だけはあなたにしか書けない。", "bold"),
        ("例：「投資歴12年、過去5年の年平均リターン+18%（米国株中心）」", "bullet"),
        ("", "normal"),
        ("指示③：スキ上位10記事を有料マガジンに追加する", "heading2"),
        ("現在マガジンは8本。スキが多い記事（サンリオ17スキ、高市13スキ等）を追加して20本以上にすること。", "normal"),
        ("「このマガジンには良い記事が揃っている」と思わせる量が必要だ。", "normal"),
        ("追加対象（スキ順）：サンリオ、高市早苗×株、保存版エントリー、レーザーテック、ゴールド完全予測", "bullet"),
        ("", "normal"),

        ("5｜収益化シミュレーション（現実的な3段階）", "heading1"),
        ("", "normal"),
        ("Phase 1（1〜3ヶ月）：フォロワー500人達成", "heading2"),
        ("月額マガジン（¥980）× 購読率3%（15人）= ¥14,700/月", "bullet"),
        ("有料記事（¥500）× 週2本 × 購入率2%（2人）= ¥4,000/月", "bullet"),
        ("目標月収：¥18,700", "bold"),
        ("", "normal"),
        ("Phase 2（3〜6ヶ月）：フォロワー1,000人達成", "heading2"),
        ("月額マガジン（¥980）× 購読率5%（50人）= ¥49,000/月", "bullet"),
        ("有料記事（¥500）× 週2本 × 購入率3%（6人）= ¥12,000/月", "bullet"),
        ("目標月収：¥61,000", "bold"),
        ("", "normal"),
        ("Phase 3（6ヶ月〜）：フォロワー2,000人＋YouTube連携", "heading2"),
        ("月額マガジン（¥980）× 100人 = ¥98,000/月", "bullet"),
        ("YouTube→note誘導による新規流入月100人ペース", "bullet"),
        ("目標月収：¥100,000+", "bold"),
        ("", "normal"),

        ("6｜PDCAの現在地と今後の自動改善サイクル", "heading1"),
        ("", "normal"),
        ("初回分析結果（108本・全期間データ）", "heading2"),
        ("全体平均スキ：4.0スキ", "bullet"),
        ("最効果的タイトルパターン：疑問形+数字（平均4.7スキ）", "bullet"),
        ("最良投稿曜日：日・土（平均5〜6スキ）", "bullet"),
        ("スキ最高記事：サンリオ逆襲（17スキ）", "bullet"),
        ("", "normal"),
        ("自動改善ループ", "heading2"),
        ("毎日：記事投稿 → スキ数取得 → DBに蓄積", "bullet"),
        ("毎週月曜：30日分を分析 → 高スキトピック・タイトルパターンを抽出", "bullet"),
        ("翌日から：分析結果がプロンプトに自動反映 → 記事品質が上がる", "bullet"),
        ("毎月：収益データ（購入数・CVR）を手動で追加して精度向上（あなたの作業）", "bullet"),
        ("", "normal"),
        ("このPDCAサイクルは永久に回り続ける。", "bold"),
        ("データが蓄積されるほど、何のテーマをどのタイトルで何曜日に書けば売れるかが明確になっていく。", "normal"),
    ]

    reqs = insert_requests(content)
    chunk_size = 100
    for i in range(0, len(reqs), chunk_size):
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": reqs[i:i+chunk_size]}
        ).execute()
        print(f"  {min(i+chunk_size, len(reqs))}/{len(reqs)} リクエスト送信済み")

    print(f"\n✅ 戦略レポート作成完了\nURL: {doc_url}")
    return doc_url

if __name__ == "__main__":
    main()
