from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class Indicators(BaseModel):
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None


class MarketContext(BaseModel):
    ticker: str
    candles: List[Candle]
    indicators: Indicators
    current_price: float
    timestamp: datetime


class Signal(BaseModel):
    action: Action
    ticker: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class Position(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float


class AccountInfo(BaseModel):
    account_id: str
    net_liquidation: float
    available_funds: float
    positions: List[Position] = Field(default_factory=list)


class OrderRequest(BaseModel):
    ticker: str
    action: Action
    quantity: int
    order_type: str = "MKT"


class OrderResult(BaseModel):
    order_id: str
    ticker: str
    action: Action
    quantity: int
    status: str


class StrategyConfig(BaseModel):
    tickers: List[str]
    timeframe: str = "1d"
    indicators: List[str] = Field(default_factory=lambda: ["sma_20", "sma_50", "rsi_14", "macd"])
    close_eod: bool = False
    confidence_threshold: float = 0.7
    max_position_pct: float = 0.1
    max_daily_loss_pct: float = 0.02
