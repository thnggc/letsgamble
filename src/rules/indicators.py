from __future__ import annotations

import pandas as pd
import ta

from src.models.types import Candle, Indicators


def compute_indicators(candles: list[Candle], requested: list[str]) -> Indicators:
    df = pd.DataFrame([c.model_dump() for c in candles])
    result = {}

    if "sma_20" in requested:
        sma = ta.trend.SMAIndicator(df["close"], window=20)
        result["sma_20"] = sma.sma_indicator().iloc[-1]

    if "sma_50" in requested:
        sma = ta.trend.SMAIndicator(df["close"], window=50)
        result["sma_50"] = sma.sma_indicator().iloc[-1]

    if "rsi_14" in requested:
        rsi = ta.momentum.RSIIndicator(df["close"], window=14)
        result["rsi_14"] = rsi.rsi().iloc[-1]

    if "macd" in requested:
        macd = ta.trend.MACD(df["close"])
        result["macd"] = macd.macd().iloc[-1]
        result["macd_signal"] = macd.macd_signal().iloc[-1]
        result["macd_histogram"] = macd.macd_diff().iloc[-1]

    for k, v in result.items():
        if pd.isna(v):
            result[k] = None

    return Indicators(**result)
