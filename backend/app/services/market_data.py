"""Alpha Vantage market data service with caching in Supabase."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.config import settings
from app.dependencies import get_supabase
from app.models.schemas import MarketType, NewsSentimentItem, OHLCVBar

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"
_rate_lock = asyncio.Lock()
_last_call_time: Optional[float] = None


async def _rate_limited_get(params: dict[str, str]) -> dict[str, Any]:
    """Make a rate-limited GET to Alpha Vantage (max 5 req/min on free tier)."""
    global _last_call_time
    async with _rate_lock:
        now = asyncio.get_event_loop().time()
        if _last_call_time is not None:
            elapsed = now - _last_call_time
            if elapsed < 12.5:  # 60s / 5 requests = 12s spacing, +0.5s buffer
                await asyncio.sleep(12.5 - elapsed)
        params["apikey"] = settings.alpha_vantage_api_key
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
        _last_call_time = asyncio.get_event_loop().time()
        return resp.json()


# -----------------------------------------------
# Crypto
# -----------------------------------------------

async def fetch_crypto_daily(symbol: str, market: str = "USD") -> list[OHLCVBar]:
    """Fetch daily OHLCV for a crypto symbol."""
    data = await _rate_limited_get({
        "function": "DIGITAL_CURRENCY_DAILY",
        "symbol": symbol,
        "market": market,
    })
    ts_key = "Time Series (Digital Currency Daily)"
    series = data.get(ts_key, {})
    bars: list[OHLCVBar] = []
    for date_str, values in sorted(series.items()):
        bars.append(OHLCVBar(
            timestamp=date_str,
            open=float(values.get(f"1a. open ({market})", 0)),
            high=float(values.get(f"2a. high ({market})", 0)),
            low=float(values.get(f"3a. low ({market})", 0)),
            close=float(values.get(f"4a. close ({market})", 0)),
            volume=float(values.get("5. volume", 0)),
        ))
    return bars


async def fetch_crypto_intraday(
    symbol: str, interval: str = "60min", market: str = "USD"
) -> list[OHLCVBar]:
    """Fetch intraday crypto data."""
    data = await _rate_limited_get({
        "function": "CRYPTO_INTRADAY",
        "symbol": symbol,
        "market": market,
        "interval": interval,
        "outputsize": "compact",
    })
    ts_key = f"Time Series Crypto ({interval})"
    series = data.get(ts_key, {})
    bars: list[OHLCVBar] = []
    for ts_str, values in sorted(series.items()):
        bars.append(OHLCVBar(
            timestamp=ts_str,
            open=float(values.get("1. open", 0)),
            high=float(values.get("2. high", 0)),
            low=float(values.get("3. low", 0)),
            close=float(values.get("4. close", 0)),
            volume=float(values.get("5. volume", 0)),
        ))
    return bars


# -----------------------------------------------
# Forex
# -----------------------------------------------

async def fetch_forex_daily(from_symbol: str, to_symbol: str) -> list[OHLCVBar]:
    """Fetch daily OHLCV for a forex pair."""
    data = await _rate_limited_get({
        "function": "FX_DAILY",
        "from_symbol": from_symbol,
        "to_symbol": to_symbol,
        "outputsize": "compact",
    })
    ts_key = "Time Series FX (Daily)"
    series = data.get(ts_key, {})
    bars: list[OHLCVBar] = []
    for date_str, values in sorted(series.items()):
        bars.append(OHLCVBar(
            timestamp=date_str,
            open=float(values.get("1. open", 0)),
            high=float(values.get("2. high", 0)),
            low=float(values.get("3. low", 0)),
            close=float(values.get("4. close", 0)),
            volume=0.0,
        ))
    return bars


async def fetch_forex_intraday(
    from_symbol: str, to_symbol: str, interval: str = "60min"
) -> list[OHLCVBar]:
    """Fetch intraday forex data."""
    data = await _rate_limited_get({
        "function": "FX_INTRADAY",
        "from_symbol": from_symbol,
        "to_symbol": to_symbol,
        "interval": interval,
        "outputsize": "compact",
    })
    ts_key = f"Time Series FX (Intraday) ({interval})"
    # Alpha Vantage sometimes uses different key names
    if ts_key not in data:
        for k in data:
            if "Time Series" in k:
                ts_key = k
                break
    series = data.get(ts_key, {})
    bars: list[OHLCVBar] = []
    for ts_str, values in sorted(series.items()):
        bars.append(OHLCVBar(
            timestamp=ts_str,
            open=float(values.get("1. open", 0)),
            high=float(values.get("2. high", 0)),
            low=float(values.get("3. low", 0)),
            close=float(values.get("4. close", 0)),
            volume=0.0,
        ))
    return bars


# -----------------------------------------------
# News & Sentiment
# -----------------------------------------------

async def fetch_news_sentiment(tickers: list[str]) -> list[NewsSentimentItem]:
    """Fetch news sentiment from Alpha Vantage."""
    data = await _rate_limited_get({
        "function": "NEWS_SENTIMENT",
        "tickers": ",".join(tickers),
        "limit": "20",
    })
    feed = data.get("feed", [])
    items: list[NewsSentimentItem] = []
    for article in feed[:20]:
        # Find best matching ticker sentiment
        best_score = 0.0
        best_relevance = 0.0
        for ts in article.get("ticker_sentiment", []):
            relevance = float(ts.get("relevance_score", 0))
            if relevance > best_relevance:
                best_relevance = relevance
                best_score = float(ts.get("ticker_sentiment_score", 0))
        items.append(NewsSentimentItem(
            headline=article.get("title", ""),
            source=article.get("source", ""),
            url=article.get("url", ""),
            sentiment_score=best_score,
            relevance_score=best_relevance,
            summary=article.get("summary", ""),
        ))
    return items


# -----------------------------------------------
# Technical Indicators (Alpha Vantage built-in)
# -----------------------------------------------

async def fetch_indicator(
    symbol: str,
    indicator: str,
    interval: str = "daily",
    time_period: int = 14,
    series_type: str = "close",
) -> dict[str, Any]:
    """Fetch a technical indicator from Alpha Vantage."""
    data = await _rate_limited_get({
        "function": indicator,
        "symbol": symbol,
        "interval": interval,
        "time_period": str(time_period),
        "series_type": series_type,
    })
    # The key varies by indicator, e.g. "Technical Analysis: RSI"
    for key, value in data.items():
        if "Technical Analysis" in key:
            return value
    return {}


# -----------------------------------------------
# Unified fetcher (used by agent)
# -----------------------------------------------

async def fetch_market_data_for_asset(
    asset: str, market_type: MarketType, timeframe: str = "daily"
) -> tuple[list[OHLCVBar], dict[str, Any]]:
    """Fetch OHLCV data for an asset. Returns (bars, raw_indicator_data)."""
    if market_type == MarketType.CRYPTO:
        if timeframe == "daily":
            bars = await fetch_crypto_daily(asset)
        else:
            bars = await fetch_crypto_intraday(asset, interval="60min")
    else:
        parts = asset.split("/")
        from_sym, to_sym = parts[0], parts[1] if len(parts) > 1 else "USD"
        if timeframe == "daily":
            bars = await fetch_forex_daily(from_sym, to_sym)
        else:
            bars = await fetch_forex_intraday(from_sym, to_sym, interval="60min")

    return bars, {}


# -----------------------------------------------
# Historical data loader (for backtesting)
# -----------------------------------------------

async def fetch_and_store_historical(
    asset: str,
    market_type: MarketType,
    timeframe: str = "daily",
) -> int:
    """Fetch full historical data and store in Supabase historical_data table.
    Returns number of rows inserted."""
    bars, _ = await fetch_market_data_for_asset(asset, market_type, timeframe)
    if not bars:
        return 0

    supabase = get_supabase()
    rows = [
        {
            "asset": asset if market_type == MarketType.CRYPTO else asset,
            "market_type": market_type.value,
            "timeframe": "1d" if timeframe == "daily" else "1h",
            "timestamp": bar.timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in bars
    ]

    # Upsert to avoid duplicates (asset + timeframe + timestamp is unique)
    supabase.table("historical_data").upsert(
        rows, on_conflict="asset,timeframe,timestamp"
    ).execute()

    logger.info(f"Stored {len(rows)} historical bars for {asset} ({timeframe})")
    return len(rows)
