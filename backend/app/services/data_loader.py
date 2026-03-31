"""Bulk historical data loader — fetches from Alpha Vantage with full output,
stores/upserts into Supabase historical_data table, and reports progress."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf

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


# yfinance symbol map (free, no API key needed)
_YF_CRYPTO = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", "BNB": "BNB-USD", "ADA": "ADA-USD"}
_YF_FOREX  = {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "USDJPY=X",
              "AUD/USD": "AUDUSD=X", "USD/CAD": "USDCAD=X"}
# Map our timeframe labels to yfinance interval strings
_YF_INTERVAL = {"1h": "1h", "4h": "1h", "30m": "30m", "15m": "15m"}


def _yf_download(yf_symbol: str, interval: str) -> pd.DataFrame:
    """Synchronous yfinance download — run in executor."""
    df = yf.download(
        yf_symbol,
        period="730d",   # max lookback for 1h is ~730 days
        interval=interval,
        progress=False,
        auto_adjust=True,
    )
    # Flatten MultiIndex columns if present (multi-ticker download)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


async def fetch_yfinance_intraday(symbol: str, timeframe: str) -> list[OHLCVBar]:
    """Fetch intraday bars for crypto or forex via yfinance (free, no key required).
    For 4h, fetches 1h data and resamples."""
    yf_symbol = _YF_CRYPTO.get(symbol) or _YF_FOREX.get(symbol)
    if not yf_symbol:
        logger.warning(f"No yfinance symbol mapping for {symbol}")
        return []

    yf_interval = _YF_INTERVAL.get(timeframe, "1h")
    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(None, _yf_download, yf_symbol, yf_interval)

    if df is None or df.empty:
        logger.warning(f"yfinance returned empty data for {symbol} ({yf_symbol}) {yf_interval}")
        return []

    bars: list[OHLCVBar] = []
    for ts, row in df.iterrows():
        try:
            # ts is a pandas Timestamp with tz; convert to ISO string
            ts_str = ts.isoformat()
            bars.append(OHLCVBar(
                timestamp=ts_str,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0)),
            ))
        except (ValueError, TypeError, KeyError):
            continue

    if timeframe == "4h" and bars:
        bars = _resample_to_4h(bars)

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
            # Daily bars: store date only (YYYY-MM-DD). Intraday: full ISO datetime.
            "timestamp": (
                (bar.timestamp[:10] if isinstance(bar.timestamp, str) else bar.timestamp.isoformat()[:10])
                if timeframe == "1d"
                else (bar.timestamp if isinstance(bar.timestamp, str) else bar.timestamp.isoformat())
            ),
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
    """Return per-asset row counts and date ranges from Supabase.
    Uses exact count queries per asset+timeframe to avoid row-limit issues."""
    supabase = get_supabase()
    combos = (
        [(a, "crypto") for a in CRYPTO_ASSETS] +
        [(p, "forex") for p in FOREX_PAIRS]
    )
    result = []
    for asset, market_type in combos:
        for tf in ("1d", "1h", "4h"):
            # count="exact" uses PostgREST Prefer: count=exact header; no rows returned
            count_resp = (
                supabase.table("historical_data")
                .select("*", count="exact")
                .eq("asset", asset).eq("timeframe", tf)
                .limit(0)
                .execute()
            )
            count = count_resp.count or 0
            if count == 0:
                continue
            # Fetch first and last timestamps with minimal data
            first = (
                supabase.table("historical_data")
                .select("timestamp").eq("asset", asset).eq("timeframe", tf)
                .order("timestamp", desc=False).limit(1).execute()
            )
            last = (
                supabase.table("historical_data")
                .select("timestamp").eq("asset", asset).eq("timeframe", tf)
                .order("timestamp", desc=True).limit(1).execute()
            )
            result.append({
                "asset": asset,
                "market_type": market_type,
                "timeframe": tf,
                "bar_count": count,
                "start_date": first.data[0]["timestamp"] if first.data else None,
                "end_date": last.data[0]["timestamp"] if last.data else None,
            })
    return result


# -----------------------------------------------
# Main bulk loader
# -----------------------------------------------

async def load_all_historical(
    crypto_assets: list[str] | None = None,
    forex_pairs: list[str] | None = None,
    timeframes: list[str] | None = None,
    progress_cb: Any = None,
) -> dict[str, Any]:
    """Fetch full historical data for all tracked assets and store in Supabase.

    Args:
        crypto_assets: list of crypto symbols (defaults to settings)
        forex_pairs: list of forex pairs like "EUR/USD" (defaults to settings)
        timeframes: list of timeframes to load, e.g. ["1d", "1h", "4h"]
                   Defaults to ["1d"] only. Note: intraday uses 25 req/day limit.
        progress_cb: async callable(dict) for progress updates

    Returns:
        Summary dict with counts per asset.
    """
    crypto_assets = crypto_assets or settings.crypto_symbols
    forex_pairs = forex_pairs or settings.forex_pairs
    timeframes = timeframes or ["1d"]

    summary: dict[str, Any] = {"loaded": {}, "errors": {}, "started_at": datetime.now(timezone.utc).isoformat()}

    async def _report(asset: str, status: str, count: int = 0):
        logger.info(f"[DataLoader] {asset}: {status} ({count} bars)")
        if progress_cb:
            await progress_cb({"asset": asset, "status": status, "bars": count})

    for tf in timeframes:
        is_daily = tf == "1d"

        # Crypto
        for symbol in crypto_assets:
            key = f"{symbol}:{tf}"
            try:
                await _report(symbol, f"fetching {tf}")
                if is_daily:
                    bars = await fetch_crypto_full(symbol)
                else:
                    bars = await fetch_yfinance_intraday(symbol, tf)
                count = _upsert_bars(symbol, MarketType.CRYPTO, bars, timeframe=tf)
                summary["loaded"][key] = count
                await _report(symbol, f"done {tf}", count)
            except Exception as e:
                logger.error(f"Failed to load crypto {symbol} {tf}: {e}")
                summary["errors"][key] = str(e)
                await _report(symbol, f"error: {e}")

        # Forex
        for pair in forex_pairs:
            key = f"{pair}:{tf}"
            parts = pair.split("/")
            if len(parts) != 2:
                continue
            from_sym, to_sym = parts
            try:
                await _report(pair, f"fetching {tf}")
                if is_daily:
                    bars = await fetch_forex_full(from_sym, to_sym)
                else:
                    bars = await fetch_yfinance_intraday(pair, tf)
                count = _upsert_bars(pair, MarketType.FOREX, bars, timeframe=tf)
                summary["loaded"][key] = count
                await _report(pair, f"done {tf}", count)
            except Exception as e:
                logger.error(f"Failed to load forex {pair} {tf}: {e}")
                summary["errors"][key] = str(e)
                await _report(pair, f"error: {e}")

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["total_bars"] = sum(summary["loaded"].values())
    return summary


def _resample_to_4h(bars: list[OHLCVBar]) -> list[OHLCVBar]:
    """Resample 1h bars into 4h candles (groups of 4)."""
    result: list[OHLCVBar] = []
    for i in range(0, len(bars), 4):
        chunk = bars[i:i+4]
        if not chunk:
            continue
        result.append(OHLCVBar(
            timestamp=chunk[0].timestamp,
            open=chunk[0].open,
            high=max(b.high for b in chunk),
            low=min(b.low for b in chunk),
            close=chunk[-1].close,
            volume=sum(b.volume for b in chunk),
        ))
    return result


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
