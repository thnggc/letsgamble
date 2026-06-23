import logging
from typing import List, Optional

from src.models.types import (
    AccountInfo,
    Action,
    OrderRequest,
    OrderResult,
    Signal,
    StrategyConfig,
)
from src.exchange.ibkr import IBKRClient

logger = logging.getLogger(__name__)


class EvalService:
    def __init__(self, ibkr: IBKRClient):
        self.ibkr = ibkr

    def evaluate_and_execute(
        self, signal: Signal, strategy: StrategyConfig, account: AccountInfo
    ) -> Optional[OrderResult]:
        if signal.action == Action.HOLD:
            logger.info(f"{signal.ticker}: HOLD — no action taken. Reason: {signal.reasoning}")
            return None

        if signal.confidence < strategy.confidence_threshold:
            logger.info(
                f"{signal.ticker}: {signal.action.value} signal rejected — "
                f"confidence {signal.confidence:.2f} below threshold {strategy.confidence_threshold}"
            )
            return None

        existing = next((p for p in account.positions if p.ticker == signal.ticker), None)
        if signal.action == Action.SELL and not existing:
            logger.info(f"{signal.ticker}: SELL signal but no position held — skipping")
            return None

        if signal.action == Action.BUY and existing and existing.quantity > 0:
            logger.info(f"{signal.ticker}: BUY signal but already holding — skipping")
            return None

        quantity = self._calculate_quantity(signal, strategy, account)
        if quantity <= 0:
            logger.info(f"{signal.ticker}: Calculated quantity is 0 — skipping")
            return None

        if signal.action == Action.SELL and existing:
            quantity = abs(int(existing.quantity))

        order = OrderRequest(
            ticker=signal.ticker,
            action=signal.action,
            quantity=quantity,
        )

        logger.info(f"Executing: {order.action.value} {order.quantity} {order.ticker}")
        return self.ibkr.place_order(order)

    def _calculate_quantity(
        self, signal: Signal, strategy: StrategyConfig, account: AccountInfo
    ) -> int:
        max_allocation = account.net_liquidation * strategy.max_position_pct
        max_from_available = account.available_funds * 0.95

        allocation = min(max_allocation, max_from_available)
        if allocation <= 0:
            return 0

        current_position = next(
            (p for p in account.positions if p.ticker == signal.ticker), None
        )
        price = current_position.avg_cost if current_position else allocation / 100

        try:
            candles = self.ibkr.get_candles(signal.ticker, timeframe="1d", bar_count=1)
            if candles:
                price = candles[-1].close
        except Exception:
            logger.warning(f"Could not fetch current price for {signal.ticker}, using estimate")

        if price <= 0:
            return 0

        return int(allocation / price)

    def close_eod_positions(self) -> List[OrderResult]:
        logger.info("End-of-day: closing all positions")
        return self.ibkr.close_all_positions()
