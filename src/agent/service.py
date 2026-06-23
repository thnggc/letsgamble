from __future__ import annotations

import json
import logging

import anthropic

from src.models.types import Action, MarketContext, Signal

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a quantitative trading analyst. You receive market data including candlestick history and technical indicators for a stock. Your job is to analyze the data and produce a trading signal.

Consider:
- Price trends and momentum from the candlestick data
- Technical indicator readings (SMA crossovers, RSI overbought/oversold, MACD divergence)
- Volume patterns
- Risk/reward ratio of the potential trade

You MUST call the `trading_signal` tool with your analysis. Be decisive — if the data is ambiguous, output HOLD with your reasoning."""

SIGNAL_TOOL = {
    "name": "trading_signal",
    "description": "Submit a trading signal based on market analysis",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["BUY", "SELL", "HOLD"],
                "description": "The trading action to take",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Confidence level from 0.0 to 1.0",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of the analysis and decision",
            },
        },
        "required": ["action", "confidence", "reasoning"],
    },
}


def _format_context(ctx: MarketContext) -> str:
    recent = ctx.candles[-10:]
    candle_lines = []
    for c in recent:
        candle_lines.append(
            f"  {c.timestamp.strftime('%Y-%m-%d %H:%M')} | "
            f"O:{c.open:.2f} H:{c.high:.2f} L:{c.low:.2f} C:{c.close:.2f} V:{c.volume}"
        )

    indicators = ctx.indicators.model_dump(exclude_none=True)
    ind_lines = [f"  {k}: {v:.4f}" for k, v in indicators.items()]

    return f"""Ticker: {ctx.ticker}
Current Price: {ctx.current_price:.2f}
Timestamp: {ctx.timestamp.isoformat()}

Recent Candles (last 10):
{chr(10).join(candle_lines)}

Technical Indicators:
{chr(10).join(ind_lines) if ind_lines else "  (none computed)"}"""


class ClaudeAgent:
    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic()
        self.model = model

    def analyze(self, context: MarketContext) -> Signal:
        logger.info(f"Sending {context.ticker} to Claude for analysis")
        formatted = _format_context(context)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=[SIGNAL_TOOL],
            tool_choice={"type": "tool", "name": "trading_signal"},
            messages=[{"role": "user", "content": formatted}],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "trading_signal":
                tool_input = block.input
                signal = Signal(
                    action=Action(tool_input["action"]),
                    ticker=context.ticker,
                    confidence=tool_input["confidence"],
                    reasoning=tool_input["reasoning"],
                )
                logger.info(
                    f"Claude signal for {context.ticker}: "
                    f"{signal.action.value} (confidence: {signal.confidence:.2f})"
                )
                return signal

        raise RuntimeError("Claude did not return a trading_signal tool call")
