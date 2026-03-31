"""Backtesting API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import get_supabase
from app.models.schemas import BacktestConfig
from app.services.backtesting import load_historical_data_for_assets, run_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/run")
async def trigger_backtest(config: BacktestConfig):
    """Run a backtest with the given configuration."""
    try:
        result = await run_backtest(config)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs")
async def list_backtest_runs(limit: int = Query(20, ge=1, le=100)):
    """List backtest run history."""
    supabase = get_supabase()
    resp = (
        supabase.table("backtest_runs")
        .select("id, name, assets, timeframe, start_date, end_date, status, results, created_at")
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


@router.post("/load-data")
async def load_historical_data(
    assets: list[str],
    timeframe: str = "1d",
):
    """Pre-load historical data for backtesting from Alpha Vantage into Supabase."""
    results = await load_historical_data_for_assets(assets, timeframe)
    return {"loaded": results}
