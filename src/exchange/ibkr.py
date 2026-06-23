from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from src.models.types import AccountInfo, Candle, OrderRequest, OrderResult, Position

logger = logging.getLogger(__name__)

TIMEFRAME_MAP = {
    "1m": ("1min", "1d"),
    "5m": ("5min", "2d"),
    "15m": ("15min", "5d"),
    "1h": ("1hour", "20d"),
    "1d": ("1day", "365d"),
}


class IBKRClient:
    def __init__(self, gateway_url: str, account_id: str):
        self.gateway_url = gateway_url.rstrip("/")
        self.account_id = account_id
        self._client = httpx.Client(verify=False, timeout=30.0)

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        url = f"{self.gateway_url}{path}"
        resp = self._client.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def ping(self) -> bool:
        try:
            self._request("POST", "/v1/api/tickle")
            return True
        except httpx.HTTPError:
            return False

    def reauthenticate(self) -> None:
        self._request("POST", "/v1/api/iserver/reauthenticate")

    def get_conid(self, ticker: str) -> int:
        results = self._request(
            "GET",
            "/v1/api/iserver/secdef/search",
            params={"symbol": ticker, "secType": "STK"},
        )
        if not results:
            raise ValueError(f"No contract found for {ticker}")
        return results[0]["conid"]

    def get_candles(self, ticker: str, timeframe: str = "1d", bar_count: int = 100) -> list[Candle]:
        conid = self.get_conid(ticker)
        bar_size, period = TIMEFRAME_MAP.get(timeframe, ("1day", "365d"))

        data = self._request(
            "GET",
            f"/v1/api/iserver/marketdata/history",
            params={
                "conid": conid,
                "period": period,
                "bar": bar_size,
                "outsideRth": False,
            },
        )

        candles = []
        for bar in data.get("data", [])[-bar_count:]:
            candles.append(
                Candle(
                    timestamp=datetime.fromtimestamp(bar["t"] / 1000, tz=timezone.utc),
                    open=bar["o"],
                    high=bar["h"],
                    low=bar["l"],
                    close=bar["c"],
                    volume=int(bar["v"]),
                )
            )
        return candles

    def get_account(self) -> AccountInfo:
        summary = self._request("GET", f"/v1/api/portfolio/{self.account_id}/summary")
        positions = self.get_positions()

        return AccountInfo(
            account_id=self.account_id,
            net_liquidation=summary.get("netliquidation", {}).get("amount", 0),
            available_funds=summary.get("availablefunds", {}).get("amount", 0),
            positions=positions,
        )

    def get_positions(self) -> list[Position]:
        data = self._request("GET", f"/v1/api/portfolio/{self.account_id}/positions/0")
        positions = []
        for pos in data:
            if pos.get("position", 0) == 0:
                continue
            positions.append(
                Position(
                    ticker=pos.get("ticker", pos.get("contractDesc", "UNKNOWN")),
                    quantity=pos["position"],
                    avg_cost=pos.get("avgCost", 0),
                    market_value=pos.get("mktValue", 0),
                    unrealized_pnl=pos.get("unrealizedPnl", 0),
                )
            )
        return positions

    def place_order(self, order: OrderRequest) -> OrderResult:
        conid = self.get_conid(order.ticker)

        order_payload = {
            "orders": [
                {
                    "conid": conid,
                    "orderType": order.order_type,
                    "side": order.action.value,
                    "quantity": order.quantity,
                    "tif": "DAY",
                }
            ]
        }

        result = self._request(
            "POST",
            f"/v1/api/iserver/account/{self.account_id}/orders",
            json=order_payload,
        )

        if isinstance(result, list) and result and result[0].get("id"):
            reply_id = result[0]["id"]
            self._request(
                "POST",
                f"/v1/api/iserver/reply/{reply_id}",
                json={"confirmed": True},
            )
            result = self._request(
                "POST",
                f"/v1/api/iserver/account/{self.account_id}/orders",
                json=order_payload,
            )

        order_id = "unknown"
        status = "submitted"
        if isinstance(result, list) and result:
            order_id = str(result[0].get("order_id", result[0].get("id", "unknown")))
            status = result[0].get("order_status", "submitted")

        logger.info(f"Order placed: {order.action.value} {order.quantity} {order.ticker} -> {status}")
        return OrderResult(
            order_id=order_id,
            ticker=order.ticker,
            action=order.action,
            quantity=order.quantity,
            status=status,
        )

    def close_all_positions(self) -> list[OrderResult]:
        positions = self.get_positions()
        results = []
        for pos in positions:
            action = "SELL" if pos.quantity > 0 else "BUY"
            order = OrderRequest(
                ticker=pos.ticker,
                action=action,
                quantity=abs(int(pos.quantity)),
            )
            result = self.place_order(order)
            results.append(result)
        return results
