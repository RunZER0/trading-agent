"""Pydantic models for trading signals, market data, and agent state."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# -----------------------------------------------
# Enums
# -----------------------------------------------
class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class MarketType(str, Enum):
    CRYPTO = "crypto"
    FOREX = "forex"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TradeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class BacktestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# -----------------------------------------------
# Signal
# -----------------------------------------------
class TradingSignal(BaseModel):
    id: Optional[str] = None
    asset: str
    market_type: MarketType
    timeframe: str = "4h"
    direction: Direction
    confidence: float = Field(ge=0, le=100)
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size_pct: Optional[float] = None
    reasoning: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    agent_run_id: Optional[str] = None
    created_at: Optional[datetime] = None


class SignalCreate(BaseModel):
    """Schema the LLM outputs for a single asset."""
    asset: str
    direction: Direction
    confidence: float = Field(ge=0, le=100)
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size_pct: Optional[float] = None
    reasoning: dict[str, Any] = Field(default_factory=dict)


# -----------------------------------------------
# Market data
# -----------------------------------------------
class OHLCVBar(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class MarketSnapshot(BaseModel):
    id: Optional[str] = None
    asset: str
    market_type: MarketType
    timeframe: str
    ohlcv: list[OHLCVBar]
    indicators: dict[str, Any] = Field(default_factory=dict)
    fetched_at: Optional[datetime] = None


class NewsSentimentItem(BaseModel):
    headline: str
    source: Optional[str] = None
    url: Optional[str] = None
    sentiment_score: Optional[float] = None
    relevance_score: Optional[float] = None
    summary: Optional[str] = None


# -----------------------------------------------
# Risk
# -----------------------------------------------
class RiskConfig(BaseModel):
    id: Optional[str] = None
    max_position_pct: float = 5.0
    max_daily_loss_pct: float = 3.0
    max_open_positions: int = 3
    default_stop_loss_pct: float = 2.0
    default_take_profit_pct: float = 4.0
    min_risk_reward_ratio: float = 2.0
    max_correlated_positions: int = 2
    drawdown_threshold_pct: float = 10.0
    drawdown_reduction_pct: float = 50.0
    updated_at: Optional[datetime] = None


class RiskAssessment(BaseModel):
    can_trade: bool
    reasons: list[str] = Field(default_factory=list)
    adjusted_position_size_pct: Optional[float] = None
    current_exposure_pct: float = 0.0
    daily_pnl_pct: float = 0.0
    open_positions: int = 0


# -----------------------------------------------
# Portfolio & Trades
# -----------------------------------------------
class PortfolioPosition(BaseModel):
    id: Optional[str] = None
    asset: str
    market_type: MarketType
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    updated_at: Optional[datetime] = None


class TradeRecord(BaseModel):
    id: Optional[str] = None
    signal_id: Optional[str] = None
    asset: str
    market_type: MarketType
    direction: Direction
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    status: TradeStatus = TradeStatus.OPEN
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


# -----------------------------------------------
# Agent Run
# -----------------------------------------------
class AgentRun(BaseModel):
    id: Optional[str] = None
    trigger_type: str = "manual"
    status: RunStatus = RunStatus.RUNNING
    assets_analyzed: list[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    logs: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# -----------------------------------------------
# Backtest
# -----------------------------------------------
class BacktestConfig(BaseModel):
    assets: list[str]
    timeframe: str = "1d"
    start_date: str          # ISO format
    end_date: str            # ISO format
    initial_capital: float = 10000.0
    strategy_params: dict[str, Any] = Field(default_factory=dict)


class BacktestTrade(BaseModel):
    asset: str
    direction: Direction
    entry_price: float
    exit_price: float
    entry_time: str
    exit_time: str
    quantity: float
    pnl: float
    pnl_pct: float
    confidence: float
    reasoning: str = ""


class BacktestResult(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    config: BacktestConfig
    status: BacktestStatus = BacktestStatus.PENDING
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    profit_factor: float = 0.0
    trades: list[BacktestTrade] = Field(default_factory=list)
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# -----------------------------------------------
# LLM structured output schemas
# -----------------------------------------------
class MarketAnalysisOutput(BaseModel):
    """Schema for the LLM market analysis step."""
    asset: str
    trend_direction: str = Field(description="bullish, bearish, or neutral")
    trend_strength: float = Field(ge=0, le=100, description="0-100 strength score")
    key_levels: dict[str, float] = Field(
        default_factory=dict,
        description="support_1, support_2, resistance_1, resistance_2"
    )
    patterns_detected: list[str] = Field(
        default_factory=list,
        description="e.g. double bottom, head and shoulders, ascending triangle"
    )
    sentiment_summary: str = Field(description="Summary of news/sentiment impact")
    risk_factors: list[str] = Field(default_factory=list)
    opportunity_score: float = Field(ge=0, le=100)


class SignalGenerationOutput(BaseModel):
    """Schema for the LLM signal generation step."""
    signals: list[SignalCreate]
    overall_market_assessment: str
    reasoning_chain: list[str] = Field(
        description="Step-by-step reasoning that led to the signals"
    )
