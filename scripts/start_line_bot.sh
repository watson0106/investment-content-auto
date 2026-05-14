#!/bin/bash
# LINE Bot + ngrok 起動スクリプト
#
# 使い方:
#   bash scripts/start_line_bot.sh
#
# 前提:
#   - .envにLINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKENが設定済み
#   - ngrokがインストール済み (choco install ngrok / https://ngrok.com/)
#   - Claude CLIがパスに通っている

set -e
cd "$(dirname "$0")/.."

PORT=${LINE_BOT_PORT:-5000}

echo "=== LINE Bot 起動 ==="

# ngrokがインストールされているか確認
if ! command -v ngrok &> /dev/null; then
    echo "ngrokが見つかりません。インストールしてください:"
    echo "  choco install ngrok"
    echo "  または https://ngrok.com/ からダウンロード"
    echo ""
    echo "インストール後、認証トークンを設定:"
    echo "  ngrok config add-authtoken YOUR_TOKEN"
    exit 1
fi

# バックグラウンドでngrok起動
echo "ngrokを起動中 (port $PORT)..."
ngrok http $PORT --log=stdout > /tmp/ngrok.log 2>&1 &
NGROK_PID=$!
sleep 3

# ngrokのURLを取得
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python -c "import sys,json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || echo "")

if [ -z "$NGROK_URL" ]; then
    echo "ngrok URLの取得に失敗しました。手動で確認: http://localhost:4040"
else
    echo ""
    echo "=========================================="
    echo "  Webhook URL: ${NGROK_URL}/callback"
    echo "=========================================="
    echo ""
    echo "このURLをLINE DevelopersのWebhook URLに設定してください"
fi

# Pythonサーバー起動（フォアグラウンド）
echo "LINE Botサーバーを起動中..."
python src/line_bot.py

# 終了時にngrokも停止
kill $NGROK_PID 2>/dev/null
