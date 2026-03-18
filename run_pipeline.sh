#!/bin/bash
# 投資記事自動生成パイプライン 実行スクリプト
# launchd / cron から呼び出される

set -euo pipefail

PROJECT_DIR="/Users/watson/investment-content-auto"
LOG_FILE="$PROJECT_DIR/output/pipeline.log"

# output ディレクトリ作成
mkdir -p "$PROJECT_DIR/output"

echo "========================================" >> "$LOG_FILE"
echo "実行開始: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

cd "$PROJECT_DIR/src"

/usr/bin/python3 main.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

echo "終了コード: $EXIT_CODE" >> "$LOG_FILE"
echo "実行終了: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"

exit $EXIT_CODE
