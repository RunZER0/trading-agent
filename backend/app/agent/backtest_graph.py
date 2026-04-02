"""Agent-driven backtesting LangGraph.

The agent:
1. Loads historical data from Supabase
2. Computes technical indicators
3. Uses GPT-5.4-mini to select relevant strategies to test
4. Simulates each strategy against historical data
5. Uses GPT-5.4 to rank results and produce a strategy recommendation
6. Persists everything to Supabase
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
from langgraph.graph import END, START, StateGraph

from app.agent.backtest_state import BacktestAgentState, StrategyResult, StrategySpec
from app.dependencies import get_supabase
from app.services.llm import decision_llm, workhorse_llm
from app.services.technical_analysis import bars_to_dataframe, compute_all_indicators

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Built-in strategy catalogue
# ──────────────────────────────────────────────────────────────────────────────

STRATEGY_CATALOGUE = [
    StrategySpec(
        name="ema_crossover_fast",
        description="Fast EMA crossover: 10/20 EMA. Entry on golden cross, exit on death cross.",
        entry_rules={"ema_fast": 10, "ema_slow": 20, "signal": "golden_cross"},
        exit_rules={"ema_fast": 10, "ema_slow": 20, "signal": "death_cross"},
    ),
    StrategySpec(
        name="ema_crossover_slow",
        description="Slow EMA crossover: 20/50 EMA. More conservative trend-following.",
        entry_rules={"ema_fast": 20, "ema_slow": 50, "signal": "golden_cross"},
        exit_rules={"ema_fast": 20, "ema_slow": 50, "signal": "death_cross"},
    ),
    StrategySpec(
        name="rsi_mean_reversion",
        description="RSI mean reversion: buy when RSI-14 < 35 (oversold), sell when RSI > 65.",
        entry_rules={"indicator": "rsi", "period": 14, "buy_threshold": 35},
        exit_rules={"indicator": "rsi", "period": 14, "sell_threshold": 65},
    ),
    StrategySpec(
        name="macd_momentum",
        description="MACD momentum: buy on MACD line crossing above signal, sell on cross below.",
        entry_rules={"indicator": "macd", "signal": "bullish_cross"},
        exit_rules={"indicator": "macd", "signal": "bearish_cross"},
    ),
    StrategySpec(
        name="bollinger_breakout",
        description="Bollinger Band breakout: buy on close above upper band, sell on close below lower band.",
        entry_rules={"indicator": "bollinger", "signal": "upper_break"},
        exit_rules={"indicator": "bollinger", "signal": "lower_break"},
    ),
    StrategySpec(
        name="rsi_trend_filter",
        description="RSI with trend filter: only buy when RSI < 40 AND 50-SMA is rising (trend confirmation).",
        entry_rules={"rsi_buy": 40, "trend_filter": "sma50_rising"},
        exit_rules={"rsi_sell": 60},
    ),
]


# ──────────────────────────────────────────────────────────────────────────────
# Node: Load historical data
# ──────────────────────────────────────────────────────────────────────────────

async def load_data_node(state: BacktestAgentState) -> BacktestAgentState:
    config = state.config
    assets = config.get("assets", [])
    timeframe = config.get("timeframe", "1d")
    start_date = config.get("start_date", "2024-01-01")
    end_date = config.get("end_date", datetime.now().strftime("%Y-%m-%d"))

    state.logs.append(f"Loading historical data for {assets}, {start_date} → {end_date}")
    supabase = get_supabase()

    for asset in assets:
        resp = (
            supabase.table("historical_data")
            .select("timestamp,open,high,low,close,volume")
            .eq("asset", asset)
            .eq("timeframe", timeframe)
            .gte("timestamp", start_date)
            .lte("timestamp", end_date)
            .order("timestamp")
            .limit(50000)  # PostgREST default caps at 1000 without this
            .execute()
        )
        rows = resp.data or []
        if len(rows) < 30:
            msg = f"Insufficient data for {asset}: only {len(rows)} bars (need ≥30). Run data loader first."
            state.logs.append(f"WARNING: {msg}")
            state.errors.append(msg)
        else:
            state.historical_data[asset] = rows
            state.logs.append(f"  {asset}: {len(rows)} bars loaded")

    return state


# ──────────────────────────────────────────────────────────────────────────────
# Node: Compute technical indicators summary
# ──────────────────────────────────────────────────────────────────────────────

async def compute_indicators_node(state: BacktestAgentState) -> BacktestAgentState:
    state.logs.append("Computing technical indicators...")
    for asset, rows in state.historical_data.items():
        try:
            df = pd.DataFrame(rows)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna().sort_values("timestamp").reset_index(drop=True)

            indicators = compute_all_indicators(df)
            state.indicators[asset] = {
                "summary": indicators.get("summary", {}),
                "bar_count": len(df),
                "date_range": f"{df['timestamp'].iloc[0].date()} to {df['timestamp'].iloc[-1].date()}",
                "current_price": float(df["close"].iloc[-1]),
                "volatility_pct": float(df["close"].pct_change().std() * 100),
                "trend_direction": indicators.get("summary", {}).get("overall_signal", "NEUTRAL"),
            }
            state.logs.append(f"  {asset}: indicators computed ({len(df)} bars)")
        except Exception as e:
            state.errors.append(f"Indicator error for {asset}: {e}")
    return state


# ──────────────────────────────────────────────────────────────────────────────
# Node: LLM selects which strategies to test
# ──────────────────────────────────────────────────────────────────────────────

async def select_strategies_node(state: BacktestAgentState) -> BacktestAgentState:
    state.logs.append("Agent selecting strategies to test...")
    config = state.config

    prompt = f"""You are a quantitative trading strategist. 
The user wants to backtest on: {config.get('assets')}
Date range: {config.get('start_date')} to {config.get('end_date')}
Capital: ${config.get('initial_capital', 10000):,.0f}
Position size per trade: {config.get('position_size_pct', 5)}%
Stop loss: {config.get('stop_loss_pct', 2)}%
Take profit: {config.get('take_profit_pct', 4)}%
User notes: {config.get('notes', 'none')}

Market indicators summary:
{json.dumps(state.indicators, indent=2, default=str)}

Available strategy catalogue:
{json.dumps([s.model_dump() for s in STRATEGY_CATALOGUE], indent=2)}

Select ALL strategies from the catalogue that are appropriate for these assets and market conditions.
Respond as JSON:
{{
  "selected_strategy_names": ["name1", "name2", ...],
  "reasoning": "why these strategies suit these assets/conditions"
}}"""

    try:
        resp = await workhorse_llm.ainvoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        # Extract JSON
        import re
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            selected_names = parsed.get("selected_strategy_names", [])
            state.strategy_selection_reasoning = parsed.get("reasoning", "")
            state.strategies = [s for s in STRATEGY_CATALOGUE if s.name in selected_names]
    except Exception as e:
        state.errors.append(f"Strategy selection error: {e}")

    # Fallback: test all strategies
    if not state.strategies:
        state.strategies = STRATEGY_CATALOGUE
        state.strategy_selection_reasoning = "Defaulted to all strategies."

    state.logs.append(f"  Selected {len(state.strategies)} strategies: {[s.name for s in state.strategies]}")
    return state


# ──────────────────────────────────────────────────────────────────────────────
# Strategy simulators
# ──────────────────────────────────────────────────────────────────────────────

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def _macd(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    ema12 = _ema(series, 12)
    ema26 = _ema(series, 26)
    macd_line = ema12 - ema26
    signal_line = _ema(macd_line, 9)
    return macd_line, signal_line

def _bollinger(series: pd.Series, period: int = 20, std: float = 2.0) -> tuple[pd.Series, pd.Series]:
    sma = series.rolling(period).mean()
    sd = series.rolling(period).std()
    return sma + std * sd, sma - std * sd


def _simulate_strategy(
    strategy: StrategySpec,
    df: pd.DataFrame,
    config: dict[str, Any],
) -> StrategyResult:
    """Simulate a strategy on a DataFrame of OHLCV data. Returns StrategyResult."""
    capital = float(config.get("initial_capital", 10000))
    pos_pct = float(config.get("position_size_pct", 5)) / 100
    sl_pct = float(config.get("stop_loss_pct", 2)) / 100
    tp_pct = float(config.get("take_profit_pct", 4)) / 100
    commission = 0.001  # 0.1% round-trip per side

    df = df.copy().reset_index(drop=True)
    close = df["close"]

    # Compute signals based on strategy
    name = strategy.name
    buy_signal = pd.Series(False, index=df.index)
    sell_signal = pd.Series(False, index=df.index)

    try:
        if "ema_crossover" in name or "ema_cross" in name:
            fast_p = strategy.entry_rules.get("ema_fast", 10)
            slow_p = strategy.entry_rules.get("ema_slow", 20)
            fast = _ema(close, fast_p)
            slow = _ema(close, slow_p)
            buy_signal = (fast > slow) & (fast.shift(1) <= slow.shift(1))
            sell_signal = (fast < slow) & (fast.shift(1) >= slow.shift(1))

        elif "rsi_mean_reversion" in name:
            period = strategy.entry_rules.get("period", 14)
            buy_threshold = strategy.entry_rules.get("buy_threshold", 35)
            sell_threshold = strategy.exit_rules.get("sell_threshold", 65)
            rsi = _rsi(close, period)
            buy_signal = (rsi < buy_threshold) & (rsi.shift(1) >= buy_threshold)
            sell_signal = (rsi > sell_threshold) & (rsi.shift(1) <= sell_threshold)

        elif "macd" in name:
            fast_p = strategy.entry_rules.get("ema_fast", 12)
            slow_p = strategy.entry_rules.get("ema_slow", 26)
            sig_p  = strategy.entry_rules.get("signal_period", 9)
            ema_f = _ema(close, fast_p)
            ema_s = _ema(close, slow_p)
            macd_line = ema_f - ema_s
            signal_line = _ema(macd_line, sig_p)
            buy_signal = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
            sell_signal = (macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))

        elif "bollinger" in name:
            period   = strategy.entry_rules.get("period", 20)
            std_mult = strategy.entry_rules.get("std", 2.0)
            upper, lower = _bollinger(close, period=period, std=std_mult)
            buy_signal = close > upper
            sell_signal = close < lower

        elif "rsi_trend" in name:
            rsi_buy    = strategy.entry_rules.get("rsi_buy", 40)
            rsi_sell   = strategy.exit_rules.get("rsi_sell", 60)
            sma_period = strategy.entry_rules.get("sma_period", 50)
            rsi = _rsi(close, 14)
            sma = close.rolling(sma_period).mean()
            sma_rising = sma > sma.shift(5)
            buy_signal = (rsi < rsi_buy) & sma_rising
            sell_signal = rsi > rsi_sell

    except Exception:
        pass

    # Simulate trades
    trades = []
    equity_curve = []
    current_capital = capital
    peak_capital = capital
    max_dd = 0.0
    in_position = False
    entry_price = 0.0
    entry_idx = 0
    entry_capital = 0.0

    for i in range(len(df)):
        row = df.iloc[i]
        price = float(row["close"])

        # Check exit
        if in_position:
            pct_change = (price - entry_price) / entry_price
            hit_sl = pct_change <= -sl_pct
            hit_tp = pct_change >= tp_pct
            hit_sell = bool(sell_signal.iloc[i])

            if hit_sl or hit_tp or hit_sell:
                exit_reason = "stop_loss" if hit_sl else ("take_profit" if hit_tp else "signal")
                pnl = entry_capital * pct_change - entry_capital * commission
                current_capital += pnl
                duration = i - entry_idx
                trades.append({
                    "entry_date": str(df.iloc[entry_idx]["timestamp"]),
                    "exit_date": str(row["timestamp"]),
                    "entry_price": entry_price,
                    "exit_price": price,
                    "pnl": round(pnl, 4),
                    "pnl_pct": round(pct_change * 100, 2),
                    "exit_reason": exit_reason,
                    "duration_days": duration,
                })
                in_position = False

        # Check entry
        if not in_position and bool(buy_signal.iloc[i]) and i + 1 < len(df):
            entry_price = float(df.iloc[i + 1]["close"])  # Next bar open
            entry_capital = current_capital * pos_pct
            current_capital -= entry_capital * commission
            in_position = True
            entry_idx = i + 1

        # Track equity
        unrealized = 0.0
        if in_position:
            unrealized = entry_capital * ((price - entry_price) / entry_price)
        total_equity = current_capital + entry_capital + unrealized
        peak_capital = max(peak_capital, total_equity)
        drawdown = (peak_capital - total_equity) / peak_capital * 100
        max_dd = max(max_dd, drawdown)
        equity_curve.append({"timestamp": str(row["timestamp"]), "equity": round(total_equity, 2)})

    # Close any open position at end
    if in_position and len(df) > 0:
        exit_price = float(df.iloc[-1]["close"])
        pct_change = (exit_price - entry_price) / entry_price
        pnl = entry_capital * pct_change
        current_capital += pnl
        trades.append({
            "entry_date": str(df.iloc[entry_idx]["timestamp"]),
            "exit_date": str(df.iloc[-1]["timestamp"]),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": round(pnl, 4),
            "pnl_pct": round(pct_change * 100, 2),
            "exit_reason": "end_of_period",
            "duration_days": len(df) - entry_idx,
        })

    # Metrics
    total_return_pct = (current_capital - capital) / capital * 100
    winning = [t for t in trades if t["pnl"] > 0]
    losing = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(winning) / len(trades) * 100 if trades else 0
    gross_profit = sum(t["pnl"] for t in winning)
    gross_loss = abs(sum(t["pnl"] for t in losing))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (10.0 if gross_profit > 0 else 0.0)

    # Sharpe ratio (daily returns)
    if len(equity_curve) > 1:
        equities = [e["equity"] for e in equity_curve]
        returns = pd.Series(equities).pct_change().dropna()
        sharpe = float(returns.mean() / returns.std() * math.sqrt(252)) if returns.std() > 0 else 0.0
    else:
        sharpe = 0.0

    avg_duration = sum(t["duration_days"] for t in trades) / len(trades) if trades else 0

    return StrategyResult(
        strategy_name=strategy.name,
        asset="",  # filled in for_asset
        total_return_pct=round(total_return_pct, 2),
        sharpe_ratio=round(sharpe, 3),
        max_drawdown_pct=round(max_dd, 2),
        win_rate=round(win_rate, 1),
        total_trades=len(trades),
        profit_factor=round(profit_factor, 3),
        avg_trade_duration_days=round(avg_duration, 1),
        equity_curve=equity_curve,
        trades=trades,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Node: Simulate all strategies
# ──────────────────────────────────────────────────────────────────────────────

async def simulate_strategies_node(state: BacktestAgentState) -> BacktestAgentState:
    state.logs.append(f"Simulating {len(state.strategies)} strategies × {len(state.historical_data)} assets...")
    # Accumulate across optimization rounds — do not replace previous results
    results: list[StrategyResult] = list(state.strategy_results)

    for asset, rows in state.historical_data.items():
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna().sort_values("timestamp").reset_index(drop=True)

        for strategy in state.strategies:
            try:
                result = _simulate_strategy(strategy, df, state.config)
                result.asset = asset
                results.append(result)
                state.logs.append(
                    f"  {strategy.name}/{asset}: return={result.total_return_pct:.1f}% "
                    f"sharpe={result.sharpe_ratio:.2f} trades={result.total_trades}"
                )
            except Exception as e:
                state.errors.append(f"Simulation error {strategy.name}/{asset}: {e}")

    state.strategy_results = results
    return state


# ──────────────────────────────────────────────────────────────────────────────
# Node: GPT-5.4 ranks strategies and recommends the best
# ──────────────────────────────────────────────────────────────────────────────

async def rank_strategies_node(state: BacktestAgentState) -> BacktestAgentState:
    state.logs.append("Agent ranking strategies and generating recommendations...")

    if not state.strategy_results:
        state.errors.append("No strategy results to rank.")
        state.completed = True
        return state

    # Sort by Sharpe ratio as a baseline for the summary
    results_summary = sorted(
        [r.model_dump(exclude={"equity_curve", "trades"}) for r in state.strategy_results],
        key=lambda x: x.get("sharpe_ratio", 0),
        reverse=True,
    )

    prompt = f"""You are an expert quantitative portfolio analyst.

User's backtest configuration:
{json.dumps(state.config, indent=2)}

Strategy test results (sorted by Sharpe ratio):
{json.dumps(results_summary, indent=2)}

Analyse these backtesting results and provide:
1. Which strategy (name + asset combination) performed best and WHY
2. Risk-adjusted analysis: balance return vs drawdown vs win rate
3. What market regime favoured each strategy
4. Specific parameter improvements to try for the best strategy
5. Which strategy you recommend going live with and at what position size

Respond as JSON:
{{
  "best_strategy_name": "...",
  "best_asset": "...",
  "ranking_analysis": "detailed markdown analysis of all strategies",
  "recommendations": "actionable advice: strategy choice, parameter tuning, risk settings",
  "suggested_live_position_pct": 3.5,
  "confidence": 75
}}"""

    try:
        resp = await decision_llm.ainvoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        import re
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            best_name = parsed.get("best_strategy_name", "")
            best_asset = parsed.get("best_asset", "")
            state.ranking_analysis = parsed.get("ranking_analysis", "")
            state.recommendations = parsed.get("recommendations", "")

            # Find the best result
            for result in state.strategy_results:
                if result.strategy_name == best_name and result.asset == best_asset:
                    state.best_result = result
                    break
            # Find best strategy spec
            for spec in state.strategies:
                if spec.name == best_name:
                    state.best_strategy = spec
                    break
    except Exception as e:
        state.errors.append(f"Ranking error: {e}")
        # Fallback: pick by Sharpe
        if state.strategy_results:
            best = max(state.strategy_results, key=lambda r: r.sharpe_ratio)
            state.best_result = best
            state.ranking_analysis = f"Best by Sharpe ratio: {best.strategy_name} on {best.asset}"

    state.logs.append(f"  Best: {state.best_strategy.name if state.best_strategy else 'N/A'}")
    return state


# ──────────────────────────────────────────────────────────────────────────────
# Node: LLM proposes parameter variants and decides whether to keep optimizing
# ──────────────────────────────────────────────────────────────────────────────

async def optimize_strategy_node(state: BacktestAgentState) -> BacktestAgentState:
    """Agent analyzes results and proposes concrete parameter variants to test next round."""
    state.iteration += 1
    state.logs.append(f"Optimization round {state.iteration}/{state.max_iterations}: agent proposing variants...")

    if not state.best_result or not state.best_strategy:
        state.should_continue_optimization = False
        return state

    results_summary = sorted(
        [r.model_dump(exclude={"equity_curve", "trades"}) for r in state.strategy_results],
        key=lambda x: x.get("sharpe_ratio", 0),
        reverse=True,
    )

    prompt = f"""You are a quantitative strategy optimizer running iteration {state.iteration} of {state.max_iterations}.

Assets: {list(state.historical_data.keys())}
Config: {json.dumps(state.config)}

All results tested so far (best first by Sharpe):
{json.dumps(results_summary[:15], indent=2)}

Best strategy so far: {state.best_strategy.model_dump()}
Best metrics: return={state.best_result.total_return_pct:.1f}%, sharpe={state.best_result.sharpe_ratio:.2f}, win_rate={state.best_result.win_rate:.1f}%, max_dd={state.best_result.max_drawdown_pct:.1f}%

Propose 2-4 NEW untested parameter variants that may outperform the current best.
Focus on the best-performing strategy family. Use SPECIFIC numbers, not vague ideas.
Set should_continue=false if: Sharpe > 2.5, you've exhausted meaningful ideas, or diminishing returns are clear.

Available strategy types and their parameter schemas:
- ema_crossover variants: entry_rules={{"ema_fast": N, "ema_slow": M}}, exit_rules={{"ema_fast": N, "ema_slow": M}}
- rsi_mean_reversion variants: entry_rules={{"period": N, "buy_threshold": X}}, exit_rules={{"sell_threshold": Y}}
- macd variants: entry_rules={{"ema_fast": N, "ema_slow": M, "signal_period": P}}, exit_rules={{}}
- bollinger variants: entry_rules={{"period": N, "std": X}}, exit_rules={{}}
- rsi_trend variants: entry_rules={{"rsi_buy": X, "sma_period": N}}, exit_rules={{"rsi_sell": Y}}

Respond ONLY as JSON:
{{
  "should_continue": true,
  "reasoning": "brief explanation of what you're testing and why",
  "variants": [
    {{
      "name": "ema_crossover_opt_{state.iteration}_1",
      "description": "EMA 8/21 — tighter than 10/20 to catch faster moves",
      "entry_rules": {{"ema_fast": 8, "ema_slow": 21}},
      "exit_rules": {{"ema_fast": 8, "ema_slow": 21}}
    }}
  ]
}}"""

    try:
        resp = await workhorse_llm.ainvoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        import re
        match = re.search(r'\{{.*\}}', content, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            state.should_continue_optimization = parsed.get("should_continue", False)
            state.optimization_reasoning = parsed.get("reasoning", "")
            new_strategies = []
            for v in parsed.get("variants", []):
                # Skip already-tested names
                tested_names = {r.strategy_name for r in state.strategy_results}
                if v.get("name") in tested_names:
                    continue
                try:
                    new_strategies.append(StrategySpec(
                        name=v["name"],
                        description=v.get("description", ""),
                        entry_rules=v.get("entry_rules", {}),
                        exit_rules=v.get("exit_rules", {}),
                    ))
                except Exception:
                    pass
            state.strategies = new_strategies
            state.logs.append(
                f"  Optimizer: {len(new_strategies)} variants queued. "
                f"Continue={state.should_continue_optimization}. {state.optimization_reasoning[:120]}"
            )
            if not new_strategies:
                state.should_continue_optimization = False
    except Exception as e:
        state.errors.append(f"Optimization error: {e}")
        state.should_continue_optimization = False

    return state


def route_after_ranking(state: BacktestAgentState) -> str:
    """Always do at least one optimization round; then follow LLM signal or iteration cap."""
    if state.iteration == 0:
        return "optimize"  # First pass: always try to improve
    if state.iteration >= state.max_iterations or not state.should_continue_optimization:
        return "persist"
    return "optimize"


# ──────────────────────────────────────────────────────────────────────────────
# Node: Persist results to Supabase
# ──────────────────────────────────────────────────────────────────────────────

async def persist_backtest_node(state: BacktestAgentState) -> BacktestAgentState:
    state.logs.append("Saving results to database...")
    supabase = get_supabase()

    # Serialize results for storage
    results_payload = [
        {**r.model_dump(exclude={"equity_curve", "trades"})} 
        for r in state.strategy_results
    ]

    best_equity = state.best_result.equity_curve if state.best_result else []
    best_trades = state.best_result.trades if state.best_result else []

    try:
        supabase.table("backtest_runs").update({
            "status": "completed",
            "results": {
                "strategy_results": results_payload,
                "best_strategy": state.best_strategy.model_dump() if state.best_strategy else None,
                "best_result_metrics": state.best_result.model_dump(exclude={"equity_curve", "trades"}) if state.best_result else None,
                "ranking_analysis": state.ranking_analysis,
                "recommendations": state.recommendations,
                "strategy_selection_reasoning": state.strategy_selection_reasoning,
                "optimization_iterations": state.iteration,
                "optimization_reasoning": state.optimization_reasoning,
                "total_variants_tested": len(state.strategy_results),
            },
            "equity_curve": best_equity,
            "trades": best_trades,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "logs": state.logs[-100:],  # last 100 log entries
        }).eq("id", state.run_id).execute()
        state.logs.append("Results saved.")
    except Exception as e:
        state.errors.append(f"Persist error: {e}")
        logger.error(f"Failed to persist backtest results: {e}")

    return state


# ──────────────────────────────────────────────────────────────────────────────
# Graph construction
# ──────────────────────────────────────────────────────────────────────────────

def build_backtest_graph() -> StateGraph:
    graph = StateGraph(BacktestAgentState)
    graph.add_node("load_data", load_data_node)
    graph.add_node("compute_indicators", compute_indicators_node)
    graph.add_node("select_strategies", select_strategies_node)
    graph.add_node("simulate_strategies", simulate_strategies_node)
    graph.add_node("rank_strategies", rank_strategies_node)
    graph.add_node("optimize_strategy", optimize_strategy_node)
    graph.add_node("persist_results", persist_backtest_node)

    graph.add_edge(START, "load_data")
    graph.add_edge("load_data", "compute_indicators")
    graph.add_edge("compute_indicators", "select_strategies")
    graph.add_edge("select_strategies", "simulate_strategies")
    graph.add_edge("simulate_strategies", "rank_strategies")
    graph.add_conditional_edges("rank_strategies", route_after_ranking, {
        "optimize": "optimize_strategy",
        "persist": "persist_results",
    })
    graph.add_edge("optimize_strategy", "simulate_strategies")
    graph.add_edge("persist_results", END)

    return graph.compile()


_backtest_graph = None

def get_backtest_graph():
    global _backtest_graph
    if _backtest_graph is None:
        _backtest_graph = build_backtest_graph()
    return _backtest_graph


async def run_backtest_agent(config: dict[str, Any], run_id: str | None = None) -> BacktestAgentState:
    """Run the agent-driven backtest and return the final state."""
    run_id = run_id or str(uuid.uuid4())
    initial_state = BacktestAgentState(run_id=run_id, config=config)
    graph = get_backtest_graph()
    final_state = await graph.ainvoke(initial_state)
    return final_state
