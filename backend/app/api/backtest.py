"""Backtesting API routes — supports both standard and agent-driven mode."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from app.agent.backtest_graph import run_backtest_agent
from app.dependencies import get_supabase
from app.models.schemas import BacktestConfig
from app.services.backtesting import run_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])


# ──────────────────────────────────────────────────────────────────────────────
# Agent-driven backtest request schema
# ──────────────────────────────────────────────────────────────────────────────

class BacktestAgentRequest(BaseModel):
    assets: list[str]
    timeframe: str = "1d"
    start_date: str = "2024-01-01"
    end_date: str = datetime.now().strftime("%Y-%m-%d")
    initial_capital: float = 10000.0
    position_size_pct: float = 5.0
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0
    notes: str = ""  # Any extra instructions for the agent


# ──────────────────────────────────────────────────────────────────────────────
# Agent-driven backtest (NEW — main endpoint)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/agent-run")
async def trigger_agent_backtest(
    request: BacktestAgentRequest,
    background_tasks: BackgroundTasks,
):
    """Start an agent-driven backtest that autonomously discovers the best strategy.
    
    The agent:
    1. Loads historical data from Supabase
    2. Computes indicators
    3. GPT-5.4-mini selects strategies to test
    4. Simulates each strategy
    5. GPT-5.4 ranks results and writes a strategy recommendation
    """
    run_id = str(uuid.uuid4())
    supabase = get_supabase()

    async def _run_in_background():
        try:
            await run_backtest_agent(request.model_dump(), run_id=run_id)
        except Exception as e:
            supabase.table("backtest_runs").update({
                "status": "failed",
                "results": {"error": str(e)},
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()

    background_tasks.add_task(_run_in_background)
    return {"run_id": run_id, "status": "running", "message": "Agent backtest started"}


@router.post("/agent-run-sync")
async def trigger_agent_backtest_sync(request: BacktestAgentRequest):
    """Synchronous agent backtest — waits for completion (use for smaller date ranges)."""
    run_id = str(uuid.uuid4())
    try:
        result = await run_backtest_agent(request.model_dump(), run_id=run_id)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


# ──────────────────────────────────────────────────────────────────────────────
# List & retrieve runs
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/runs")
async def list_backtest_runs(limit: int = Query(20, ge=1, le=100)):
    """List backtest run history."""
    supabase = get_supabase()
    resp = (
        supabase.table("backtest_runs")
        .select("id, name, assets, timeframe, start_date, end_date, status, results, initial_capital, created_at, completed_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"runs": resp.data or []}


@router.get("/runs/{run_id}")
async def get_backtest_run(run_id: str):
    """Get full backtest results including trades and equity curve."""
    supabase = get_supabase()
    resp = supabase.table("backtest_runs").select("*").eq("id", run_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return resp.data[0]


@router.get("/runs/{run_id}/strategies")
async def get_strategy_results(run_id: str):
    """Get per-strategy performance results for a run."""
    supabase = get_supabase()
    resp = supabase.table("backtest_runs").select("results").eq("id", run_id).execute()
    if not resp.data:
        raise HTTPException(404, "Run not found")
    results = resp.data[0].get("results") or {}
    return {"strategy_results": results.get("strategy_results", [])}


# ──────────────────────────────────────────────────────────────────────────────
# Legacy simple backtest (kept for compatibility)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/run")
async def trigger_backtest(config: BacktestConfig):
    """Standard (non-agent) backtest using pre-defined parameters."""
    try:
        result = await run_backtest(config)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
