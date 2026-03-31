"""Agent-driven backtesting state definitions."""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class StrategySpec(BaseModel):
    """A trading strategy specification to be tested."""
    name: str
    description: str
    entry_rules: dict[str, Any]   # indicator thresholds/conditions
    exit_rules: dict[str, Any]
    params: dict[str, Any] = Field(default_factory=dict)


class StrategyResult(BaseModel):
    """Performance result for a single strategy on a single asset."""
    strategy_name: str
    asset: str
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    profit_factor: float = 0.0
    avg_trade_duration_days: float = 0.0
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    trades: list[dict[str, Any]] = Field(default_factory=list)


class BacktestAgentState(BaseModel):
    """Full state carried through the agent-driven backtest graph."""
    run_id: str
    config: dict[str, Any]  # user-provided BacktestAgentConfig

    # Data
    historical_data: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    indicators: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Strategy selection
    strategies: list[StrategySpec] = Field(default_factory=list)
    strategy_selection_reasoning: str = ""

    # Results
    strategy_results: list[StrategyResult] = Field(default_factory=list)
    best_strategy: Optional[StrategySpec] = None
    best_result: Optional[StrategyResult] = None
    ranking_analysis: str = ""
    recommendations: str = ""

    # Meta
    logs: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    completed: bool = False
