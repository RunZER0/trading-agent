"""
Live trading agent — a real ReAct agent built on LangGraph.

The agent has access to tools and decides for itself:
- Which assets to look at first
- Which timeframes and indicators to pull
- Whether to check news
- Whether to check existing portfolio positions
- When it has enough information to place or skip a signal
- How many assets to analyse before concluding

It loops (Reason → Act → Observe) until it decides it is done, then stops.
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

from app.agent.tools import LIVE_AGENT_TOOLS
from app.config import settings
from app.dependencies import get_supabase
from app.services.llm import decision_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "market_analyst.md").read_text(encoding="utf-8") + """

## You are an autonomous trading agent with the following tools:
- `get_ohlcv(asset, timeframe, limit)` — fetch candlestick data from the database
- `compute_indicators(asset, timeframe)` — compute RSI, MACD, EMA, Bollinger Bands, ADX, ATR, support/resistance
- `get_news_sentiment(assets)` — fetch recent news headlines and sentiment scores
- `get_portfolio_state()` — see currently open positions
- `get_previous_signals(asset)` — see recent signal history for an asset
- `place_signal(asset, direction, confidence, entry_price, stop_loss, take_profit, position_size_pct, reasoning, agent_run_id)` — emit a trading signal

## Workflow — decide for yourself:
1. Start by checking the portfolio state and recent signals to understand existing exposure
2. For each asset you want to analyse: fetch OHLCV, then compute indicators, optionally check news
3. Reason about the data. If you see a high-confidence setup (>=60), place a signal. Otherwise skip.
4. You do NOT need to analyse every asset — skip assets where the data is clearly not interesting
5. When you are done with all assets, stop. Do not loop unnecessarily.

## Rules:
- Never place a signal with confidence < 60
- Always set a stop_loss and take_profit
- HOLD is a valid conclusion — do not force trades
- Be concise in tool calls — do not repeat the same call twice
"""


# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────

class LiveAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    agent_run_id: str
    assets: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# Nodes
# ─────────────────────────────────────────────────────────────────────────────

llm_with_tools = decision_llm.bind_tools(LIVE_AGENT_TOOLS)


async def agent_node(state: LiveAgentState) -> dict:
    """The LLM reasons and decides which tool to call next (or stops)."""
    response = await llm_with_tools.ainvoke(state["messages"])
    return {"messages": [response]}


def should_continue(state: LiveAgentState) -> str:
    """Route: if the last message has tool calls, execute them. Otherwise end."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


# ─────────────────────────────────────────────────────────────────────────────
# Graph
# ─────────────────────────────────────────────────────────────────────────────

tool_node = ToolNode(LIVE_AGENT_TOOLS)

graph = StateGraph(LiveAgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", tool_node)

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")

trading_agent = graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def run_trading_agent(
    trigger_type: str = "manual",
    assets: list[str] | None = None,
) -> dict[str, Any]:
    """Run the live trading agent. Returns the final state dict."""

    if assets is None:
        assets = list(settings.crypto_symbols) + list(settings.forex_pairs)

    supabase = get_supabase()
    run_record = supabase.table("agent_runs").insert({
        "trigger_type": trigger_type,
        "status": "running",
        "assets_analyzed": assets,
    }).execute()
    run_id = run_record.data[0]["id"] if run_record.data else str(uuid.uuid4())

    user_message = (
        f"Analyse the following assets and generate trading signals where appropriate: "
        f"{', '.join(assets)}. "
        f"Today is {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
        f"Your agent_run_id for place_signal calls is: {run_id}"
    )

    initial_state: LiveAgentState = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ],
        "agent_run_id": run_id,
        "assets": assets,
    }

    logger.info(f"Starting live trading agent run {run_id} for {assets}")
    try:
        final_state = await trading_agent.ainvoke(initial_state)

        signals_placed = sum(
            1 for m in final_state["messages"]
            if isinstance(m, ToolMessage)
            and '"status": "saved"' in str(m.content)
        )

        supabase.table("agent_runs").update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "logs": [
                {"role": m.type, "content": str(m.content)[:500]}
                for m in final_state["messages"]
            ],
        }).eq("id", run_id).execute()

        logger.info(f"Agent run {run_id} completed. Signals placed: {signals_placed}")
        return {"run_id": run_id, "status": "completed", "signals_placed": signals_placed}

    except Exception as e:
        logger.error(f"Agent run {run_id} failed: {e}")
        supabase.table("agent_runs").update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()
        raise

