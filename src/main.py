from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.agent.service import ClaudeAgent
from src.evaluation.service import EvalService
from src.exchange.ibkr import IBKRClient
from src.models.types import StrategyConfig

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_strategies(path: str = "config/strategies.yaml") -> dict[str, StrategyConfig]:
    with open(path) as f:
        raw = yaml.safe_load(f)

    strategies = {}
    for name, cfg in raw["strategies"].items():
        strategies[name] = StrategyConfig(**cfg)
    return strategies


def run_strategy(
    strategy_name: str,
    strategy: StrategyConfig,
    ibkr: IBKRClient,
    agent: ClaudeAgent,
    eval_service: EvalService,
):
    logger.info(f"=== Running strategy: {strategy_name} ===")
    from src.rules.service import RuleService

    rule_service = RuleService(ibkr)
    account = ibkr.get_account()
    logger.info(
        f"Account: NLV=${account.net_liquidation:,.2f}, "
        f"Available=${account.available_funds:,.2f}, "
        f"Positions={len(account.positions)}"
    )

    for ticker in strategy.tickers:
        try:
            context = rule_service.gather_context(ticker, strategy)
            signal = agent.analyze(context)
            result = eval_service.evaluate_and_execute(signal, strategy, account)
            if result:
                logger.info(f"{ticker}: Order {result.status} (ID: {result.order_id})")
        except Exception:
            logger.exception(f"Error processing {ticker}")


def run_eod(ibkr: IBKRClient, strategies: dict[str, StrategyConfig]):
    logger.info("=== End-of-day cleanup ===")
    eval_service = EvalService(ibkr)
    eod_strategies = {k: v for k, v in strategies.items() if v.close_eod}
    if eod_strategies:
        results = eval_service.close_eod_positions()
        for r in results:
            logger.info(f"Closed: {r.action.value} {r.quantity} {r.ticker} -> {r.status}")
    else:
        logger.info("No strategies with close_eod enabled")


def main():
    parser = argparse.ArgumentParser(description="letsgamble trading bot")
    parser.add_argument(
        "--strategy",
        default=None,
        help="Run a specific strategy (default: all)",
    )
    parser.add_argument(
        "--eod",
        action="store_true",
        help="Run end-of-day position cleanup",
    )
    parser.add_argument(
        "--config",
        default="config/strategies.yaml",
        help="Path to strategies config file",
    )
    parser.add_argument(
        "--gateway-url",
        default=None,
        help="IBKR gateway URL (overrides env)",
    )
    parser.add_argument(
        "--account-id",
        default=None,
        help="IBKR account ID (overrides env)",
    )
    args = parser.parse_args()

    import os

    gateway_url = args.gateway_url or os.environ.get("IBKR_GATEWAY_URL", "https://localhost:5000")
    account_id = args.account_id or os.environ.get("IBKR_ACCOUNT_ID")
    if not account_id:
        logger.error("IBKR_ACCOUNT_ID not set. Pass --account-id or set env var.")
        sys.exit(1)

    ibkr = IBKRClient(gateway_url, account_id)
    if not ibkr.ping():
        logger.error(f"Cannot connect to IBKR Gateway at {gateway_url}. Is it running?")
        sys.exit(1)

    strategies = load_strategies(args.config)

    if args.eod:
        run_eod(ibkr, strategies)
        return

    agent = ClaudeAgent()
    eval_service = EvalService(ibkr)

    if args.strategy:
        if args.strategy not in strategies:
            logger.error(f"Strategy '{args.strategy}' not found. Available: {list(strategies.keys())}")
            sys.exit(1)
        run_strategy(args.strategy, strategies[args.strategy], ibkr, agent, eval_service)
    else:
        for name, strategy in strategies.items():
            run_strategy(name, strategy, ibkr, agent, eval_service)

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
