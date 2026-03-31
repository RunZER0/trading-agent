-- =============================================================
-- Agentic Trading Platform — Initial Schema
-- Run this in Supabase SQL Editor
-- =============================================================

-- -----------------------------------------------
-- Trading Signals
-- -----------------------------------------------
CREATE TABLE IF NOT EXISTS trading_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset           TEXT NOT NULL,                            -- e.g. "BTC/USD", "EUR/USD"
    market_type     TEXT NOT NULL CHECK (market_type IN ('crypto', 'forex')),
    timeframe       TEXT NOT NULL DEFAULT '4h',               -- e.g. "1h", "4h", "1d"
    direction       TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL', 'HOLD')),
    confidence      REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 100),
    entry_price     REAL,
    stop_loss       REAL,
    take_profit     REAL,
    position_size_pct REAL,
    reasoning       JSONB NOT NULL DEFAULT '{}',              -- full chain-of-thought
    metadata        JSONB DEFAULT '{}',
    agent_run_id    UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_signals_asset ON trading_signals (asset, created_at DESC);
CREATE INDEX idx_signals_direction ON trading_signals (direction, created_at DESC);

-- -----------------------------------------------
-- Market Snapshots (cached OHLCV + indicators)
-- -----------------------------------------------
CREATE TABLE IF NOT EXISTS market_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset           TEXT NOT NULL,
    market_type     TEXT NOT NULL CHECK (market_type IN ('crypto', 'forex')),
    timeframe       TEXT NOT NULL,
    ohlcv           JSONB NOT NULL,                           -- array of {open,high,low,close,volume,timestamp}
    indicators      JSONB DEFAULT '{}',                       -- computed indicators (RSI, MACD, etc.)
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_snapshots_asset ON market_snapshots (asset, timeframe, fetched_at DESC);

-- -----------------------------------------------
-- Historical Market Data (for backtesting)
-- -----------------------------------------------
CREATE TABLE IF NOT EXISTS historical_data (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset           TEXT NOT NULL,
    market_type     TEXT NOT NULL CHECK (market_type IN ('crypto', 'forex')),
    timeframe       TEXT NOT NULL,                            -- "1d", "1h", etc.
    timestamp       TIMESTAMPTZ NOT NULL,
    open            REAL NOT NULL,
    high            REAL NOT NULL,
    low             REAL NOT NULL,
    close           REAL NOT NULL,
    volume          REAL DEFAULT 0,
    UNIQUE (asset, timeframe, timestamp)
);

CREATE INDEX idx_historical_asset ON historical_data (asset, timeframe, timestamp);

-- -----------------------------------------------
-- News Sentiment
-- -----------------------------------------------
CREATE TABLE IF NOT EXISTS news_sentiment (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset           TEXT,                                     -- nullable = general market news
    headline        TEXT NOT NULL,
    source          TEXT,
    url             TEXT,
    sentiment_score REAL,                                     -- -1.0 to 1.0
    relevance_score REAL,                                     -- 0.0 to 1.0
    summary         TEXT,
    raw_data        JSONB DEFAULT '{}',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_news_asset ON news_sentiment (asset, fetched_at DESC);

-- -----------------------------------------------
-- Agent Runs (audit trail)
-- -----------------------------------------------
CREATE TABLE IF NOT EXISTS agent_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_type    TEXT NOT NULL CHECK (trigger_type IN ('scheduled', 'manual', 'backtest')),
    status          TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')) DEFAULT 'running',
    assets_analyzed TEXT[] DEFAULT '{}',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    logs            JSONB DEFAULT '[]',
    token_usage     JSONB DEFAULT '{}',                       -- {prompt_tokens, completion_tokens, total_cost}
    error_message   TEXT,
    metadata        JSONB DEFAULT '{}'
);

CREATE INDEX idx_runs_status ON agent_runs (status, started_at DESC);

-- -----------------------------------------------
-- Risk Configuration
-- -----------------------------------------------
CREATE TABLE IF NOT EXISTS risk_config (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    max_position_pct        REAL NOT NULL DEFAULT 5.0,
    max_daily_loss_pct      REAL NOT NULL DEFAULT 3.0,
    max_open_positions      INT NOT NULL DEFAULT 3,
    default_stop_loss_pct   REAL NOT NULL DEFAULT 2.0,
    default_take_profit_pct REAL NOT NULL DEFAULT 4.0,
    min_risk_reward_ratio   REAL NOT NULL DEFAULT 2.0,
    max_correlated_positions INT NOT NULL DEFAULT 2,
    drawdown_threshold_pct  REAL NOT NULL DEFAULT 10.0,
    drawdown_reduction_pct  REAL NOT NULL DEFAULT 50.0,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Insert default risk config
INSERT INTO risk_config (
    max_position_pct, max_daily_loss_pct, max_open_positions,
    default_stop_loss_pct, default_take_profit_pct
) VALUES (5.0, 3.0, 3, 2.0, 4.0)
ON CONFLICT DO NOTHING;

-- -----------------------------------------------
-- Portfolio
-- -----------------------------------------------
CREATE TABLE IF NOT EXISTS portfolio (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset           TEXT NOT NULL UNIQUE,
    market_type     TEXT NOT NULL CHECK (market_type IN ('crypto', 'forex')),
    quantity        REAL NOT NULL DEFAULT 0,
    avg_entry_price REAL NOT NULL DEFAULT 0,
    current_price   REAL DEFAULT 0,
    unrealized_pnl  REAL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------
-- Trade History
-- -----------------------------------------------
CREATE TABLE IF NOT EXISTS trade_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id       UUID REFERENCES trading_signals(id),
    asset           TEXT NOT NULL,
    market_type     TEXT NOT NULL CHECK (market_type IN ('crypto', 'forex')),
    direction       TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    entry_price     REAL NOT NULL,
    exit_price      REAL,
    quantity        REAL NOT NULL,
    pnl             REAL,
    pnl_pct         REAL,
    status          TEXT NOT NULL CHECK (status IN ('open', 'closed', 'cancelled')) DEFAULT 'open',
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at       TIMESTAMPTZ
);

CREATE INDEX idx_trades_status ON trade_history (status, opened_at DESC);
CREATE INDEX idx_trades_asset ON trade_history (asset, opened_at DESC);

-- -----------------------------------------------
-- Backtest Runs
-- -----------------------------------------------
CREATE TABLE IF NOT EXISTS backtest_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    description     TEXT,
    assets          TEXT[] NOT NULL,
    timeframe       TEXT NOT NULL,
    start_date      TIMESTAMPTZ NOT NULL,
    end_date        TIMESTAMPTZ NOT NULL,
    initial_capital REAL NOT NULL DEFAULT 10000,
    status          TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')) DEFAULT 'pending',
    config          JSONB NOT NULL DEFAULT '{}',              -- strategy parameters
    results         JSONB DEFAULT '{}',                       -- final metrics
    trades          JSONB DEFAULT '[]',                       -- array of simulated trades
    equity_curve    JSONB DEFAULT '[]',                       -- [{timestamp, equity}]
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

-- -----------------------------------------------
-- Enable Realtime on key tables
-- -----------------------------------------------
ALTER PUBLICATION supabase_realtime ADD TABLE trading_signals;
ALTER PUBLICATION supabase_realtime ADD TABLE agent_runs;
