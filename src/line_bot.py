"""
LINE Bot <-> Claude Code 連携サーバー

iPhoneのLINEからメッセージを送ると、Claude CLIが応答を生成してLINEに返信する。
cloudflared tunnel でWebhook URLを自動取得。アカウント不要。
"""

import os
import sys
import subprocess
import json
import logging
import threading
import time
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.getenv("LINE_USER_ID", "")
PORT = int(os.getenv("LINE_BOT_PORT", "5000"))

CLAUDE_TIMEOUT = 180

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Windows では claude.cmd のフルパスを使う
CLAUDE_CMD = os.path.join(
    os.path.expanduser("~"), "AppData", "Roaming", "npm", "claude.cmd"
)

# cloudflared のパス
CLOUDFLARED = os.path.join(
    os.path.expanduser("~"),
    "AppData", "Local", "Microsoft", "WinGet", "Packages",
    "Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe",
    "cloudflared.exe",
)


def push_message(user_id: str, text: str):
    """LINE Push APIでメッセージを送信する"""
    messages = []
    while text:
        chunk = text[:4900]
        text = text[4900:]
        messages.append({"type": "text", "text": chunk})
        if len(messages) >= 5:
            break

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    data = json.dumps({"to": user_id, "messages": messages}).encode("utf-8")

    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req) as resp:
            log.info(f"LINE push sent: {resp.status}")
    except Exception as e:
        log.error(f"LINE push failed: {e}")


def ask_claude(message: str) -> str:
    """Claude CLIにメッセージを送って応答を取得する"""
    try:
        # メッセージ内の引用符をエスケープ
        safe_msg = message.replace('"', '\\"')
        result = subprocess.run(
            f'"{CLAUDE_CMD}" -p "{safe_msg}"',
            capture_output=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=PROJECT_ROOT,
            shell=True,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.decode("utf-8", errors="replace").strip()
        elif result.stderr:
            err = result.stderr.decode("utf-8", errors="replace")
            log.error(f"Claude CLI error: {err}")
            return f"エラー: {err[:500]}"
        else:
            return "応答を取得できませんでした"
    except subprocess.TimeoutExpired:
        return "タイムアウト（180秒超過）"
    except FileNotFoundError:
        return "Claude CLIが見つかりません"
    except Exception as e:
        log.error(f"ask_claude exception: {e}")
        return f"エラー: {str(e)[:500]}"


def handle_message_async(user_id: str, user_message: str):
    """別スレッドでClaude CLIを呼び出し、Push APIで返信する"""
    log.info(f"Processing: {user_message[:80]}...")
    push_message(user_id, "考え中...")

    response = ask_claude(user_message)
    log.info(f"Response ({len(response)} chars): {response[:100]}...")
    push_message(user_id, response)


class LineWebhookHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

        try:
            body_str = body.decode("utf-8", errors="replace")
            events = json.loads(body_str).get("events", [])
            for event in events:
                self._handle_event(event)
        except Exception as e:
            log.error(f"Event processing error: {e}")

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"LINE Bot is running")

    def _handle_event(self, event: dict):
        if event.get("type") != "message":
            return
        if event["message"].get("type") != "text":
            return

        user_id = event["source"].get("userId", "")

        if LINE_USER_ID and user_id != LINE_USER_ID:
            log.warning(f"Ignored message from unknown user: {user_id}")
            return

        user_message = event["message"]["text"]

        thread = threading.Thread(
            target=handle_message_async,
            args=(user_id, user_message),
            daemon=True,
        )
        thread.start()

    def log_message(self, format, *args):
        pass


def start_tunnel():
    """cloudflared quick tunnel を起動してURLを取得する"""
    if not os.path.exists(CLOUDFLARED):
        log.warning(f"cloudflared not found at {CLOUDFLARED}")
        return None

    proc = subprocess.Popen(
        [CLOUDFLARED, "tunnel", "--url", f"http://localhost:{PORT}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    # URLが出力されるまで待つ
    url = None
    deadline = time.time() + 30
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        log.debug(f"cloudflared: {line.strip()}")
        match = re.search(r"(https://[a-z0-9-]+\.trycloudflare\.com)", line)
        if match:
            url = match.group(1)
            break

    if url:
        # 残りの出力を別スレッドで読み続ける（バッファ溢れ防止）
        def drain():
            for line in proc.stdout:
                pass
        threading.Thread(target=drain, daemon=True).start()

    return url, proc


def main():
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("LINE_CHANNEL_ACCESS_TOKEN が .env に設定されていません")
        sys.exit(1)

    log.info(f"LINE Bot starting on port {PORT}")

    # cloudflared tunnel を起動
    tunnel_url = None
    tunnel_proc = None
    try:
        result = start_tunnel()
        if result:
            tunnel_url, tunnel_proc = result
    except Exception as e:
        log.warning(f"Tunnel start failed: {e}")

    if tunnel_url:
        webhook_url = f"{tunnel_url}/callback"
        log.info("")
        log.info("=" * 60)
        log.info(f"  Webhook URL: {webhook_url}")
        log.info("=" * 60)
        log.info("")
        log.info("LINE Developers > Messaging API > Webhook URL に設定してください")
        log.info("「Use webhook」を ON にしてください")
    else:
        log.warning("トンネルURL取得失敗。手動でngrok等を起動してください")

    server = HTTPServer(("0.0.0.0", PORT), LineWebhookHandler)
    log.info(f"Server listening on port {PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Server stopped")
        server.server_close()
        if tunnel_proc:
            tunnel_proc.terminate()


if __name__ == "__main__":
    main()
