"""Comprehensive backtesting framework.

Pulls historical data from Supabase (pre-loaded via yfinance),
replays it through the agent's analysis pipeline, and produces
detailed performance metrics.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.dependencies import get_supabase
from app.models.schemas import (
    BacktestConfig,
    BacktestResult,
    BacktestStatus,
    BacktestTrade,
    Direction,
    MarketAnalysisOutput,
    MarketType,
    OHLCVBar,
    SignalGenerationOutput,
)
from app.services.llm import decision_llm, llm_structured_output, workhorse_llm
from app.services.technical_analysis import (
    bars_to_dataframe,
    compute_all_indicators,
    compute_support_resistance,
    format_indicators_for_llm,
)

logger = logging.getLogger(__name__)

# Default lookback window for indicator calculation
LOOKBACK_WINDOW = 100


# -----------------------------------------------
# Data loading
# -----------------------------------------------

async def ensure_historical_data(
    asset: str, market_type: MarketType, timeframe: str = "1d"
) -> int:
    """Return the number of historical bars available in Supabase for this asset."""
    supabase = get_supabase()
    count_resp = (
        supabase.table("historical_data")
        .select("id", count="exact")
        .eq("asset", asset)
        .eq("timeframe", timeframe)
        .execute()
    )
    return count_resp.count or 0


def load_historical_from_supabase(
    asset: str,
    timeframe: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Load historical OHLCV data from Supabase into a DataFrame."""
    supabase = get_supabase()
    resp = (
        supabase.table("historical_data")
        .select("*")
        .eq("asset", asset)
        .eq("timeframe", timeframe)
        .gte("timestamp", start_date)
        .lte("timestamp", end_date)
        .order("timestamp")
        .limit(50000)  # Supabase PostgREST caps at 1000 rows by default without this
        .execute()
    )

    if not resp.data:
        return pd.DataFrame()

    df = pd.DataFrame(resp.data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# -----------------------------------------------
# Backtesting engine
# -----------------------------------------------

class BacktestEngine:
    """Replays historical data and generates simulated trades using the trading agent's logic."""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.initial_capital = config.initial_capital
        self.capital = config.initial_capital
        self.positions: dict[str, dict[str, Any]] = {}  # asset -> position info
        self.trades: list[BacktestTrade] = []
        self.equity_curve: list[dict[str, Any]] = []
        self.peak_equity = config.initial_capital
        self.max_drawdown = 0.0

    async def run(self) -> BacktestResult:
        """Execute the full backtest."""
        logger.info(
            f"Starting backtest: {self.config.assets}, "
            f"{self.config.start_date} to {self.config.end_date}"
        )

        # Create run record
        supabase = get_supabase()
        run_record = supabase.table("backtest_runs").insert({
            "name": f"Backtest {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
            "assets": self.config.assets,
            "timeframe": self.config.timeframe,
            "start_date": self.config.start_date,
            "end_date": self.config.end_date,
            "initial_capital": self.config.initial_capital,
            "status": "running",
            "config": self.config.model_dump(),
        }).execute()
        run_id = run_record.data[0]["id"] if run_record.data else None

        try:
            # Load all historical data
            all_data: dict[str, pd.DataFrame] = {}
            for asset in self.config.assets:
                market_type = self._determine_market_type(asset)
                await ensure_historical_data(asset, market_type, self.config.timeframe)
                df = load_historical_from_supabase(
                    asset, self.config.timeframe,
                    self.config.start_date, self.config.end_date,
                )
                if not df.empty:
                    all_data[asset] = df
                    logger.info(f"  Loaded {len(df)} bars for {asset}")
                else:
                    logger.warning(f"  No data for {asset}")

            if not all_data:
                raise ValueError("No historical data available for any asset")

            # Find common date range
            all_dates = set()
            for df in all_data.values():
                all_dates.update(df["timestamp"].tolist())
            sorted_dates = sorted(all_dates)

            # Walk through each date
            for i, current_date in enumerate(sorted_dates):
                if i < LOOKBACK_WINDOW:
                    continue  # Need enough data for indicators

                # Build lookback window for each asset
                asset_windows: dict[str, pd.DataFrame] = {}
                for asset, df in all_data.items():
                    mask = df["timestamp"] <= current_date
                    window = df[mask].tail(LOOKBACK_WINDOW)
                    if len(window) >= 20:  # Need at least 20 bars
                        asset_windows[asset] = window

                if not asset_windows:
                    continue

                # Check stop-losses and take-profits for open positions
                self._check_exits(asset_windows, current_date)

                # Every N bars, run analysis and generate signals
                step_interval = self.config.strategy_params.get("signal_interval", 5)
                if i % step_interval == 0:
                    await self._generate_signals_for_step(
                        asset_windows, current_date
                    )

                # Record equity
                equity = self._calculate_equity(asset_windows)
                self.equity_curve.append({
                    "timestamp": current_date.isoformat() if hasattr(current_date, "isoformat") else str(current_date),
                    "equity": round(equity, 2),
                })
                if equity > self.peak_equity:
                    self.peak_equity = equity
                dd = (self.peak_equity - equity) / self.peak_equity * 100
                if dd > self.max_drawdown:
                    self.max_drawdown = dd

            # Close any remaining positions at last price
            self._close_all_positions(all_data)

            # Calculate metrics
            result = self._compute_metrics(run_id)

            # Save to Supabase
            if run_id:
                supabase.table("backtest_runs").update({
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "results": result.model_dump(exclude={"trades", "equity_curve", "config"}),
                    "trades": [t.model_dump() for t in result.trades],
                    "equity_curve": result.equity_curve,
                }).eq("id", run_id).execute()

            logger.info(
                f"Backtest completed: {result.total_trades} trades, "
                f"{result.total_return_pct:.2f}% return, "
                f"{result.win_rate:.1f}% win rate"
            )
            return result

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            if run_id:
                supabase.table("backtest_runs").update({
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "results": {"error": str(e)},
                }).eq("id", run_id).execute()
            raise

    async def _generate_signals_for_step(
        self,
        asset_windows: dict[str, pd.DataFrame],
        current_date: Any,
    ) -> None:
        """Run the agent's analysis pipeline on current data window."""
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent / "agent" / "prompts"

        # Compute indicators for each asset
        analyses_context = ""
        for asset, window in asset_windows.items():
            indicators = compute_all_indicators(window)
            levels = compute_support_resistance(window)
            formatted = format_indicators_for_llm(indicators, levels)
            market_type = self._determine_market_type(asset)

            analyses_context += f"\n## {asset} ({market_type.value})\n{formatted}\n"

        # Use the frontier model to generate signals
        system_prompt = (prompts_dir / "signal_generator.md").read_text(encoding="utf-8")
        user_prompt = (
            f"# Backtest Analysis — Date: {current_date}\n\n"
            f"{analyses_context}\n\n"
            "Generate trading signals for the above assets. "
            "This is a backtest — focus on the technical data provided. "
            "HOLD is always valid. Only signal BUY/SELL when confidence ≥ 60."
        )

        try:
            result = await llm_structured_output(
                decision_llm,
                SignalGenerationOutput,
                system_prompt,
                user_prompt,
            )

            for signal in result.signals:
                if signal.direction in (Direction.BUY, Direction.SELL) and signal.confidence >= 60:
                    self._execute_signal(signal, asset_windows, current_date)

        except Exception as e:
            logger.warning(f"Signal generation failed at {current_date}: {e}")

    def _execute_signal(
        self, signal: Any, windows: dict[str, pd.DataFrame], date: Any
    ) -> None:
        """Execute a trade signal in the backtest simulation."""
        asset = signal.asset
        if asset not in windows:
            return

        current_price = float(windows[asset]["close"].iloc[-1])

        # Don't open if already have position in same direction
        if asset in self.positions:
            existing = self.positions[asset]
            if existing["direction"] == signal.direction.value:
                return
            # Close existing opposite position first
            self._close_position(asset, current_price, date)

        # Calculate position size
        position_pct = min(
            signal.position_size_pct or 5.0,
            self.config.strategy_params.get("max_position_pct", 5.0),
        )
        position_value = self.capital * (position_pct / 100)
        if position_value <= 0:
            return

        quantity = position_value / current_price

        # Open position
        self.positions[asset] = {
            "direction": signal.direction.value,
            "entry_price": current_price,
            "quantity": quantity,
            "stop_loss": signal.stop_loss or (
                current_price * 0.98 if signal.direction == Direction.BUY
                else current_price * 1.02
            ),
            "take_profit": signal.take_profit or (
                current_price * 1.04 if signal.direction == Direction.BUY
                else current_price * 0.96
            ),
            "entry_time": str(date),
            "confidence": signal.confidence,
            "reasoning": str(signal.reasoning),
        }
        self.capital -= position_value

    def _check_exits(
        self, windows: dict[str, pd.DataFrame], current_date: Any
    ) -> None:
        """Check stop-loss and take-profit for open positions."""
        assets_to_close = []
        for asset, pos in self.positions.items():
            if asset not in windows:
                continue
            row = windows[asset].iloc[-1]
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])

            if pos["direction"] == "BUY":
                if low <= pos["stop_loss"]:
                    assets_to_close.append((asset, pos["stop_loss"], current_date))
                elif high >= pos["take_profit"]:
                    assets_to_close.append((asset, pos["take_profit"], current_date))
            else:  # SELL
                if high >= pos["stop_loss"]:
                    assets_to_close.append((asset, pos["stop_loss"], current_date))
                elif low <= pos["take_profit"]:
                    assets_to_close.append((asset, pos["take_profit"], current_date))

        for asset, price, date in assets_to_close:
            self._close_position(asset, price, date)

    def _close_position(self, asset: str, exit_price: float, date: Any) -> None:
        """Close a position and record the trade."""
        if asset not in self.positions:
            return

        pos = self.positions.pop(asset)
        entry_price = pos["entry_price"]
        quantity = pos["quantity"]

        if pos["direction"] == "BUY":
            pnl = (exit_price - entry_price) * quantity
        else:
            pnl = (entry_price - exit_price) * quantity

        pnl_pct = (pnl / (entry_price * quantity)) * 100 if entry_price * quantity > 0 else 0

        self.capital += (entry_price * quantity) + pnl

        self.trades.append(BacktestTrade(
            asset=asset,
            direction=Direction(pos["direction"]),
            entry_price=round(entry_price, 6),
            exit_price=round(exit_price, 6),
            entry_time=pos["entry_time"],
            exit_time=str(date),
            quantity=round(quantity, 6),
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
            confidence=pos["confidence"],
            reasoning=pos.get("reasoning", ""),
        ))

    def _close_all_positions(self, all_data: dict[str, pd.DataFrame]) -> None:
        """Close remaining positions at last available price."""
        for asset in list(self.positions):
            if asset in all_data:
                last_price = float(all_data[asset]["close"].iloc[-1])
                last_date = all_data[asset]["timestamp"].iloc[-1]
                self._close_position(asset, last_price, last_date)

    def _calculate_equity(self, windows: dict[str, pd.DataFrame]) -> float:
        """Calculate total equity (cash + open positions at current prices)."""
        equity = self.capital
        for asset, pos in self.positions.items():
            if asset in windows:
                current_price = float(windows[asset]["close"].iloc[-1])
                if pos["direction"] == "BUY":
                    equity += (current_price - pos["entry_price"]) * pos["quantity"]
                    equity += pos["entry_price"] * pos["quantity"]
                else:
                    equity += (pos["entry_price"] - current_price) * pos["quantity"]
                    equity += pos["entry_price"] * pos["quantity"]
        return equity

    def _compute_metrics(self, run_id: str | None) -> BacktestResult:
        """Compute performance metrics from trade history."""
        winning = [t for t in self.trades if t.pnl > 0]
        losing = [t for t in self.trades if t.pnl <= 0]

        total_return = self.capital - self.initial_capital
        for pos in self.positions.values():
            total_return += pos["entry_price"] * pos["quantity"]
        total_return_pct = (total_return / self.initial_capital) * 100

        win_rate = (len(winning) / len(self.trades) * 100) if self.trades else 0

        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        # Sharpe ratio (simplified, annualised assuming daily returns)
        if len(self.equity_curve) > 1:
            equities = [e["equity"] for e in self.equity_curve]
            returns = pd.Series(equities).pct_change().dropna()
            if returns.std() > 0:
                sharpe = (returns.mean() / returns.std()) * math.sqrt(252)
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        return BacktestResult(
            id=run_id,
            name=f"Backtest {self.config.start_date} to {self.config.end_date}",
            config=self.config,
            status=BacktestStatus.COMPLETED,
            total_return_pct=round(total_return_pct, 2),
            sharpe_ratio=round(sharpe, 2),
            max_drawdown_pct=round(self.max_drawdown, 2),
            win_rate=round(win_rate, 1),
            total_trades=len(self.trades),
            profit_factor=round(profit_factor, 2) if profit_factor != float("inf") else 999.99,
            trades=self.trades,
            equity_curve=self.equity_curve,
        )

    @staticmethod
    def _determine_market_type(asset: str) -> MarketType:
        if "/" in asset and any(
            c in asset for c in ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
        ):
            return MarketType.FOREX
        return MarketType.CRYPTO


# -----------------------------------------------
# Public API
# -----------------------------------------------

async def run_backtest(config: BacktestConfig) -> BacktestResult:
    """Run a full backtest with the given configuration."""
    engine = BacktestEngine(config)
    return await engine.run()


async def load_historical_data_for_assets(
    assets: list[str], timeframe: str = "1d"
) -> dict[str, int]:
    """Pre-load historical data for multiple assets. Returns {asset: row_count}."""
    results: dict[str, int] = {}
    for asset in assets:
        market_type = BacktestEngine._determine_market_type(asset)
        count = await ensure_historical_data(asset, market_type, timeframe)
        results[asset] = count
    return results
