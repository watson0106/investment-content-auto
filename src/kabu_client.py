"""
au カブコム証券 kabuステーションAPI クライアント

- .env の KABU_API_ENV (prod/test) に応じてポートとパスワードを切替
- トークンはプロセス内キャッシュ（失効時は自動再取得）
- 照会系のみ提供（/sendorder 等の発注系は意図的に未実装）

使用例:
    from kabu_client import KabuClient
    cli = KabuClient()
    board = cli.get_board("7203")            # トヨタの板
    ranking = cli.get_ranking_by_turnover()  # 売買代金上位
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# investment-content-auto/.env を優先的に読み込む
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)
else:
    load_dotenv()


class KabuAPIError(RuntimeError):
    """kabuステーションAPI 呼び出しで発生したエラー"""


class KabuClient:
    """kabuステーションAPI の薄いラッパー"""

    def __init__(
        self,
        env: str | None = None,
        host: str | None = None,
        password: str | None = None,
        timeout: int = 10,
    ):
        self.env = (env or os.getenv("KABU_API_ENV", "prod")).lower()
        self.host = host or os.getenv("KABU_API_HOST", "localhost")
        self.timeout = timeout

        if self.env.startswith("prod"):
            self.port = 18080
            self.password = password or os.getenv("KABU_API_PASSWORD_PROD", "")
        else:
            self.port = 18081
            self.password = password or os.getenv("KABU_API_PASSWORD_TEST", "")

        if not self.password or "ここに" in self.password:
            raise KabuAPIError(
                f".env に KABU_API_PASSWORD_{'PROD' if self.env.startswith('prod') else 'TEST'} が設定されていません"
            )

        self.base = f"http://{self.host}:{self.port}/kabusapi"
        self._token: str | None = None
        self._token_ts: float = 0.0

    # ── 認証 ────────────────────────────────────────────
    def _issue_token(self) -> str:
        req = urllib.request.Request(
            f"{self.base}/token",
            data=json.dumps({"APIPassword": self.password}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise KabuAPIError(f"トークン取得失敗 HTTP {e.code}: {e.read().decode(errors='replace')}")
        except urllib.error.URLError as e:
            raise KabuAPIError(
                f"kabuステーションに接続できません ({self.host}:{self.port}): {e.reason}"
            )
        token = body.get("Token")
        if not token:
            raise KabuAPIError(f"トークンが取得できませんでした: {body}")
        self._token = token
        self._token_ts = time.time()
        return token

    def _ensure_token(self) -> str:
        # トークンは発行から24時間有効。安全のため6時間で再取得
        if not self._token or (time.time() - self._token_ts) > 6 * 3600:
            return self._issue_token()
        return self._token

    # ── 汎用リクエスト ──────────────────────────────────
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        token = self._ensure_token()
        url = f"{self.base}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"X-API-KEY": token})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            # 401 → トークン失効。1回だけ再試行
            if e.code == 401:
                self._token = None
                token = self._ensure_token()
                req = urllib.request.Request(url, headers={"X-API-KEY": token})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read())
            raise KabuAPIError(f"GET {path} 失敗 HTTP {e.code}: {e.read().decode(errors='replace')}")
        except urllib.error.URLError as e:
            raise KabuAPIError(f"GET {path} 接続エラー: {e.reason}")

    def _put(self, path: str, payload: dict[str, Any]) -> Any:
        token = self._ensure_token()
        req = urllib.request.Request(
            f"{self.base}/{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-API-KEY": token},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise KabuAPIError(f"PUT {path} 失敗 HTTP {e.code}: {e.read().decode(errors='replace')}")

    # ── 銘柄登録（板PUSH配信用） ────────────────────────
    def register_symbols(self, codes: list[str], exchange: int = 1) -> Any:
        """板情報のPUSH配信対象として銘柄を登録"""
        symbols = [{"Symbol": c, "Exchange": exchange} for c in codes]
        return self._put("register", {"Symbols": symbols})

    def unregister_all(self) -> Any:
        return self._put("unregister/all", {})

    # ── 板情報 ──────────────────────────────────────────
    def get_board(self, code: str, exchange: int = 1) -> dict:
        """板情報取得（exchange: 1=東証, 3=名証, 5=福証, 6=札証）"""
        return self._get(f"board/{code}@{exchange}")

    def get_symbol(self, code: str, exchange: int = 1) -> dict:
        """銘柄マスタ情報取得"""
        return self._get(f"symbol/{code}@{exchange}")

    # ── ランキング ─────────────────────────────────────
    # Type一覧:
    #   1=値上がり率, 2=値下がり率, 3=売買高上位, 4=売買代金上位,
    #   5=TICK回数, 6=売買高急増, 7=売買代金急増,
    #   8=信用売残増, 9=信用売残減, 10=信用買残増, 11=信用買残減,
    #   12=信用高倍率, 13=信用低倍率, 14=業種別値上がり率, 15=業種別値下がり率
    def get_ranking(self, ranking_type: int = 4, exchange_division: str = "ALL") -> list[dict]:
        """
        ランキング取得

        Args:
            ranking_type: 1〜15（デフォルト4=売買代金上位）
            exchange_division: ALL / T(東証) / TP(プライム) / TS(スタンダード) / TG(グロース) / M(名証) / FK(福証) / S(札証)
        """
        body = self._get("ranking", {"Type": ranking_type, "ExchangeDivision": exchange_division})
        return body.get("Ranking", []) if isinstance(body, dict) else []

    def get_ranking_by_turnover(self, exchange_division: str = "ALL") -> list[dict]:
        """売買代金上位ランキング（Type=4）"""
        return self.get_ranking(4, exchange_division)

    def get_ranking_by_volume(self, exchange_division: str = "ALL") -> list[dict]:
        """売買高上位ランキング（Type=3）"""
        return self.get_ranking(3, exchange_division)

    def get_ranking_gainers(self, exchange_division: str = "ALL") -> list[dict]:
        """値上がり率ランキング（Type=1）"""
        return self.get_ranking(1, exchange_division)

    def get_ranking_losers(self, exchange_division: str = "ALL") -> list[dict]:
        """値下がり率ランキング（Type=2）"""
        return self.get_ranking(2, exchange_division)

    # ── 高レベルヘルパ ─────────────────────────────────
    def get_top_turnover_with_board(self, n: int = 15) -> list[dict]:
        """
        売買代金上位n銘柄を取得し、各銘柄の板情報をマージして返す。
        引け後や前場前でランキングのTurnOver/ChangePercentがnullになる問題を回避。
        """
        ranking = self.get_ranking_by_turnover("ALL")[:n]
        result = []
        for r in ranking:
            code = r.get("Symbol")
            if not code:
                continue
            try:
                board = self.get_board(code)
            except KabuAPIError:
                board = {}
            result.append(
                {
                    "rank": r.get("No"),
                    "code": code,
                    "name": r.get("SymbolName"),
                    "price": board.get("CurrentPrice") or r.get("CurrentPrice"),
                    "change_pct": board.get("ChangePreviousClosePer"),
                    "volume": board.get("TradingVolume"),
                    "turnover": board.get("TradingValue"),
                    "vwap": board.get("VWAP"),
                }
            )
        return result


# ── 単体実行テスト ──────────────────────────────────────
if __name__ == "__main__":
    cli = KabuClient()
    print(f"接続先: {cli.host}:{cli.port} (env={cli.env})")

    print("\n[1] トークン取得")
    token = cli._issue_token()
    print(f"  OK: {token[:20]}...")

    print("\n[2] トヨタ (7203) 板情報")
    board = cli.get_board("7203")
    print(f"  {board.get('SymbolName')} ({board.get('Symbol')})")
    print(f"  現在値: {board.get('CurrentPrice')}円  VWAP: {board.get('VWAP')}")
    print(f"  出来高: {board.get('TradingVolume')}  売買代金: {board.get('TradingValue')}")
    s1 = board.get("Sell1") or {}
    b1 = board.get("Buy1") or {}
    print(f"  売1: {s1.get('Price')}x{s1.get('Qty')} / 買1: {b1.get('Price')}x{b1.get('Qty')}")

    print("\n[3] 売買代金上位 TOP15 (板情報マージ版)")
    top = cli.get_top_turnover_with_board(15)
    print(f"  {'順位':>3} {'コード':>5} {'銘柄':<14} {'現在値':>10} {'前日比%':>8} {'売買代金':>12}")
    print("  " + "─" * 65)
    for r in top:
        price = r["price"] or 0
        pct = r["change_pct"] or 0
        to = (r["turnover"] or 0) / 1e8
        name = (r["name"] or "")[:13]
        print(f"  {r['rank']:>3} {r['code']:>5} {name:<14} {price:>9,.1f}円 {pct:>+7.2f}% {to:>9,.0f}億円")
