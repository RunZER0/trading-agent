"""Agent management API routes."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.agent.graph import run_trading_agent
from app.dependencies import get_supabase

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/run")
async def trigger_agent_run(
    trigger_type: str = "manual",
    assets: Optional[list[str]] = None,
):
    """Trigger a new agent run. Returns immediately with run ID."""
    try:
        # Run in background task
        state = await run_trading_agent(trigger_type=trigger_type, assets=assets)
        return {
            "run_id": state.agent_run_id,
            "status": "completed",
            "signals_generated": len(state.trading_signals),
            "errors": state.errors,
            "signals": [s.model_dump() for s in state.trading_signals],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs")
async def list_agent_runs(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """List agent run history."""
    supabase = get_supabase()
    query = supabase.table("agent_runs").select("*")
    if status:
        query = query.eq("status", status)
    resp = query.order("started_at", desc=True).limit(limit).execute()
    return {"runs": resp.data or []}


@router.get("/runs/{run_id}")
async def get_agent_run(run_id: str):
    """Get details of a specific agent run."""
    supabase = get_supabase()
    resp = supabase.table("agent_runs").select("*").eq("id", run_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Run not found")
    return resp.data[0]
