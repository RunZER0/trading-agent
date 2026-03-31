"""Portfolio API routes."""

from __future__ import annotations

from fastapi import APIRouter
from app.dependencies import get_supabase

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("")
async def get_portfolio():
    """Get current portfolio positions."""
    supabase = get_supabase()
    resp = supabase.table("portfolio").select("*").execute()
    positions = resp.data or []
    total_value = sum(
        p.get("quantity", 0) * p.get("current_price", 0) for p in positions
    )
    total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)
    return {
        "positions": positions,
        "total_value": round(total_value, 2),
        "total_unrealized_pnl": round(total_pnl, 2),
    }


@router.get("/trades")
async def get_trade_history(
    status: str | None = None,
    asset: str | None = None,
    limit: int = 50,
):
    """Get trade history."""
    supabase = get_supabase()
    query = supabase.table("trade_history").select("*")
    if status:
        query = query.eq("status", status)
    if asset:
        query = query.eq("asset", asset)
    resp = query.order("opened_at", desc=True).limit(limit).execute()
    return {"trades": resp.data or []}


@router.get("/pnl")
async def get_pnl_summary():
    """Get P&L summary."""
    supabase = get_supabase()

    # Closed trades P&L
    closed = (
        supabase.table("trade_history")
        .select("pnl, pnl_pct, asset, closed_at")
        .eq("status", "closed")
        .order("closed_at", desc=True)
        .limit(100)
        .execute()
    )

    trades = closed.data or []
    total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)
    winning = [t for t in trades if (t.get("pnl", 0) or 0) > 0]
    losing = [t for t in trades if (t.get("pnl", 0) or 0) <= 0]

    return {
        "total_realized_pnl": round(total_pnl, 2),
        "total_trades": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round(len(winning) / len(trades) * 100, 1) if trades else 0,
        "recent_trades": trades[:10],
    }
