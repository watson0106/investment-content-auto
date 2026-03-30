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
- GEMINI_API_KEY：カバー画像生成用（ワークフローのenv:に追加済み。**GitHub Secretsで管理。CLAUDE.mdには書かない**）

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

### 見本記事
https://note.com/preview/n776eaef10c91?prev_access_key=d87dc1d34d851160b81df8ae74c9e8a0

### タイトル固定
`新聞より早くてわかりやすい今日の投資ニュース速報｜M/D`
（「投資」を含める）

### ニュース本数
- 2本（3本ではない）

### 本文構成（見出しレベル）—— 見本記事（3/30版）の構造に準拠
```
## 今日のニュース速報｜10秒サマリー   ← H2（## 必須。clean_article()で消えないよう）
① [ニュース1要点1行・数字含む]
② [ニュース2要点1行・数字含む]
---
# ①[ソース名]が報じたこと        ← H1（①②プレフィックス付き）
[「ソース名によると、」で始まる本文300〜400字。H2の前に直接書く。「## 数字で見る」などの固定見出しは使わない]
## [カスタムH2タイトル1（例：「ドル買いを呼ぶメカニズム」）]    ← H2（内容に即した独自タイトル）
[300〜400字]
## [カスタムH2タイトル2（例：「介入ハードルが高い理由」）]      ← H2
[300〜400字]
## [カスタムH2タイトル3（例：「日銀利上げ観測との綱引き」）]    ← H2（必要に応じて3つ目）
[300〜400字]
# [社説タイトル（例：「160円は通過点に過ぎないと私は見ている」）] ← H1（一人称断定形）
[500〜700字。具体的数字・シナリオ含む]
# このニュースで注目すべき銘柄  ← H1
[銘柄名（ticker）]               ← 「銘柄名：」プレフィックスなし。括弧内のティッカーをチャート生成に使用
本日の株価：[直近株価と説明]
__CHART_0__                      ← yfinanceチャート自動挿入（銘柄直下）
[300〜500字。短期値動きシナリオ（具体的株価・出来高数字）含む]
---
# ②[ソース名2]が報じたこと       ← H1
[本文300〜400字]
## [カスタムH2タイトル1]
[300〜400字]
## [カスタムH2タイトル2]
[300〜400字]
## [カスタムH2タイトル3]
[300〜400字]
# [社説タイトル2]                ← H1
[500〜700字]
# このニュースで注目すべき銘柄  ← H1
[銘柄名（ticker）]               ← 「銘柄名：」プレフィックスなし
本日の株価：[直近株価と説明]
__CHART_1__
[300〜500字]
---
[CTA文（固定）]
__MAGAZINE_EMBED__               ← 有料マガジン埋め込み自動挿入
```

### 禁止事項
- `## 数字で見る` `## 背景にある構造` `## 何が起きたのか` などの固定サブ見出し禁止
- H1の①②ソースセクション直下は必ず本文から直接始めること
- H2タイトルは常にそのニュース内容に即した具体的なタイトルにする

### CTA文（固定・記事末尾）
```
情報を正確に理解することは、投資の第一歩に過ぎない。株価は常に「情報の一歩先」を織り込んで動いており、ニュースを読むだけでは勝てないのが相場の現実だ。毎週の注目銘柄・具体的な売買シナリオ・エントリー根拠まで踏み込んで解説する有料マガジンはこちら。「知っている」を「稼げる」に変えたい方はぜひ。
```
- 有料マガジンURL: https://note.com/kawasewatson0106/m/me3bdb7d529fc
- 挿入方法: 「＋」→「埋め込み」→URL入力→「適用」（Seleniumで自動化）

## 画像仕様

### カバー画像（サムネイル）
- **Geminiは一切使用しない**
- **優先①**: `~/Desktop/投資画像/` 内の最新画像を使用（Gemini_Gener...で始まるファイルを優先）
- **優先②**: `assets/cover_image.png` をフォールバック（デスクトップ画像なし時）
- `post_to_note.py` の `_upload_cover_image()` で3段階アプローチを実行:
  1. エディタ上部のアイキャッチエリアをクリック → ファイルインプット出現 → send_keys
  2. 「公開に進む」モーダルのアイキャッチエリア経由
  3. note API `POST /api/v1/text_notes/{key}/eyecatch` でbase64アップロード
- アップロード後6秒待機

### 銘柄チャート
- `generate_images.py` が yfinance + matplotlib で1時間足チャート生成
- 銘柄コード抽出: `# このニュースで注目すべき銘柄` セクション直後の行から `（TICKER）` を抽出
  - 「銘柄名：」プレフィックスありなし両対応
- 日本株4桁→ `.T` 付加（例：7203 → 7203.T）
- MA5/MA20/RSI(14)/出来高付きダークテーマチャート
- `__CHART_0__` → `__IMAGE_0__`、`__CHART_1__` → `__IMAGE_1__` に置換して挿入

## note.com 見出し対応
- `#` (H1) → `document.execCommand('formatBlock', false, 'h1')`
- `##` (H2) → `document.execCommand('formatBlock', false, 'h2')`
- `insert_section_with_headings()` で level 判定して適用

## 文体ルール（watson0106/stock-analysis-auto 準拠）
- 絵文字使用禁止
- 「おそらく」「推測される」「〜と思われる」「〜かもしれない」使用禁止
- 「私はこう見ている」一人称を判断の表明として使う（言い訳に使わない）
- 試算数字には必ず計算式か前提条件を1行添える
- 断言できないことは書かない
- マークダウン `#`/`##` は見出しのみ。インライン太字（**）は使用禁止
- 不確かな情報は「〜と報じられています」と出典を明記する

## 絶対ルール
- Anthropic API キーは使わない（OAuthトークンのみ）
- Claude CLI の OAuth 認証のみ
- **Gemini は一切使わない**（APIキーがあっても使用禁止）
- **YouTube note パイプラインは無効化済み**（英語タイトル記事を作成するため）
- 会話の進捗・決定事項をこのファイルに逐一保存する
