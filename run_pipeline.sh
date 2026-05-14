#!/bin/bash
# 投資記事自動生成パイプライン 実行スクリプト
# macOS / Linux どちらでも動作する

set -euo pipefail

# スクリプト自身の場所からプロジェクトルートを特定
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
LOG_FILE="$PROJECT_DIR/output/pipeline.log"

# output ディレクトリ作成
mkdir -p "$PROJECT_DIR/output"

echo "========================================" >> "$LOG_FILE"
echo "実行開始: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

cd "$PROJECT_DIR/src"

# .env を読み込む（存在する場合）
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

python3 main.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

echo "終了コード: $EXIT_CODE" >> "$LOG_FILE"
echo "実行終了: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"

exit $EXIT_CODE
