"""Technical analysis service — compute indicators locally using pandas + ta library."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import ta

from app.models.schemas import OHLCVBar

logger = logging.getLogger(__name__)


def bars_to_dataframe(bars: list[OHLCVBar]) -> pd.DataFrame:
    """Convert OHLCV bars to a pandas DataFrame."""
    if not bars:
        return pd.DataFrame()
    df = pd.DataFrame([b.model_dump() for b in bars])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_all_indicators(df: pd.DataFrame) -> dict[str, Any]:
    """Compute a comprehensive set of technical indicators on OHLCV DataFrame.

    Returns a dict of indicator names -> latest value (or list for series).
    """
    if df.empty or len(df) < 20:
        return {"error": "Insufficient data for indicator calculation"}

    result: dict[str, Any] = {}

    # --- Trend ---
    result["sma_20"] = ta.trend.sma_indicator(df["close"], window=20).iloc[-1]
    result["sma_50"] = ta.trend.sma_indicator(df["close"], window=50).iloc[-1] if len(df) >= 50 else None
    result["sma_200"] = ta.trend.sma_indicator(df["close"], window=200).iloc[-1] if len(df) >= 200 else None
    result["ema_12"] = ta.trend.ema_indicator(df["close"], window=12).iloc[-1]
    result["ema_26"] = ta.trend.ema_indicator(df["close"], window=26).iloc[-1]

    macd_obj = ta.trend.MACD(df["close"])
    result["macd"] = macd_obj.macd().iloc[-1]
    result["macd_signal"] = macd_obj.macd_signal().iloc[-1]
    result["macd_histogram"] = macd_obj.macd_diff().iloc[-1]

    adx_obj = ta.trend.ADXIndicator(df["high"], df["low"], df["close"])
    result["adx"] = adx_obj.adx().iloc[-1]
    result["adx_pos"] = adx_obj.adx_pos().iloc[-1]
    result["adx_neg"] = adx_obj.adx_neg().iloc[-1]

    # --- Momentum ---
    result["rsi_14"] = ta.momentum.rsi(df["close"], window=14).iloc[-1]
    result["rsi_7"] = ta.momentum.rsi(df["close"], window=7).iloc[-1]

    stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"])
    result["stoch_k"] = stoch.stoch().iloc[-1]
    result["stoch_d"] = stoch.stoch_signal().iloc[-1]

    result["williams_r"] = ta.momentum.williams_r(df["high"], df["low"], df["close"]).iloc[-1]
    result["cci"] = ta.trend.cci(df["high"], df["low"], df["close"]).iloc[-1]

    # --- Volatility ---
    bb = ta.volatility.BollingerBands(df["close"])
    result["bb_upper"] = bb.bollinger_hband().iloc[-1]
    result["bb_middle"] = bb.bollinger_mavg().iloc[-1]
    result["bb_lower"] = bb.bollinger_lband().iloc[-1]
    result["bb_width"] = bb.bollinger_wband().iloc[-1]

    result["atr_14"] = ta.volatility.average_true_range(
        df["high"], df["low"], df["close"], window=14
    ).iloc[-1]

    # --- Volume (only meaningful for crypto) ---
    if df["volume"].sum() > 0:
        result["obv"] = ta.volume.on_balance_volume(df["close"], df["volume"]).iloc[-1]
        result["vwap"] = (
            (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()
        ).iloc[-1]
    else:
        result["obv"] = None
        result["vwap"] = None

    # --- Price context ---
    result["current_price"] = float(df["close"].iloc[-1])
    result["prev_close"] = float(df["close"].iloc[-2]) if len(df) > 1 else None
    result["price_change_pct"] = (
        (result["current_price"] - result["prev_close"]) / result["prev_close"] * 100
        if result["prev_close"]
        else 0
    )
    result["high_20d"] = float(df["high"].tail(20).max())
    result["low_20d"] = float(df["low"].tail(20).min())
    result["high_52w"] = float(df["high"].tail(252).max()) if len(df) >= 252 else float(df["high"].max())
    result["low_52w"] = float(df["low"].tail(252).min()) if len(df) >= 252 else float(df["low"].min())

    # --- Pattern detection hints ---
    result["sma_20_50_cross"] = _detect_cross(
        ta.trend.sma_indicator(df["close"], 20),
        ta.trend.sma_indicator(df["close"], 50),
    ) if len(df) >= 50 else "insufficient_data"

    result["macd_cross"] = _detect_cross(
        macd_obj.macd(), macd_obj.macd_signal()
    )

    result["rsi_divergence"] = _detect_rsi_divergence(df["close"], ta.momentum.rsi(df["close"], 14))

    # Clean NaN values
    for key in result:
        if isinstance(result[key], float) and (np.isnan(result[key]) or np.isinf(result[key])):
            result[key] = None

    return result


def _detect_cross(fast: pd.Series, slow: pd.Series) -> str:
    """Detect if a crossover happened in the last 3 bars."""
    if len(fast) < 3 or len(slow) < 3:
        return "no_signal"
    # Current: fast > slow, Previous: fast < slow → bullish cross
    if fast.iloc[-1] > slow.iloc[-1] and fast.iloc[-3] < slow.iloc[-3]:
        return "bullish_cross"
    if fast.iloc[-1] < slow.iloc[-1] and fast.iloc[-3] > slow.iloc[-3]:
        return "bearish_cross"
    return "no_signal"


def _detect_rsi_divergence(price: pd.Series, rsi: pd.Series) -> str:
    """Simplified RSI divergence detection over last 20 bars."""
    if len(price) < 20 or len(rsi) < 20:
        return "no_signal"
    price_tail = price.tail(20)
    rsi_tail = rsi.tail(20)

    # Bullish divergence: price making lower lows, RSI making higher lows
    price_min_idx = price_tail.idxmin()
    rsi_at_price_min = rsi_tail.loc[price_min_idx] if price_min_idx in rsi_tail.index else None

    if rsi_at_price_min is not None:
        if (
            price_tail.iloc[-1] <= price_tail.iloc[0]
            and rsi_tail.iloc[-1] > rsi_tail.iloc[0]
        ):
            return "bullish_divergence"
        if (
            price_tail.iloc[-1] >= price_tail.iloc[0]
            and rsi_tail.iloc[-1] < rsi_tail.iloc[0]
        ):
            return "bearish_divergence"

    return "no_signal"


def compute_support_resistance(df: pd.DataFrame, window: int = 20) -> dict[str, list[float]]:
    """Identify key support and resistance levels using pivot points."""
    if df.empty or len(df) < window:
        return {"support": [], "resistance": []}

    highs = df["high"].tail(window * 3)
    lows = df["low"].tail(window * 3)
    current = float(df["close"].iloc[-1])

    # Simple pivot-based levels
    pivot = (float(highs.max()) + float(lows.min()) + current) / 3
    r1 = 2 * pivot - float(lows.min())
    r2 = pivot + (float(highs.max()) - float(lows.min()))
    s1 = 2 * pivot - float(highs.max())
    s2 = pivot - (float(highs.max()) - float(lows.min()))

    resistance = sorted([r1, r2], reverse=True)
    support = sorted([s1, s2])

    return {"support": support, "resistance": resistance}


def format_indicators_for_llm(indicators: dict[str, Any], levels: dict[str, list[float]]) -> str:
    """Format indicators into a readable string for the LLM."""
    lines = ["## Technical Indicators\n"]

    if "current_price" in indicators:
        lines.append(f"**Current Price**: {indicators['current_price']:.4f}")
        if indicators.get("price_change_pct") is not None:
            lines.append(f"**24h Change**: {indicators['price_change_pct']:.2f}%")

    lines.append("\n### Trend")
    for key in ["sma_20", "sma_50", "sma_200", "ema_12", "ema_26"]:
        if indicators.get(key) is not None:
            lines.append(f"- {key.upper()}: {indicators[key]:.4f}")

    lines.append(f"- MACD: {indicators.get('macd', 'N/A')}")
    lines.append(f"- MACD Signal: {indicators.get('macd_signal', 'N/A')}")
    lines.append(f"- MACD Histogram: {indicators.get('macd_histogram', 'N/A')}")
    lines.append(f"- ADX: {indicators.get('adx', 'N/A')}")

    lines.append("\n### Momentum")
    lines.append(f"- RSI(14): {indicators.get('rsi_14', 'N/A')}")
    lines.append(f"- RSI(7): {indicators.get('rsi_7', 'N/A')}")
    lines.append(f"- Stochastic %K: {indicators.get('stoch_k', 'N/A')}")
    lines.append(f"- Stochastic %D: {indicators.get('stoch_d', 'N/A')}")
    lines.append(f"- Williams %R: {indicators.get('williams_r', 'N/A')}")
    lines.append(f"- CCI: {indicators.get('cci', 'N/A')}")

    lines.append("\n### Volatility")
    lines.append(f"- Bollinger Upper: {indicators.get('bb_upper', 'N/A')}")
    lines.append(f"- Bollinger Lower: {indicators.get('bb_lower', 'N/A')}")
    lines.append(f"- Bollinger Width: {indicators.get('bb_width', 'N/A')}")
    lines.append(f"- ATR(14): {indicators.get('atr_14', 'N/A')}")

    lines.append("\n### Key Levels")
    for s in levels.get("support", []):
        lines.append(f"- Support: {s:.4f}")
    for r in levels.get("resistance", []):
        lines.append(f"- Resistance: {r:.4f}")

    lines.append("\n### Signals")
    lines.append(f"- SMA 20/50 Cross: {indicators.get('sma_20_50_cross', 'N/A')}")
    lines.append(f"- MACD Cross: {indicators.get('macd_cross', 'N/A')}")
    lines.append(f"- RSI Divergence: {indicators.get('rsi_divergence', 'N/A')}")

    lines.append(f"\n### Range")
    lines.append(f"- 20-day High: {indicators.get('high_20d', 'N/A')}")
    lines.append(f"- 20-day Low: {indicators.get('low_20d', 'N/A')}")
    lines.append(f"- 52-week High: {indicators.get('high_52w', 'N/A')}")
    lines.append(f"- 52-week Low: {indicators.get('low_52w', 'N/A')}")

    return "\n".join(lines)
