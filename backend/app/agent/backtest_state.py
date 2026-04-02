"""Backtest agent state — minimal, just messages + metadata."""
from __future__ import annotations
from typing import Any
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict


class BacktestAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    run_id: str
    config: dict[str, Any]

