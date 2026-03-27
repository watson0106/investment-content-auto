# investment-content-auto — プロジェクト指示書

## コミュニケーション
- 日本語で会話する

## プロジェクト概要
- 毎日投資ニュースを自動収集・AI分析・記事生成・note投稿するパイプライン
- GitHub Actions で毎朝 JST 07:00 に自動実行
- **記事は1日1記事のみ**（有料記事・YouTube下書き等の2つ目は作らない）

## ユーザー指示
- おおまかな計画だけ言う、細かい判断・選択はすべてClaudeに一任
- 承認を求めずに最善策を実行して成果物を作り上げること
- 会話の進捗・決定事項を CLAUDE.md に逐一保存すること
- **修正・変更したら必ず自分で実行して検証すること**（動作確認せずに「修正しました」で終わらない）

## パイプラインフロー（無料記事 + 有料記事のセット）
1. ① ニュース収集（RSS 13ソース → スコアリング → 上位10件選出）
2. ② Gemini で深掘り記事執筆（Claude CLIは会話応答を返すためGeminiをメインで使用）
3. ③ Claude Opus で添削（ファクトチェック・個人ブロガー口調に調整）
4. ④ Gemini 3 Pro で画像生成（カバー画像 + 本文中のイメージ画像）
5. ⑤ タイトル生成（Claude CLI → スコアリング自動選択）
6. ⑥ note に無料記事を下書き保存
7. ⑦ 投稿結果の検証（タイトル・本文・画像の品質チェック）
8. ⑧ 有料記事生成・投稿（100円、画像なし、GS級分析＋ブロガー口調）
9. ⑨ 無料記事の末尾に有料記事リンクを追記
10. ⑩ PDCAトラッカー（スキ数更新）

## 有料記事の仕様
- 無料記事のテーマに紐づく「具体的な投資アクションプラン」
- ペルソナ: GS出身シニアアナリスト級の分析力、ブロガー口調で執筆
- 構成: 結論→理由（最初に「何を買って何を売るか」を言い切る）
- 「みんなが思いつく予測」はNG、「その発想はなかった」と思わせる視点
- 画像なし、100円
- 投資助言にあたらない内容（免責事項付き）
- AI感のある表現NG、箇条書きに「*」使わない

## 削除済み機能（復活させない）
- YouTube note 下書きパイプライン
- マガジン自動管理
- プロフィール自動更新
- 異常検知
- 日次レポート通知

## 既知の問題・注意点
- Claude CLI をsubprocessで呼ぶと、CLAUDE.mdのペルソナ指示を拾って「承知しました」等の会話応答を返す
  → 品質検証で検出し、Geminiにフォールバックする仕組みで対処済み
- 画像挿入: noteのProseMirrorエディタへの画像挿入は `/api/v1/image_upload` API方式を使用
  → クリップボードペースト方式はSelenium経由で動作しないため廃止

## 技術スタック
- ニュース収集：feedparser + BeautifulSoup（13 RSS ソース）
- 深掘り分析：Gemini 2.5 Flash（メイン）
- 添削：Claude Opus 4.6
- 画像生成：Gemini 3 Pro Image Preview
- タイトル生成：Claude Opus 4.6
- 自動投稿：undetected-chromedriver + JS API
- CI/CD：GitHub Actions（毎日 UTC 22:00 = JST 07:00、Xvfb使用）

## 環境変数（GitHub Secrets に登録）
- GEMINI_API_KEY = AIzaSyA-J-W8cw_do0mFLvkO_MeZrVgCdPGdBQs
- ANTHROPIC_API_KEY（Claude CLI のキーを使用）
- NOTE_EMAIL = watson19910704@gmail.com
- NOTE_PASSWORD = ts2164
