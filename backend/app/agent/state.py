"""LangGraph agent state definition."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.schemas import (
    MarketAnalysisOutput,
    NewsSentimentItem,
    OHLCVBar,
    RiskAssessment,
    SignalCreate,
)


class AssetData(BaseModel):
    """Market data + indicators for a single asset."""
    asset: str
    market_type: str  # "crypto" or "forex"
    bars: list[OHLCVBar] = Field(default_factory=list)
    indicators: dict[str, Any] = Field(default_factory=dict)
    support_resistance: dict[str, list[float]] = Field(default_factory=dict)
    formatted_analysis: str = ""  # Human-readable indicator summary for LLM


class TradingAgentState(BaseModel):
    """State that flows through the LangGraph agent."""

    # --- Input ---
    assets: list[str] = Field(default_factory=list)
    trigger_type: str = "manual"  # "scheduled" | "manual" | "backtest"

    # --- Data collection ---
    market_data: dict[str, AssetData] = Field(default_factory=dict)
    news_items: list[NewsSentimentItem] = Field(default_factory=list)
    news_summary: str = ""

    # --- Analysis ---
    market_analyses: list[MarketAnalysisOutput] = Field(default_factory=list)

    # --- Risk ---
    risk_assessments: dict[str, RiskAssessment] = Field(default_factory=dict)

    # --- Output ---
    trading_signals: list[SignalCreate] = Field(default_factory=list)
    reasoning_chain: list[str] = Field(default_factory=list)
    overall_assessment: str = ""

    # --- Metadata ---
    agent_run_id: Optional[str] = None
    logs: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: dict[str, Any] = Field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_cost": 0.0}
    )
    errors: list[str] = Field(default_factory=list)
