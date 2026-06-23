from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.exchange.ibkr import IBKRClient
from src.models.types import MarketContext, StrategyConfig
from src.rules.indicators import compute_indicators

logger = logging.getLogger(__name__)


class RuleService:
    def __init__(self, ibkr: IBKRClient):
        self.ibkr = ibkr

    def gather_context(self, ticker: str, strategy: StrategyConfig) -> MarketContext:
        logger.info(f"Gathering market context for {ticker} ({strategy.timeframe})")

        candles = self.ibkr.get_candles(ticker, timeframe=strategy.timeframe)
        if not candles:
            raise ValueError(f"No candle data returned for {ticker}")

        indicators = compute_indicators(candles, strategy.indicators)
        current_price = candles[-1].close

        return MarketContext(
            ticker=ticker,
            candles=candles[-20:],
            indicators=indicators,
            current_price=current_price,
            timestamp=datetime.now(timezone.utc),
        )
