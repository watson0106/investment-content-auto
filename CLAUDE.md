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

### 現在の構成 ✅
- **全工程 Claude CLI のみ**（GeminiもAnthropicAPIキーも不使用）
- Claude CLIはOAuth認証（claude.ai Proアカウント）で動作
- GitHub ActionsではCLAUDE_CODE_CREDENTIALSシークレットからOAuthトークンを読み込む

### パイプライン構成
- [x] src/collect_news.py（RSS 13ソース → Claude CLIで選定）
- [x] src/deep_research.py（Claude Opus 4.6で記事執筆）
- [x] src/post_to_note.py（JS API方式でnote下書き保存）
- [x] src/main.py（パイプライン統合エントリポイント）
- [x] .github/workflows/daily_post.yml（毎日 JST 05:00 = UTC 20:00）

### GitHub Secrets（登録済み）
- CLAUDE_CODE_CREDENTIALS：OAuthトークンJSON（キーチェーンから取得）
- NOTE_EMAIL = watson19910704@gmail.com
- NOTE_PASSWORD = ts2164
- GEMINI_API_KEY：残存しているが未使用

### note投稿方式（JS API方式）✅ 動作確認済み
- undetected-chromedriver + headless=false でWAFを回避
- ログイン: `POST /api/v1/sessions/sign_in`
- ドラフト作成・公開: `PUT /api/v1/text_notes/{id}`
- GitHub Actions: Xvfb仮想ディスプレイで非headless実行

### GitHub Actions ワークフロー構成
1. checkout → Python 3.11 → Chrome → Xvfb → pip install
2. npm install -g @anthropic-ai/claude-code（Claude CLI インストール）
3. CLAUDE_CODE_CREDENTIALSを ~/.claude/.credentials.json に書き込み
4. python src/main.py（ニュース収集→執筆→note下書き保存）
5. 記事履歴をリポジトリにコミット

## 記事フォーマット（速報スタイル）

### タイトル固定
`新聞より早くてわかりやすい今日のニュース速報｜M/D`
（「投資」は含めない）

### ニュース本数
- 2本（3本ではない）

### 本文構成
```
今日のニュース速報｜10秒サマリー
① [ニュース1の要点1行・数字含む・事実を断言]
② [ニュース2の要点1行・数字含む・事実を断言]

---

## ニュース① [見出し・25字以内]

**[ソース名]が報じたこと**
[600〜800字。「[ソース名]によると、」で始める。5W1H・具体的数字]

**なぜ投資家に重要か**
[500〜700字。株価・為替・金利・業績への波及。具体的な銘柄名・ETF名]

**自分の意見（社説）**
[400〜600字。「私はこう見ている」一人称。断定形。具体的行動で締める]

**このニュースで注目すべき銘柄**
銘柄名：[銘柄名（ティッカーまたは証券コード）]
現在株価：[直近株価。不明なら「要確認」]
[300〜500字。なぜ注目か。業績・株価への直結を論理的に説明]

---

## ニュース②（同様）
```

テンプレート参照記事: https://editor.note.com/notes/n776eaef10c91/edit/

## 文体ルール（watson0106/stock-analysis-auto 準拠）
- 絵文字使用禁止
- 「おそらく」「推測される」「〜と思われる」「〜かもしれない」使用禁止
- 「私はこう見ている」一人称を判断の表明として使う（言い訳に使わない）
- 試算数字には必ず計算式か前提条件を1行添える
- 断言できないことは書かない
- マークダウン太字（**）は見出しのみ
- 不確かな情報は「〜と報じられています」と出典を明記する

## 絶対ルール
- Anthropic API キーは使わない（OAuthトークンのみ）
- Geminiは使わない（全工程Claude）
- 会話の進捗・決定事項をこのファイルに逐一保存する
