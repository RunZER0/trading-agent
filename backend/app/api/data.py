"""Data management API — fetch, status, and visualization endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from app.dependencies import get_supabase
from app.models.schemas import MarketType
from app.services.data_loader import (
    CRYPTO_ASSETS,
    FOREX_PAIRS,
    get_data_status,
    load_all_historical,
    load_single_asset,
)

router = APIRouter(prefix="/data", tags=["data"])
logger = logging.getLogger(__name__)

# Track ongoing bulk loads
_active_load: dict = {}


class LoadRequest(BaseModel):
    crypto_assets: list[str] = CRYPTO_ASSETS
    forex_pairs: list[str] = FOREX_PAIRS


class SingleAssetRequest(BaseModel):
    asset: str
    market_type: str  # "crypto" or "forex"


@router.get("/status")
async def get_status():
    """Return per-asset historical data availability."""
    return {"assets": get_data_status()}


@router.post("/load-all")
async def load_all(request: LoadRequest, background_tasks: BackgroundTasks):
    """Trigger a full bulk historical data load in background."""
    global _active_load
    if _active_load.get("running"):
        return {"message": "Load already in progress", "running": True}

    _active_load = {"running": True, "started": True}

    async def _run():
        global _active_load
        result = await load_all_historical(
            crypto_assets=request.crypto_assets,
            forex_pairs=request.forex_pairs,
        )
        _active_load = {"running": False, "result": result}
        logger.info(f"Bulk load complete: {result}")

    background_tasks.add_task(_run)
    return {"message": "Bulk historical data load started", "running": True}


@router.get("/load-status")
async def get_load_status():
    """Check if a bulk load is running and get its result."""
    return {
        "running": _active_load.get("running", False),
        "result": _active_load.get("result"),
    }


@router.post("/load-asset")
async def load_asset(request: SingleAssetRequest):
    """Load historical data for a single asset."""
    try:
        mt = MarketType(request.market_type)
    except ValueError:
        raise HTTPException(400, f"Invalid market_type: {request.market_type}")
    result = await load_single_asset(request.asset, mt)
    return result


@router.get("/ohlcv/{asset}")
async def get_ohlcv(
    asset: str,
    timeframe: str = Query("1d"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(500),
):
    """Return stored OHLCV bars for an asset — used for chart visualization."""
    supabase = get_supabase()
    query = (
        supabase.table("historical_data")
        .select("timestamp,open,high,low,close,volume")
        .eq("asset", asset)
        .eq("timeframe", timeframe)
        .order("timestamp")
    )
    if start_date:
        query = query.gte("timestamp", start_date)
    if end_date:
        query = query.lte("timestamp", end_date)
    query = query.limit(limit)
    resp = query.execute()
    bars = resp.data or []
    return {
        "asset": asset,
        "timeframe": timeframe,
        "count": len(bars),
        "bars": bars,
    }
