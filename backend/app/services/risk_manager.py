"""Risk management engine — validates trades against configurable risk rules."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.dependencies import get_supabase
from app.models.schemas import (
    Direction,
    RiskAssessment,
    RiskConfig,
    TradeStatus,
)

logger = logging.getLogger(__name__)

# Correlated asset groups — positions in the same group count together
CORRELATED_GROUPS: list[set[str]] = [
    {"BTC", "ETH", "SOL"},          # Crypto majors
    {"EUR/USD", "GBP/USD"},          # USD pairs (inversely correlated)
    {"USD/JPY"},                      # JPY pair
]


async def load_risk_config() -> RiskConfig:
    """Load risk configuration from Supabase."""
    supabase = get_supabase()
    resp = supabase.table("risk_config").select("*").limit(1).execute()
    if resp.data:
        return RiskConfig(**resp.data[0])
    return RiskConfig()


async def get_open_positions() -> list[dict[str, Any]]:
    """Get all currently open trades."""
    supabase = get_supabase()
    resp = (
        supabase.table("trade_history")
        .select("*")
        .eq("status", "open")
        .execute()
    )
    return resp.data or []


async def get_daily_pnl() -> float:
    """Calculate today's realised P&L from closed trades."""
    supabase = get_supabase()
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    resp = (
        supabase.table("trade_history")
        .select("pnl")
        .eq("status", "closed")
        .gte("closed_at", today_start)
        .execute()
    )
    return sum(row["pnl"] or 0 for row in (resp.data or []))


async def get_portfolio_value() -> float:
    """Get total portfolio value (sum of positions + cash). Simplified."""
    supabase = get_supabase()
    resp = supabase.table("portfolio").select("*").execute()
    positions = resp.data or []
    return sum(
        (p.get("quantity", 0) * p.get("current_price", 0)) for p in positions
    ) or 10000.0  # Default to 10k if empty


async def get_peak_portfolio_value() -> float:
    """Get peak portfolio value for drawdown calculation.
    Simplified: checks max equity from completed backtest runs or returns current value."""
    return await get_portfolio_value()  # TODO: track equity curve over time


def _find_correlated_group(asset: str) -> set[str] | None:
    """Find which correlation group an asset belongs to."""
    asset_clean = asset.replace("/USD", "").replace("USD/", "")
    for group in CORRELATED_GROUPS:
        if asset in group or asset_clean in group:
            return group
    return None


async def evaluate_risk(
    asset: str,
    direction: Direction,
    proposed_position_pct: float | None = None,
) -> RiskAssessment:
    """Evaluate whether a trade is allowed given current risk parameters.

    Returns a RiskAssessment with can_trade=True/False and reasons.
    """
    config = await load_risk_config()
    open_positions = await get_open_positions()
    daily_pnl = await get_daily_pnl()
    portfolio_value = await get_portfolio_value()
    peak_value = await get_peak_portfolio_value()

    reasons: list[str] = []
    can_trade = True
    adjusted_size = proposed_position_pct or config.max_position_pct

    # --- Rule 1: Max open positions ---
    if len(open_positions) >= config.max_open_positions:
        can_trade = False
        reasons.append(
            f"Max open positions reached ({len(open_positions)}/{config.max_open_positions})"
        )

    # --- Rule 2: Daily loss circuit breaker ---
    daily_pnl_pct = (daily_pnl / portfolio_value * 100) if portfolio_value > 0 else 0
    if daily_pnl_pct <= -config.max_daily_loss_pct:
        can_trade = False
        reasons.append(
            f"Daily loss circuit breaker triggered ({daily_pnl_pct:.2f}% >= "
            f"-{config.max_daily_loss_pct}% limit)"
        )

    # --- Rule 3: Max position size ---
    if adjusted_size > config.max_position_pct:
        adjusted_size = config.max_position_pct
        reasons.append(
            f"Position size capped at {config.max_position_pct}%"
        )

    # --- Rule 4: Correlated asset check ---
    group = _find_correlated_group(asset)
    if group:
        correlated_count = sum(
            1 for p in open_positions
            if _find_correlated_group(p["asset"]) == group
        )
        if correlated_count >= config.max_correlated_positions:
            can_trade = False
            reasons.append(
                f"Max correlated positions reached for group "
                f"{group} ({correlated_count}/{config.max_correlated_positions})"
            )

    # --- Rule 5: Drawdown protection ---
    if peak_value > 0:
        drawdown_pct = ((peak_value - portfolio_value) / peak_value) * 100
        if drawdown_pct >= config.drawdown_threshold_pct:
            reduction = config.drawdown_reduction_pct / 100
            adjusted_size *= (1 - reduction)
            reasons.append(
                f"Drawdown protection active ({drawdown_pct:.1f}% drawdown). "
                f"Position size reduced by {config.drawdown_reduction_pct}%"
            )

    # --- Rule 6: Already have position in this asset ---
    existing = [p for p in open_positions if p["asset"] == asset]
    if existing:
        existing_dir = existing[0].get("direction", "")
        if existing_dir == direction.value:
            reasons.append(f"Already have {direction.value} position in {asset}")
        else:
            reasons.append(
                f"Existing {existing_dir} position in {asset} — "
                f"new {direction.value} would close/reverse"
            )

    # Compute current exposure
    total_exposure = sum(
        abs(p.get("quantity", 0) * p.get("entry_price", 0))
        for p in open_positions
    )
    exposure_pct = (total_exposure / portfolio_value * 100) if portfolio_value > 0 else 0

    if not reasons:
        reasons.append("All risk checks passed")

    return RiskAssessment(
        can_trade=can_trade,
        reasons=reasons,
        adjusted_position_size_pct=round(adjusted_size, 2),
        current_exposure_pct=round(exposure_pct, 2),
        daily_pnl_pct=round(daily_pnl_pct, 2),
        open_positions=len(open_positions),
    )
