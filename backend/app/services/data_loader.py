"""Bulk historical data loader — fetches from Alpha Vantage with full output,
stores/upserts into Supabase historical_data table, and reports progress."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.dependencies import get_supabase
from app.models.schemas import MarketType, OHLCVBar
from app.services.market_data import (
    fetch_crypto_daily,
    fetch_forex_daily,
    _rate_limited_get,
)

logger = logging.getLogger(__name__)

# Supported assets for backtesting
CRYPTO_ASSETS = ["BTC", "ETH", "SOL", "BNB", "ADA"]
FOREX_PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD"]


# -----------------------------------------------
# Full-output fetchers (for maximum historical depth)
# -----------------------------------------------

async def fetch_crypto_full(symbol: str, market: str = "USD") -> list[OHLCVBar]:
    """Fetch full daily OHLCV history for crypto (outputsize=full = ~20 years)."""
    data = await _rate_limited_get({
        "function": "DIGITAL_CURRENCY_DAILY",
        "symbol": symbol,
        "market": market,
    })
    ts_key = "Time Series (Digital Currency Daily)"
    series = data.get(ts_key, {})
    if not series:
        logger.warning(f"No data returned for crypto {symbol}. Raw keys: {list(data.keys())[:5]}")
        return []
    bars: list[OHLCVBar] = []
    for date_str, values in sorted(series.items()):
        try:
            bars.append(OHLCVBar(
                timestamp=date_str,
                open=float(values.get(f"1a. open ({market})", values.get("1. open", 0))),
                high=float(values.get(f"2a. high ({market})", values.get("2. high", 0))),
                low=float(values.get(f"3a. low ({market})", values.get("3. low", 0))),
                close=float(values.get(f"4a. close ({market})", values.get("4. close", 0))),
                volume=float(values.get("5. volume", 0)),
            ))
        except (ValueError, TypeError):
            continue
    return bars


async def fetch_forex_full(from_symbol: str, to_symbol: str) -> list[OHLCVBar]:
    """Fetch full daily OHLCV history for a forex pair (outputsize=full)."""
    data = await _rate_limited_get({
        "function": "FX_DAILY",
        "from_symbol": from_symbol,
        "to_symbol": to_symbol,
        "outputsize": "full",
    })
    ts_key = "Time Series FX (Daily)"
    series = data.get(ts_key, {})
    if not series:
        logger.warning(f"No data returned for forex {from_symbol}/{to_symbol}. Raw keys: {list(data.keys())[:5]}")
        return []
    bars: list[OHLCVBar] = []
    for date_str, values in sorted(series.items()):
        try:
            bars.append(OHLCVBar(
                timestamp=date_str,
                open=float(values.get("1. open", 0)),
                high=float(values.get("2. high", 0)),
                low=float(values.get("3. low", 0)),
                close=float(values.get("4. close", 0)),
                volume=0.0,
            ))
        except (ValueError, TypeError):
            continue
    return bars


# -----------------------------------------------
# Store helpers
# -----------------------------------------------

def _upsert_bars(asset: str, market_type: MarketType, bars: list[OHLCVBar], timeframe: str = "1d") -> int:
    """Upsert bars into Supabase historical_data. Returns inserted count."""
    if not bars:
        return 0
    supabase = get_supabase()
    rows = [
        {
            "asset": asset,
            "market_type": market_type.value,
            "timeframe": timeframe,
            "timestamp": bar.timestamp if isinstance(bar.timestamp, str) else bar.timestamp.isoformat()[:10],
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in bars
    ]
    # Batch in chunks of 500 to avoid request size limits
    batch_size = 500
    total = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        supabase.table("historical_data").upsert(
            chunk, on_conflict="asset,timeframe,timestamp"
        ).execute()
        total += len(chunk)
    return total


def get_data_status() -> list[dict[str, Any]]:
    """Return per-asset row counts and date ranges from Supabase."""
    supabase = get_supabase()
    # Get stats per asset+timeframe
    resp = supabase.table("historical_data").select(
        "asset, market_type, timeframe, timestamp"
    ).execute()
    rows = resp.data or []

    # Aggregate
    from collections import defaultdict
    stats: dict[tuple, dict] = defaultdict(lambda: {"count": 0, "min_date": None, "max_date": None})
    for row in rows:
        key = (row["asset"], row["market_type"], row["timeframe"])
        s = stats[key]
        s["count"] += 1
        ts = row["timestamp"]
        if s["min_date"] is None or ts < s["min_date"]:
            s["min_date"] = ts
        if s["max_date"] is None or ts > s["max_date"]:
            s["max_date"] = ts

    result = []
    for (asset, market_type, timeframe), s in sorted(stats.items()):
        result.append({
            "asset": asset,
            "market_type": market_type,
            "timeframe": timeframe,
            "bar_count": s["count"],
            "start_date": s["min_date"],
            "end_date": s["max_date"],
        })
    return result


# -----------------------------------------------
# Main bulk loader
# -----------------------------------------------

async def load_all_historical(
    crypto_assets: list[str] | None = None,
    forex_pairs: list[str] | None = None,
    progress_cb: Any = None,
) -> dict[str, Any]:
    """Fetch full historical data for all tracked assets and store in Supabase.
    
    Args:
        crypto_assets: list of crypto symbols (defaults to settings)
        forex_pairs: list of forex pairs like "EUR/USD" (defaults to settings)
        progress_cb: async callable(asset, status, bars_loaded) for WebSocket progress

    Returns:
        Summary dict with counts per asset.
    """
    crypto_assets = crypto_assets or settings.crypto_symbols
    forex_pairs = forex_pairs or settings.forex_pairs

    summary: dict[str, Any] = {"loaded": {}, "errors": {}, "started_at": datetime.now(timezone.utc).isoformat()}

    async def _report(asset: str, status: str, count: int = 0):
        logger.info(f"[DataLoader] {asset}: {status} ({count} bars)")
        if progress_cb:
            await progress_cb({"asset": asset, "status": status, "bars": count})

    # Crypto
    for symbol in crypto_assets:
        try:
            await _report(symbol, "fetching")
            bars = await fetch_crypto_full(symbol)
            count = _upsert_bars(symbol, MarketType.CRYPTO, bars)
            summary["loaded"][symbol] = count
            await _report(symbol, "done", count)
        except Exception as e:
            logger.error(f"Failed to load crypto {symbol}: {e}")
            summary["errors"][symbol] = str(e)
            await _report(symbol, f"error: {e}")

    # Forex
    for pair in forex_pairs:
        try:
            parts = pair.split("/")
            if len(parts) != 2:
                continue
            from_sym, to_sym = parts
            await _report(pair, "fetching")
            bars = await fetch_forex_full(from_sym, to_sym)
            count = _upsert_bars(pair, MarketType.FOREX, bars)
            summary["loaded"][pair] = count
            await _report(pair, "done", count)
        except Exception as e:
            logger.error(f"Failed to load forex {pair}: {e}")
            summary["errors"][pair] = str(e)
            await _report(pair, f"error: {e}")

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["total_bars"] = sum(summary["loaded"].values())
    return summary


async def load_single_asset(asset: str, market_type: MarketType) -> dict[str, Any]:
    """Fetch and store historical data for a single asset."""
    try:
        if market_type == MarketType.CRYPTO:
            bars = await fetch_crypto_full(asset)
        else:
            parts = asset.split("/")
            bars = await fetch_forex_full(parts[0], parts[1])
        count = _upsert_bars(asset, market_type, bars)
        return {"asset": asset, "bars_loaded": count, "status": "ok"}
    except Exception as e:
        logger.error(f"Failed to load {asset}: {e}")
        return {"asset": asset, "bars_loaded": 0, "status": "error", "error": str(e)}
