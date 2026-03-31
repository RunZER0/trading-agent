"""Agent node functions — each step in the LangGraph trading agent."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agent.state import AssetData, TradingAgentState
from app.config import settings
from app.dependencies import get_supabase
from app.models.schemas import (
    Direction,
    MarketAnalysisOutput,
    MarketType,
    SignalGenerationOutput,
)
from app.services.llm import decision_llm, llm_structured_output, workhorse_llm, llm_text
from app.services.market_data import (
    fetch_market_data_for_asset,
    fetch_news_sentiment,
)
from app.services.risk_manager import evaluate_risk
from app.services.technical_analysis import (
    bars_to_dataframe,
    compute_all_indicators,
    compute_support_resistance,
    format_indicators_for_llm,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _log(state: TradingAgentState, node: str, message: str) -> None:
    state.logs.append({
        "node": node,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    logger.info(f"[{node}] {message}")


# -----------------------------------------------
# Node 1: Fetch market data
# -----------------------------------------------

async def fetch_market_data_node(state: TradingAgentState) -> dict[str, Any]:
    """Fetch OHLCV data for all tracked assets."""
    _log(state, "fetch_market_data", f"Fetching data for {len(state.assets)} assets")
    market_data: dict[str, AssetData] = {}

    for asset in state.assets:
        try:
            # Determine market type
            if "/" in asset and any(
                c in asset for c in ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
            ):
                market_type = MarketType.FOREX
            else:
                market_type = MarketType.CRYPTO

            bars, _ = await fetch_market_data_for_asset(asset, market_type, "daily")
            market_data[asset] = AssetData(
                asset=asset,
                market_type=market_type.value,
                bars=bars,
            )
            _log(state, "fetch_market_data", f"  {asset}: {len(bars)} bars fetched")
        except Exception as e:
            state.errors.append(f"Failed to fetch {asset}: {e}")
            _log(state, "fetch_market_data", f"  {asset}: ERROR - {e}")

    return {"market_data": market_data, "logs": state.logs, "errors": state.errors}


# -----------------------------------------------
# Node 2: Compute technical indicators
# -----------------------------------------------

async def compute_technicals_node(state: TradingAgentState) -> dict[str, Any]:
    """Compute indicators for each asset using local ta library (no LLM needed)."""
    _log(state, "compute_technicals", "Computing indicators for all assets")

    for asset, data in state.market_data.items():
        if not data.bars:
            continue
        try:
            df = bars_to_dataframe(data.bars)
            indicators = compute_all_indicators(df)
            levels = compute_support_resistance(df)
            formatted = format_indicators_for_llm(indicators, levels)

            data.indicators = indicators
            data.support_resistance = levels
            data.formatted_analysis = formatted
            _log(state, "compute_technicals", f"  {asset}: indicators computed")
        except Exception as e:
            state.errors.append(f"Indicators failed for {asset}: {e}")
            _log(state, "compute_technicals", f"  {asset}: ERROR - {e}")

    return {"market_data": state.market_data, "logs": state.logs, "errors": state.errors}


# -----------------------------------------------
# Node 3: Fetch news & sentiment
# -----------------------------------------------

async def fetch_news_node(state: TradingAgentState) -> dict[str, Any]:
    """Fetch news sentiment for tracked assets."""
    _log(state, "fetch_news", "Fetching news sentiment")

    # Build ticker list Alpha Vantage understands
    tickers = []
    for asset in state.assets:
        if "/" in asset:
            tickers.append(f"FOREX:{asset.replace('/', '')}")
        else:
            tickers.append(f"CRYPTO:{asset}")

    try:
        items = await fetch_news_sentiment(tickers)
        _log(state, "fetch_news", f"  {len(items)} news items fetched")

        # Summarise news using workhorse model (GPT-5.4 mini, cheap)
        if items:
            news_text = "\n".join(
                f"- [{n.source}] {n.headline} (sentiment: {n.sentiment_score})"
                for n in items[:15]
            )
            summary = await llm_text(
                workhorse_llm,
                "You are a financial news analyst. Summarise the following news items "
                "and their potential market impact in 2-3 paragraphs. Focus on actionable insights.",
                news_text,
            )
        else:
            summary = "No significant news items found for the tracked assets."

        return {
            "news_items": items,
            "news_summary": summary,
            "logs": state.logs,
        }
    except Exception as e:
        state.errors.append(f"News fetch failed: {e}")
        _log(state, "fetch_news", f"  ERROR - {e}")
        return {
            "news_items": [],
            "news_summary": "News data unavailable.",
            "logs": state.logs,
            "errors": state.errors,
        }


# -----------------------------------------------
# Node 4: Analyze market (LLM — GPT-5.4 frontier)
# -----------------------------------------------

async def analyze_market_node(state: TradingAgentState) -> dict[str, Any]:
    """Use GPT-5.4 (frontier) to analyze each asset's data."""
    _log(state, "analyze_market", "Running LLM market analysis (GPT-5.4)")

    system_prompt = _load_prompt("market_analyst.md")
    analyses: list[MarketAnalysisOutput] = []

    for asset, data in state.market_data.items():
        if not data.indicators:
            continue

        user_prompt = (
            f"# Asset: {asset} ({data.market_type})\n\n"
            f"{data.formatted_analysis}\n\n"
            f"## News Context\n{state.news_summary}\n\n"
            f"Analyze this asset and produce a structured MarketAnalysisOutput."
        )

        try:
            analysis = await llm_structured_output(
                decision_llm,
                MarketAnalysisOutput,
                system_prompt,
                user_prompt,
            )
            analysis.asset = asset
            analyses.append(analysis)
            _log(
                state, "analyze_market",
                f"  {asset}: trend={analysis.trend_direction}, "
                f"strength={analysis.trend_strength}, "
                f"opportunity={analysis.opportunity_score}"
            )
        except Exception as e:
            state.errors.append(f"Analysis failed for {asset}: {e}")
            _log(state, "analyze_market", f"  {asset}: ERROR - {e}")

    return {"market_analyses": analyses, "logs": state.logs, "errors": state.errors}


# -----------------------------------------------
# Node 5: Evaluate risk
# -----------------------------------------------

async def evaluate_risk_node(state: TradingAgentState) -> dict[str, Any]:
    """Check risk constraints for each asset (pure logic, no LLM)."""
    _log(state, "evaluate_risk", "Running risk evaluation")

    assessments: dict[str, Any] = {}
    for analysis in state.market_analyses:
        direction = (
            Direction.BUY if analysis.trend_direction == "bullish"
            else Direction.SELL if analysis.trend_direction == "bearish"
            else Direction.HOLD
        )
        try:
            assessment = await evaluate_risk(analysis.asset, direction)
            assessments[analysis.asset] = assessment
            _log(
                state, "evaluate_risk",
                f"  {analysis.asset}: can_trade={assessment.can_trade}, "
                f"reasons={assessment.reasons}"
            )
        except Exception as e:
            state.errors.append(f"Risk eval failed for {analysis.asset}: {e}")
            _log(state, "evaluate_risk", f"  {analysis.asset}: ERROR - {e}")

    return {"risk_assessments": assessments, "logs": state.logs, "errors": state.errors}


# -----------------------------------------------
# Node 6: Generate signals (LLM — GPT-5.4 frontier)
# -----------------------------------------------

async def generate_signal_node(state: TradingAgentState) -> dict[str, Any]:
    """Use GPT-5.4 (frontier) to generate final trading signals."""
    _log(state, "generate_signal", "Generating trading signals (GPT-5.4)")

    system_prompt = _load_prompt("signal_generator.md")

    # Build comprehensive context for the LLM
    analyses_text = ""
    for analysis in state.market_analyses:
        risk = state.risk_assessments.get(analysis.asset)
        risk_text = (
            f"can_trade={risk.can_trade}, reasons={risk.reasons}, "
            f"max_position={risk.adjusted_position_size_pct}%"
            if risk else "No risk data"
        )
        analyses_text += (
            f"\n## {analysis.asset}\n"
            f"- Trend: {analysis.trend_direction} (strength: {analysis.trend_strength}/100)\n"
            f"- Patterns: {', '.join(analysis.patterns_detected) or 'None'}\n"
            f"- Key levels: {json.dumps(analysis.key_levels)}\n"
            f"- Sentiment: {analysis.sentiment_summary}\n"
            f"- Risk factors: {', '.join(analysis.risk_factors) or 'None'}\n"
            f"- Opportunity score: {analysis.opportunity_score}/100\n"
            f"- **Risk Assessment**: {risk_text}\n"
        )

    user_prompt = (
        f"# Market Analysis Summary\n{analyses_text}\n\n"
        f"# News Summary\n{state.news_summary}\n\n"
        "Generate trading signals for each asset. Remember: HOLD is always valid. "
        "Only signal BUY/SELL when confidence ≥ 60 and risk assessment allows it."
    )

    try:
        result = await llm_structured_output(
            decision_llm,
            SignalGenerationOutput,
            system_prompt,
            user_prompt,
        )
        _log(
            state, "generate_signal",
            f"  Generated {len(result.signals)} signals: "
            + ", ".join(f"{s.asset}={s.direction}" for s in result.signals)
        )
        return {
            "trading_signals": result.signals,
            "reasoning_chain": result.reasoning_chain,
            "overall_assessment": result.overall_market_assessment,
            "logs": state.logs,
        }
    except Exception as e:
        state.errors.append(f"Signal generation failed: {e}")
        _log(state, "generate_signal", f"  ERROR - {e}")
        return {
            "trading_signals": [],
            "reasoning_chain": [f"Signal generation failed: {e}"],
            "overall_assessment": "Error in signal generation",
            "logs": state.logs,
            "errors": state.errors,
        }


# -----------------------------------------------
# Node 7: Persist results
# -----------------------------------------------

async def persist_results_node(state: TradingAgentState) -> dict[str, Any]:
    """Save signals and run metadata to Supabase."""
    _log(state, "persist_results", "Saving results to database")
    supabase = get_supabase()

    # Save each signal
    for signal in state.trading_signals:
        asset_data = state.market_data.get(signal.asset)
        market_type = asset_data.market_type if asset_data else "crypto"

        row = {
            "asset": signal.asset,
            "market_type": market_type,
            "timeframe": "4h",
            "direction": signal.direction.value if hasattr(signal.direction, "value") else signal.direction,
            "confidence": signal.confidence,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "position_size_pct": signal.position_size_pct,
            "reasoning": signal.reasoning,
            "agent_run_id": state.agent_run_id,
        }
        try:
            supabase.table("trading_signals").insert(row).execute()
        except Exception as e:
            _log(state, "persist_results", f"  Failed to save signal for {signal.asset}: {e}")

    # Update agent run record
    if state.agent_run_id:
        try:
            supabase.table("agent_runs").update({
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "logs": state.logs,
                "token_usage": state.token_usage,
                "assets_analyzed": state.assets,
            }).eq("id", state.agent_run_id).execute()
        except Exception as e:
            _log(state, "persist_results", f"  Failed to update agent run: {e}")

    _log(state, "persist_results", f"  Saved {len(state.trading_signals)} signals")
    return {"logs": state.logs}
