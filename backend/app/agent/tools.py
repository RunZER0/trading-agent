"""
All tools available to the trading agents.

Every function decorated with @tool is callable by the LLM via LangGraph's
ToolNode — the model sees the docstring as its description and the type
annotations as the parameter schema.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Annotated, Any

import numpy as np
import pandas as pd
from langchain_core.tools import tool

from app.dependencies import get_supabase
from app.services.technical_analysis import (
    compute_all_indicators,
    compute_support_resistance,
    format_indicators_for_llm,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data tools
# ─────────────────────────────────────────────────────────────────────────────

@tool
def get_ohlcv(
    asset: Annotated[str, "Asset symbol e.g. 'BTC', 'EUR/USD'"],
    timeframe: Annotated[str, "Timeframe: '1d', '4h', '1h', '15m'"],
    limit: Annotated[int, "Number of most-recent bars to return (max 2000)"] = 365,
    start_date: Annotated[str, "Optional ISO start date YYYY-MM-DD"] = "",
    end_date: Annotated[str, "Optional ISO end date YYYY-MM-DD"] = "",
) -> str:
    """Fetch OHLCV candlestick bars for an asset from Supabase.
    Returns a JSON summary with bar count, date range, and last 5 bars."""
    supabase = get_supabase()
    limit = min(limit, 2000)
    query = (
        supabase.table("historical_data")
        .select("timestamp,open,high,low,close,volume")
        .eq("asset", asset)
        .eq("timeframe", timeframe)
        .order("timestamp", desc=True)
        .limit(limit)
    )
    if start_date:
        query = query.gte("timestamp", start_date)
    if end_date:
        query = query.lte("timestamp", end_date)

    resp = query.execute()
    bars = list(reversed(resp.data or []))

    if not bars:
        return json.dumps({"error": f"No data found for {asset} {timeframe}"})

    return json.dumps({
        "asset": asset,
        "timeframe": timeframe,
        "bar_count": len(bars),
        "date_range": f"{bars[0]['timestamp']} → {bars[-1]['timestamp']}",
        "latest_close": bars[-1]["close"],
        "latest_high": bars[-1]["high"],
        "latest_low": bars[-1]["low"],
        "latest_volume": bars[-1]["volume"],
        "last_5_bars": bars[-5:],
    })


@tool
def compute_indicators(
    asset: Annotated[str, "Asset symbol e.g. 'BTC', 'EUR/USD'"],
    timeframe: Annotated[str, "Timeframe: '1d', '4h', '1h', '15m'"],
    limit: Annotated[int, "Bars of history to use for calculation"] = 200,
) -> str:
    """Compute technical indicators (RSI, MACD, EMA, Bollinger Bands, ADX, ATR,
    Stochastic, support/resistance) for an asset. Returns formatted analysis
    ready for trading decisions."""
    supabase = get_supabase()
    resp = (
        supabase.table("historical_data")
        .select("timestamp,open,high,low,close,volume")
        .eq("asset", asset)
        .eq("timeframe", timeframe)
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    rows = list(reversed(resp.data or []))
    if len(rows) < 20:
        return json.dumps({"error": f"Insufficient data for {asset} {timeframe}: only {len(rows)} bars"})

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().sort_values("timestamp").reset_index(drop=True)

    indicators = compute_all_indicators(df)
    levels = compute_support_resistance(df)
    formatted = format_indicators_for_llm(indicators, levels)

    return json.dumps({
        "asset": asset,
        "timeframe": timeframe,
        "bar_count": len(df),
        "indicators": {k: (round(v, 6) if isinstance(v, float) else v)
                       for k, v in indicators.items() if v is not None},
        "support_levels": levels.get("support", []),
        "resistance_levels": levels.get("resistance", []),
        "formatted_summary": formatted,
    })


@tool
def get_news_sentiment(
    assets: Annotated[list[str], "List of asset symbols to get news for"],
) -> str:
    """Fetch recent news headlines and sentiment scores for given assets
    from Alpha Vantage. Returns top 10 items with sentiment."""
    import asyncio
    from app.services.market_data import fetch_news_sentiment

    tickers = []
    for asset in assets:
        if "/" in asset:
            tickers.append(f"FOREX:{asset.replace('/', '')}")
        else:
            tickers.append(f"CRYPTO:{asset}")

    try:
        loop = asyncio.get_event_loop()
        items = loop.run_until_complete(fetch_news_sentiment(tickers))
        return json.dumps({
            "count": len(items),
            "items": [
                {
                    "headline": n.headline,
                    "source": n.source,
                    "sentiment_score": n.sentiment_score,
                    "sentiment_label": n.sentiment_label,
                    "published": n.published_at,
                    "assets_mentioned": n.assets_mentioned,
                }
                for n in items[:10]
            ],
        })
    except Exception as e:
        return json.dumps({"error": str(e), "items": []})


@tool
def get_portfolio_state() -> str:
    """Get current open trading signals and portfolio state from Supabase.
    Returns active signals, their directions, confidence, and P&L status."""
    supabase = get_supabase()
    resp = (
        supabase.table("trading_signals")
        .select("*")
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    signals = resp.data or []
    return json.dumps({
        "open_positions": len(signals),
        "signals": signals,
    })


@tool
def get_previous_signals(
    asset: Annotated[str, "Asset symbol, or empty string for all assets"] = "",
    limit: Annotated[int, "Number of recent signals to return"] = 10,
) -> str:
    """Get historical trading signals for an asset to understand past performance."""
    supabase = get_supabase()
    query = (
        supabase.table("trading_signals")
        .select("asset,direction,confidence,entry_price,stop_loss,take_profit,created_at,status")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if asset:
        query = query.eq("asset", asset)
    resp = query.execute()
    return json.dumps({"signals": resp.data or []})


# ─────────────────────────────────────────────────────────────────────────────
# Strategy simulation tool (for backtest agent)
# ─────────────────────────────────────────────────────────────────────────────

@tool
def run_strategy(
    asset: Annotated[str, "Asset symbol e.g. 'BTC', 'EUR/USD'"],
    strategy_type: Annotated[str, "One of: ema_crossover, rsi_mean_reversion, macd, bollinger, rsi_trend"],
    params: Annotated[dict, "Strategy parameters as a dict. See schema below."],
    start_date: Annotated[str, "Backtest start date YYYY-MM-DD"],
    end_date: Annotated[str, "Backtest end date YYYY-MM-DD"],
    timeframe: Annotated[str, "Timeframe: '1d', '4h', '1h'"] = "1d",
    initial_capital: Annotated[float, "Starting capital in USD"] = 10000.0,
    position_size_pct: Annotated[float, "Position size as % of capital per trade"] = 5.0,
    stop_loss_pct: Annotated[float, "Stop loss as % from entry"] = 2.0,
    take_profit_pct: Annotated[float, "Take profit as % from entry"] = 4.0,
) -> str:
    """Simulate a trading strategy on historical data and return performance metrics.

    Strategy parameter schemas:
    - ema_crossover:       {"ema_fast": 10, "ema_slow": 20}
    - rsi_mean_reversion:  {"period": 14, "buy_threshold": 35, "sell_threshold": 65}
    - macd:                {"ema_fast": 12, "ema_slow": 26, "signal_period": 9}
    - bollinger:           {"period": 20, "std": 2.0}
    - rsi_trend:           {"rsi_buy": 40, "rsi_sell": 60, "sma_period": 50}

    Returns: total_return_pct, sharpe_ratio, max_drawdown_pct, win_rate,
             total_trades, profit_factor, avg_trade_duration_days, and all trades.
    """
    supabase = get_supabase()
    resp = (
        supabase.table("historical_data")
        .select("timestamp,open,high,low,close,volume")
        .eq("asset", asset)
        .eq("timeframe", timeframe)
        .gte("timestamp", start_date)
        .lte("timestamp", end_date)
        .order("timestamp")
        .limit(50000)
        .execute()
    )
    rows = resp.data or []
    if len(rows) < 30:
        return json.dumps({"error": f"Insufficient data for {asset} {timeframe} {start_date}→{end_date}: {len(rows)} bars"})

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().sort_values("timestamp").reset_index(drop=True)

    close = df["close"]
    buy_signal = pd.Series(False, index=df.index)
    sell_signal = pd.Series(False, index=df.index)

    try:
        st = strategy_type.lower()
        if "ema" in st:
            fp = int(params.get("ema_fast", 10))
            sp = int(params.get("ema_slow", 20))
            fast = close.ewm(span=fp, adjust=False).mean()
            slow = close.ewm(span=sp, adjust=False).mean()
            buy_signal = (fast > slow) & (fast.shift(1) <= slow.shift(1))
            sell_signal = (fast < slow) & (fast.shift(1) >= slow.shift(1))

        elif "rsi_mean" in st or st == "rsi_mean_reversion":
            period = int(params.get("period", 14))
            buy_thr = float(params.get("buy_threshold", 35))
            sell_thr = float(params.get("sell_threshold", 65))
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(period).mean()
            loss = (-delta.clip(upper=0)).rolling(period).mean()
            rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
            buy_signal = (rsi < buy_thr) & (rsi.shift(1) >= buy_thr)
            sell_signal = (rsi > sell_thr) & (rsi.shift(1) <= sell_thr)

        elif "macd" in st:
            fp = int(params.get("ema_fast", 12))
            sp = int(params.get("ema_slow", 26))
            sigp = int(params.get("signal_period", 9))
            macd_line = close.ewm(span=fp, adjust=False).mean() - close.ewm(span=sp, adjust=False).mean()
            sig_line = macd_line.ewm(span=sigp, adjust=False).mean()
            buy_signal = (macd_line > sig_line) & (macd_line.shift(1) <= sig_line.shift(1))
            sell_signal = (macd_line < sig_line) & (macd_line.shift(1) >= sig_line.shift(1))

        elif "bollinger" in st:
            period = int(params.get("period", 20))
            std_mult = float(params.get("std", 2.0))
            sma = close.rolling(period).mean()
            sd = close.rolling(period).std()
            upper = sma + std_mult * sd
            lower = sma - std_mult * sd
            buy_signal = close > upper
            sell_signal = close < lower

        elif "rsi_trend" in st:
            rsi_buy = float(params.get("rsi_buy", 40))
            rsi_sell = float(params.get("rsi_sell", 60))
            sma_p = int(params.get("sma_period", 50))
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
            sma = close.rolling(sma_p).mean()
            sma_rising = sma > sma.shift(5)
            buy_signal = (rsi < rsi_buy) & sma_rising
            sell_signal = rsi > rsi_sell
        else:
            return json.dumps({"error": f"Unknown strategy_type: {strategy_type}"})
    except Exception as e:
        return json.dumps({"error": f"Signal computation failed: {e}"})

    # Simulate
    capital = float(initial_capital)
    pos_pct = float(position_size_pct) / 100
    sl_pct = float(stop_loss_pct) / 100
    tp_pct = float(take_profit_pct) / 100
    commission = 0.001

    trades = []
    equity_curve = []
    peak = capital
    max_dd = 0.0
    in_pos = False
    entry_price = 0.0
    entry_capital = 0.0
    entry_idx = 0

    for i in range(len(df)):
        price = float(df["close"].iloc[i])
        if in_pos:
            pct = (price - entry_price) / entry_price
            if pct <= -sl_pct or pct >= tp_pct or bool(sell_signal.iloc[i]):
                reason = "stop_loss" if pct <= -sl_pct else ("take_profit" if pct >= tp_pct else "signal")
                pnl = entry_capital * pct - entry_capital * commission
                capital += entry_capital + pnl
                trades.append({
                    "entry": str(df["timestamp"].iloc[entry_idx]),
                    "exit": str(df["timestamp"].iloc[i]),
                    "entry_price": round(entry_price, 6),
                    "exit_price": round(price, 6),
                    "pnl": round(pnl, 4),
                    "pnl_pct": round(pct * 100, 2),
                    "reason": reason,
                    "duration_bars": i - entry_idx,
                })
                in_pos = False

        if not in_pos and bool(buy_signal.iloc[i]) and i + 1 < len(df):
            entry_price = float(df["close"].iloc[i + 1])
            entry_capital = capital * pos_pct
            capital -= entry_capital + entry_capital * commission
            in_pos = True
            entry_idx = i + 1

        unrealized = entry_capital * ((price - entry_price) / entry_price) if in_pos else 0.0
        total = capital + (entry_capital + unrealized if in_pos else 0)
        peak = max(peak, total)
        dd = (peak - total) / peak * 100
        max_dd = max(max_dd, dd)
        equity_curve.append({"ts": str(df["timestamp"].iloc[i]), "equity": round(total, 2)})

    if in_pos:
        exit_price = float(df["close"].iloc[-1])
        pct = (exit_price - entry_price) / entry_price
        pnl = entry_capital * pct
        trades.append({
            "entry": str(df["timestamp"].iloc[entry_idx]),
            "exit": str(df["timestamp"].iloc[-1]),
            "entry_price": round(entry_price, 6),
            "exit_price": round(exit_price, 6),
            "pnl": round(pnl, 4),
            "pnl_pct": round(pct * 100, 2),
            "reason": "end_of_period",
            "duration_bars": len(df) - entry_idx,
        })
        capital += entry_capital + pnl

    total_return = (capital - initial_capital) / initial_capital * 100
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (10.0 if gross_profit > 0 else 0.0)

    equities = [e["equity"] for e in equity_curve]
    rets = pd.Series(equities).pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if rets.std() > 0 else 0.0

    return json.dumps({
        "asset": asset,
        "strategy": strategy_type,
        "params": params,
        "timeframe": timeframe,
        "period": f"{start_date} → {end_date}",
        "bars_used": len(df),
        "total_return_pct": round(total_return, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "win_rate_pct": round(win_rate, 1),
        "total_trades": len(trades),
        "profit_factor": round(profit_factor, 3),
        "avg_duration_bars": round(sum(t["duration_bars"] for t in trades) / len(trades), 1) if trades else 0,
        "final_capital": round(capital, 2),
        "trades": trades[-20:],  # last 20 trades to keep response size manageable
        "equity_curve_sample": equity_curve[::max(1, len(equity_curve)//50)],  # 50-point sample
    })


# ─────────────────────────────────────────────────────────────────────────────
# Signal emission tool
# ─────────────────────────────────────────────────────────────────────────────

@tool
def place_signal(
    asset: Annotated[str, "Asset symbol e.g. 'BTC', 'EUR/USD'"],
    direction: Annotated[str, "Trade direction: 'buy', 'sell', or 'hold'"],
    confidence: Annotated[int, "Confidence score 0-100"],
    entry_price: Annotated[float, "Suggested entry price"],
    stop_loss: Annotated[float, "Stop loss price"],
    take_profit: Annotated[float, "Take profit price"],
    position_size_pct: Annotated[float, "Position size as % of portfolio"],
    reasoning: Annotated[str, "Full reasoning chain for this signal"],
    agent_run_id: Annotated[str, "Agent run ID to associate this signal with"] = "",
) -> str:
    """Emit a trading signal to Supabase. Only call this when you have
    high conviction (confidence >= 60). Use direction='hold' to explicitly
    record a HOLD decision."""
    if confidence < 60 and direction.lower() != "hold":
        return json.dumps({"warning": f"Confidence {confidence} < 60 — signal not saved. Use 'hold' instead."})

    market_type = "forex" if "/" in asset and any(
        c in asset for c in ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
    ) else "crypto"

    supabase = get_supabase()
    row = {
        "asset": asset,
        "market_type": market_type,
        "timeframe": "1d",
        "direction": direction.lower(),
        "confidence": confidence,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "position_size_pct": position_size_pct,
        "reasoning": reasoning,
        "agent_run_id": agent_run_id or None,
        "status": "active",
    }
    try:
        resp = supabase.table("trading_signals").insert(row).execute()
        signal_id = resp.data[0]["id"] if resp.data else None
        return json.dumps({"status": "saved", "signal_id": signal_id, "asset": asset, "direction": direction})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─────────────────────────────────────────────────────────────────────────────
# Tool lists (imported by agents)
# ─────────────────────────────────────────────────────────────────────────────

# Live trading agent — reads data, analyses, emits signals
LIVE_AGENT_TOOLS = [
    get_ohlcv,
    compute_indicators,
    get_news_sentiment,
    get_portfolio_state,
    get_previous_signals,
    place_signal,
]

# Backtest agent — reads data, computes indicators, runs strategies, compares
BACKTEST_AGENT_TOOLS = [
    get_ohlcv,
    compute_indicators,
    run_strategy,
    get_previous_signals,
]
