# investment-content-auto — プロジェクト指示書

## コミュニケーション
- 日本語で会話する

## プロジェクト概要
- 毎日投資ニュースを自動収集・AI分析・記事生成・note投稿するパイプライン
- GitHub Actions で毎朝 JST 07:00 に自動実行

## ユーザー指示
- おおまかな計画だけ言う、細かい判断・選択はすべてClaudeに一任
- 承認を求めずに最善策を実行して成果物を作り上げること
- 会話の進捗・決定事項を CLAUDE.md に逐一保存すること

## 進捗状況

### PHASE 1：コード実装 ✅ 完了
- [x] src/collect_news.py（RSS 13ソース、スコアリング・重複除去）
- [x] src/deep_research.py（Gemini 2.0 Flash で記事ドラフト生成）
- [x] src/fact_check.py（Claude Opus でファクトチェック・文体調整）
- [x] src/generate_images.py（Gemini 画像生成 API で図表挿入）
- [x] src/generate_title.py（Claude Opus でタイトル10案生成・自動選択）
- [x] src/post_to_note.py（Selenium で note.com に自動投稿）
- [x] src/main.py（パイプライン統合エントリポイント）
- [x] .github/workflows/daily_post.yml（毎日 JST 07:00 自動実行）

### PHASE 2：GitHub リポジトリ作成・Secrets 設定
- [x] GitHubリポジトリ作成（watson0106/investment-content-auto）
- [ ] GitHub Secrets 設定（GEMINI_API_KEY / ANTHROPIC_API_KEY / NOTE_EMAIL / NOTE_PASSWORD）
- [ ] 動作確認（workflow_dispatch で手動実行）

### note投稿方式（JS API方式）✅ 動作確認済み
- SeleniumのDOM操作ではなく内部APIをJS fetchで直接呼び出す方式
- undetected-chromedriver + headless=false でWAFを回避
- ログイン: `POST /api/v1/sessions/sign_in`
- ドラフト作成: `POST /api/v1/text_notes`（editor.note.comドメインから）
- 記事更新・公開: `PUT /api/v1/text_notes/{id}` with `{name, body, status, hashtag_list}`
- GitHub Actions: Xvfb仮想ディスプレイで非headless実行
- ローカルテストでWAFレートリミットに注意（連続アクセスで403）

## 技術スタック
- ニュース収集：feedparser + BeautifulSoup（13 RSS ソース）
- 深掘り分析：Gemini 2.5 Flash
- 添削：Claude Opus 4.6
- 画像生成：Gemini 3 Pro Image Preview
- タイトル生成：Claude Opus 4.6
- 自動投稿：undetected-chromedriver + JS API
- CI/CD：GitHub Actions（毎日 UTC 22:00 = JST 07:00、Xvfb使用）

## 環境変数（GitHub Secrets に登録）
- GEMINI_API_KEY
- ANTHROPIC_API_KEY
- NOTE_EMAIL
- NOTE_PASSWORD
