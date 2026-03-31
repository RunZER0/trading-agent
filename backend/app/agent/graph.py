"""LangGraph agent definition — the trading agent's brain."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    analyze_market_node,
    compute_technicals_node,
    evaluate_risk_node,
    fetch_market_data_node,
    fetch_news_node,
    generate_signal_node,
    persist_results_node,
)
from app.agent.state import TradingAgentState
from app.config import settings
from app.dependencies import get_supabase

logger = logging.getLogger(__name__)


def _should_generate_signals(state: TradingAgentState) -> str:
    """Conditional edge: skip signal generation if no analyses available."""
    if not state.market_analyses:
        return "persist_results"
    return "evaluate_risk"


def build_trading_graph() -> StateGraph:
    """Build and compile the LangGraph trading agent.

    Graph flow:
        START
          ├─→ fetch_market_data
          │       ├─→ compute_technicals ─┐
          │       └─→ fetch_news ─────────┤
          │                               ▼
          │                        analyze_market
          │                               │
          │                    (conditional: has analyses?)
          │                        ┌──────┴──────┐
          │                        ▼              ▼
          │                  evaluate_risk    persist_results
          │                        │              │
          │                        ▼              │
          │                  generate_signal      │
          │                        │              │
          │                        ▼              │
          │                  persist_results ◄────┘
          │                        │
          └────────────────────── END
    """
    graph = StateGraph(TradingAgentState)

    # Add nodes
    graph.add_node("fetch_market_data", fetch_market_data_node)
    graph.add_node("compute_technicals", compute_technicals_node)
    graph.add_node("fetch_news", fetch_news_node)
    graph.add_node("analyze_market", analyze_market_node)
    graph.add_node("evaluate_risk", evaluate_risk_node)
    graph.add_node("generate_signal", generate_signal_node)
    graph.add_node("persist_results", persist_results_node)

    # Edges
    graph.add_edge(START, "fetch_market_data")
    graph.add_edge("fetch_market_data", "compute_technicals")
    graph.add_edge("fetch_market_data", "fetch_news")
    graph.add_edge("compute_technicals", "analyze_market")
    graph.add_edge("fetch_news", "analyze_market")

    # Conditional: only generate signals if we have analyses
    graph.add_conditional_edges(
        "analyze_market",
        _should_generate_signals,
        {"evaluate_risk": "evaluate_risk", "persist_results": "persist_results"},
    )
    graph.add_edge("evaluate_risk", "generate_signal")
    graph.add_edge("generate_signal", "persist_results")
    graph.add_edge("persist_results", END)

    return graph


# Compiled graph (singleton)
trading_agent = build_trading_graph().compile()


async def run_trading_agent(
    trigger_type: str = "manual",
    assets: list[str] | None = None,
) -> TradingAgentState:
    """Execute the full trading agent pipeline.

    Args:
        trigger_type: "manual", "scheduled", or "backtest"
        assets: override asset list (defaults to config)

    Returns:
        Final agent state with signals and metadata.
    """
    # Build asset list
    if assets is None:
        assets = []
        for sym in settings.crypto_symbols:
            assets.append(sym)
        for pair in settings.forex_pairs:
            assets.append(pair)

    # Create agent run record in Supabase
    supabase = get_supabase()
    run_record = supabase.table("agent_runs").insert({
        "trigger_type": trigger_type,
        "status": "running",
        "assets_analyzed": assets,
    }).execute()

    run_id = run_record.data[0]["id"] if run_record.data else None

    # Build initial state
    initial_state = TradingAgentState(
        assets=assets,
        trigger_type=trigger_type,
        agent_run_id=run_id,
    )

    logger.info(f"Starting trading agent run {run_id} for {assets}")

    try:
        # Execute the graph
        final_state = await trading_agent.ainvoke(initial_state)

        # Convert back to our state model if needed
        if isinstance(final_state, dict):
            final_state = TradingAgentState(**final_state)

        logger.info(
            f"Agent run {run_id} completed. "
            f"Signals: {len(final_state.trading_signals)}, "
            f"Errors: {len(final_state.errors)}"
        )
        return final_state

    except Exception as e:
        logger.error(f"Agent run {run_id} failed: {e}")
        # Mark run as failed
        if run_id:
            supabase.table("agent_runs").update({
                "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": str(e),
            }).eq("id", run_id).execute()
        raise
