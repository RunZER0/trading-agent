"""Trading signals API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import get_supabase
from app.models.schemas import TradingSignal

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
async def list_signals(
    asset: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    market_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List trading signals with optional filters."""
    supabase = get_supabase()
    query = supabase.table("trading_signals").select("*")

    if asset:
        query = query.eq("asset", asset)
    if direction:
        query = query.eq("direction", direction)
    if market_type:
        query = query.eq("market_type", market_type)

    resp = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return {"signals": resp.data or [], "count": len(resp.data or [])}


@router.get("/{signal_id}")
async def get_signal(signal_id: str):
    """Get a single signal by ID."""
    supabase = get_supabase()
    resp = supabase.table("trading_signals").select("*").eq("id", signal_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Signal not found")
    return resp.data[0]
