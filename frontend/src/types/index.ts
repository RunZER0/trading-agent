export interface TradingSignal {
  id: string;
  asset: string;
  market_type: 'crypto' | 'forex';
  timeframe: string;
  direction: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  position_size_pct: number | null;
  reasoning: Record<string, unknown>;
  metadata: Record<string, unknown>;
  agent_run_id: string | null;
  created_at: string;
}

export interface AgentRun {
  id: string;
  trigger_type: string;
  status: 'running' | 'completed' | 'failed';
  assets_analyzed: string[];
  started_at: string;
  completed_at: string | null;
  logs: Array<{ node: string; message: string; timestamp: string }>;
  token_usage: Record<string, number>;
  error_message: string | null;
}

export interface PortfolioPosition {
  id: string;
  asset: string;
  market_type: string;
  quantity: number;
  avg_entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  updated_at: string;
}

export interface TradeRecord {
  id: string;
  signal_id: string | null;
  asset: string;
  direction: string;
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  pnl: number | null;
  pnl_pct: number | null;
  status: 'open' | 'closed' | 'cancelled';
  opened_at: string;
  closed_at: string | null;
}

export interface RiskConfig {
  id?: string;
  max_position_pct: number;
  max_daily_loss_pct: number;
  max_open_positions: number;
  default_stop_loss_pct: number;
  default_take_profit_pct: number;
  min_risk_reward_ratio: number;
  max_correlated_positions: number;
  drawdown_threshold_pct: number;
  drawdown_reduction_pct: number;
}

export interface BacktestConfig {
  assets: string[];
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  strategy_params: Record<string, unknown>;
}

export interface BacktestRun {
  id: string;
  name: string;
  assets: string[];
  timeframe: string;
  start_date: string;
  end_date: string;
  status: string;
  results: {
    total_return_pct?: number;
    sharpe_ratio?: number;
    max_drawdown_pct?: number;
    win_rate?: number;
    total_trades?: number;
    profit_factor?: number;
  };
  trades: Array<{
    asset: string;
    direction: string;
    entry_price: number;
    exit_price: number;
    pnl: number;
    pnl_pct: number;
    confidence: number;
  }>;
  equity_curve: Array<{ timestamp: string; equity: number }>;
  created_at: string;
}

export interface OHLCVBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface BacktestAgentRequest {
  assets: string[];
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  position_size_pct: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  notes: string;
}

export interface StrategyResult {
  strategy_name: string;
  asset: string;
  total_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  win_rate: number;
  total_trades: number;
  profit_factor: number;
  avg_trade_duration_days: number;
}

export interface AgentBacktestRun {
  id: string;
  name: string;
  assets: string[];
  timeframe: string;
  start_date: string;
  end_date: string;
  status: 'running' | 'completed' | 'failed';
  initial_capital: number;
  results: {
    strategy_results?: StrategyResult[];
    best_strategy?: { name: string; description: string };
    best_result_metrics?: StrategyResult;
    ranking_analysis?: string;
    recommendations?: string;
    strategy_selection_reasoning?: string;
  } | null;
  equity_curve?: Array<{ timestamp: string; equity: number }>;
  trades?: Array<{
    entry_date: string;
    exit_date: string;
    entry_price: number;
    exit_price: number;
    pnl: number;
    pnl_pct: number;
    exit_reason: string;
    duration_days: number;
  }>;
  created_at: string;
  completed_at: string | null;
}
