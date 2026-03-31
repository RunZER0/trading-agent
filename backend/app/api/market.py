"""Market data API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import get_supabase
from app.models.schemas import MarketType
from app.services.market_data import fetch_market_data_for_asset, fetch_news_sentiment

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/{asset}/snapshot")
async def get_market_snapshot(
    asset: str,
    market_type: str = "crypto",
    timeframe: str = "daily",
):
    """Get latest market snapshot for an asset (fetches live if needed)."""
    mt = MarketType.CRYPTO if market_type == "crypto" else MarketType.FOREX
    bars, _ = await fetch_market_data_for_asset(asset, mt, timeframe)
    return {
        "asset": asset,
        "market_type": market_type,
        "timeframe": timeframe,
        "bars_count": len(bars),
        "latest": bars[-1].model_dump() if bars else None,
        "bars": [b.model_dump() for b in bars[-50:]],  # Last 50 bars
    }


@router.get("/{asset}/history")
async def get_historical_data(
    asset: str,
    timeframe: str = "1d",
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
):
    """Get historical data from Supabase."""
    supabase = get_supabase()
    query = (
        supabase.table("historical_data")
        .select("*")
        .eq("asset", asset)
        .eq("timeframe", timeframe)
    )
    if start_date:
        query = query.gte("timestamp", start_date)
    if end_date:
        query = query.lte("timestamp", end_date)

    resp = query.order("timestamp", desc=True).limit(limit).execute()
    return {"asset": asset, "timeframe": timeframe, "data": resp.data or []}


@router.get("/news")
async def get_market_news(
    tickers: str = Query("BTC,ETH", description="Comma-separated tickers"),
):
    """Get latest news sentiment."""
    ticker_list = [t.strip() for t in tickers.split(",")]
    items = await fetch_news_sentiment(ticker_list)
    return {"items": [i.model_dump() for i in items]}
