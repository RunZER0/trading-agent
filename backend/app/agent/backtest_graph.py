"""
Backtest agent — a real ReAct agent built on LangGraph.

The agent has access to tools and decides for itself:
- Which strategies and parameter combinations to test
- Which assets and timeframes to focus on
- How many iterations to run until satisfied with results
- When to stop optimizing (diminishing returns)
- What the final recommendation is

It loops (Reason → Act → Observe) calling run_strategy() as many times
as it wants until it concludes which setup is best.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import Annotated, TypedDict

from app.agent.backtest_state import BacktestAgentState
from app.agent.tools import BACKTEST_AGENT_TOOLS
from app.dependencies import get_supabase
from app.services.llm import decision_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an autonomous quantitative trading strategist and backtest agent.

You have access to these tools:
- `get_ohlcv(asset, timeframe, limit, start_date, end_date)` — inspect raw price data
- `compute_indicators(asset, timeframe)` — get RSI, MACD, EMA, Bollinger Bands, ADX, support/resistance
- `run_strategy(asset, strategy_type, params, start_date, end_date, timeframe, ...)` — simulate a strategy and get performance metrics
- `get_previous_signals(asset)` — see what signals were historically generated

Available strategy types and their parameter schemas:
- ema_crossover:       {"ema_fast": N, "ema_slow": M}  (e.g. 10/20, 8/21, 5/15, 20/50)
- rsi_mean_reversion:  {"period": N, "buy_threshold": X, "sell_threshold": Y}
- macd:                {"ema_fast": N, "ema_slow": M, "signal_period": P}
- bollinger:           {"period": N, "std": X}
- rsi_trend:           {"rsi_buy": X, "rsi_sell": Y, "sma_period": N}

## Your process:
1. First, compute indicators for each asset to understand market regime (trending vs ranging, volatility)
2. Based on market regime, select strategy types that suit the conditions
3. Run strategies with initial parameters
4. Analyse results (sharpe_ratio, max_drawdown_pct, win_rate_pct, profit_factor)
5. For the best-performing strategy family, try 2-4 parameter variants to improve it
6. Keep iterating until: sharpe > 2.0, you've tried enough variants, or results are clearly not improving
7. Conclude with a clear recommendation: best strategy, best params, best asset, and forward-looking advice

## Rules:
- A good strategy has: sharpe_ratio > 1.0, max_drawdown < 25%, win_rate > 45%, profit_factor > 1.3
- Compare strategies fairly across the same date ranges
- Do not run more than 20 strategy simulations total
- Be decisive — conclude when you have enough data
- Your final message (no tool calls) must summarise: best strategy, params, metrics, and recommendation
"""


# ─────────────────────────────────────────────────────────────────────────────
# Nodes
# ─────────────────────────────────────────────────────────────────────────────

llm_with_tools = decision_llm.bind_tools(BACKTEST_AGENT_TOOLS)


async def agent_node(state: BacktestAgentState) -> dict:
    """The LLM reasons and decides which tool to call next (or concludes)."""
    response = await llm_with_tools.ainvoke(state["messages"])
    return {"messages": [response]}


def should_continue(state: BacktestAgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


# ─────────────────────────────────────────────────────────────────────────────
# Graph
# ─────────────────────────────────────────────────────────────────────────────

tool_node = ToolNode(BACKTEST_AGENT_TOOLS)

graph = StateGraph(BacktestAgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", tool_node)

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")

backtest_agent = graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def run_backtest_agent(config: dict[str, Any], run_id: str | None = None) -> dict[str, Any]:
    """Run the backtest agent. config keys: assets, timeframe, start_date,
    end_date, initial_capital, position_size_pct, stop_loss_pct,
    take_profit_pct, notes."""

    run_id = run_id or str(uuid.uuid4())
    supabase = get_supabase()

    # Create run record
    supabase.table("backtest_runs").insert({
        "id": run_id,
        "name": f"Agent Backtest {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        "assets": config.get("assets", []),
        "timeframe": config.get("timeframe", "1d"),
        "start_date": config.get("start_date"),
        "end_date": config.get("end_date"),
        "initial_capital": config.get("initial_capital", 10000),
        "status": "running",
        "config": config,
    }).execute()

    user_message = (
        f"Run a full strategy backtest and optimization for the following configuration:\n"
        f"{json.dumps(config, indent=2)}\n\n"
        f"Analyse each asset's market regime first, then test and optimize strategies. "
        f"Conclude with your best recommendation."
    )

    initial_state: BacktestAgentState = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ],
        "run_id": run_id,
        "config": config,
    }

    logger.info(f"Starting backtest agent run {run_id}")
    try:
        final_state = await backtest_agent.ainvoke(initial_state)

        # Extract final conclusion (last AI message without tool calls)
        conclusion = ""
        tool_calls_made = 0
        strategies_tested = []
        best_metrics = {}

        for m in final_state["messages"]:
            if isinstance(m, AIMessage):
                if not m.tool_calls and m.content:
                    conclusion = str(m.content)
                if m.tool_calls:
                    tool_calls_made += len(m.tool_calls)
            if isinstance(m, ToolMessage) and m.content:
                try:
                    data = json.loads(str(m.content))
                    if "strategy" in data and "total_return_pct" in data:
                        strategies_tested.append(data)
                        # Track best by sharpe
                        if not best_metrics or data.get("sharpe_ratio", 0) > best_metrics.get("sharpe_ratio", 0):
                            best_metrics = data
                except Exception:
                    pass

        # Build equity curve from best result if available
        equity_curve = best_metrics.get("equity_curve_sample", [])
        trades = best_metrics.get("trades", [])

        supabase.table("backtest_runs").update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "results": {
                "conclusion": conclusion,
                "tool_calls_made": tool_calls_made,
                "strategies_tested": len(strategies_tested),
                "best_strategy": best_metrics.get("strategy"),
                "best_params": best_metrics.get("params"),
                "best_asset": best_metrics.get("asset"),
                "best_metrics": {
                    k: best_metrics.get(k)
                    for k in ["total_return_pct", "sharpe_ratio", "max_drawdown_pct",
                              "win_rate_pct", "total_trades", "profit_factor"]
                } if best_metrics else {},
                "all_results": [
                    {k: r.get(k) for k in ["asset", "strategy", "params", "total_return_pct",
                                           "sharpe_ratio", "max_drawdown_pct", "win_rate_pct",
                                           "total_trades", "profit_factor"]}
                    for r in strategies_tested
                ],
                "recommendations": conclusion,
            },
            "equity_curve": equity_curve,
            "trades": trades,
            "logs": [{"role": m.type, "content": str(m.content)[:300]}
                     for m in final_state["messages"]],
        }).eq("id", run_id).execute()

        logger.info(f"Backtest agent {run_id} done. {len(strategies_tested)} strategies tested.")
        return {
            "run_id": run_id,
            "status": "completed",
            "strategies_tested": len(strategies_tested),
            "best_strategy": best_metrics.get("strategy"),
            "best_sharpe": best_metrics.get("sharpe_ratio"),
        }

    except Exception as e:
        logger.error(f"Backtest agent {run_id} failed: {e}")
        supabase.table("backtest_runs").update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "results": {"error": str(e)},
        }).eq("id", run_id).execute()
        raise

