import { useEffect, useState, useRef } from 'react';
import { Play, RefreshCw, Loader, TrendingUp } from 'lucide-react';
import api from '../lib/api';
import PnLChart from '../components/PnLChart';
import CandlestickChart from '../components/CandlestickChart';
import type { OHLCVBar, AgentBacktestRun, BacktestAgentRequest } from '../types';

const DEFAULT_CONFIG: BacktestAgentRequest = {
  assets: ['BTC', 'ETH', 'EUR/USD'],
  timeframe: '1d',
  start_date: '2024-01-01',
  end_date: '2025-12-31',
  initial_capital: 10000,
  position_size_pct: 5,
  stop_loss_pct: 2,
  take_profit_pct: 4,
  notes: '',
};

export default function Backtest() {
  const [config, setConfig] = useState<BacktestAgentRequest>(DEFAULT_CONFIG);
  const [runs, setRuns] = useState<AgentBacktestRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<AgentBacktestRun | null>(null);
  const [running, setRunning] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'strategies' | 'trades' | 'chart'>('overview');
  const [ohlcvBars, setOhlcvBars] = useState<OHLCVBar[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    loadRuns();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  async function loadRuns() {
    const { data } = await api.get('/backtest/runs');
    setRuns(data.runs || []);
  }

  async function openRun(run: AgentBacktestRun) {
    const { data } = await api.get(`/backtest/runs/${run.id}`);
    setSelectedRun(data);
    setActiveTab('overview');
    if (data.assets?.[0]) loadOhlcv(data.assets[0]);
  }

  async function loadOhlcv(asset: string) {
    try {
      const { data } = await api.get(`/data/ohlcv/${asset}`, { params: { timeframe: '1d', limit: 500 } });
      setOhlcvBars(data.bars || []);
    } catch { setOhlcvBars([]); }
  }

  async function handleRun() {
    setRunning(true);
    try {
      const { data } = await api.post('/backtest/agent-run', config);
      const runId = data.run_id;
      await loadRuns();
      pollRef.current = setInterval(async () => {
        try {
          const { data: run } = await api.get(`/backtest/runs/${runId}`);
          if (run.status !== 'running') {
            setRunning(false);
            if (pollRef.current) clearInterval(pollRef.current);
            await loadRuns();
            setSelectedRun(run);
            setActiveTab('overview');
            if (run.assets?.[0]) loadOhlcv(run.assets[0]);
          }
        } catch { /* ignore */ }
      }, 5000);
    } catch {
      setRunning(false);
    }
  }

  const r = selectedRun?.results;
  const bestMetrics = r?.best_result_metrics;
  const allStrategies = r?.strategy_results || [];

  // Trade markers for candlestick overlay
  const tradeMarkers = (selectedRun?.trades || []).map((t) => ({
    timestamp: t.entry_date?.slice(0, 10) ?? '',
    direction: 'BUY' as const,
    price: t.entry_price,
    label: `${t.pnl > 0 ? '+' : ''}${t.pnl.toFixed(0)}`,
  }));

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white">Agent Backtesting</h2>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
        {/* ── Config Panel ── */}
        <div className="xl:col-span-1 space-y-4">
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
            <h3 className="text-sm font-semibold text-gray-300">Strategy Conditions</h3>

            <div>
              <label className="text-xs text-gray-500">Assets (comma-separated)</label>
              <input
                className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                  text-sm text-white focus:outline-none focus:border-green-500"
                value={config.assets.join(', ')}
                onChange={(e) =>
                  setConfig({ ...config, assets: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })
                }
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-gray-500">Start</label>
                <input
                  type="date"
                  className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5
                    text-xs text-white focus:outline-none focus:border-green-500"
                  value={config.start_date}
                  onChange={(e) => setConfig({ ...config, start_date: e.target.value })}
                />
              </div>
              <div>
                <label className="text-xs text-gray-500">End</label>
                <input
                  type="date"
                  className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5
                    text-xs text-white focus:outline-none focus:border-green-500"
                  value={config.end_date}
                  onChange={(e) => setConfig({ ...config, end_date: e.target.value })}
                />
              </div>
            </div>

            {(
              [
                { key: 'initial_capital',   label: 'Capital ($)',      step: 1000 },
                { key: 'position_size_pct', label: 'Position Size %',  step: 0.5 },
                { key: 'stop_loss_pct',     label: 'Stop Loss %',      step: 0.5 },
                { key: 'take_profit_pct',   label: 'Take Profit %',    step: 0.5 },
              ] as { key: keyof BacktestAgentRequest; label: string; step: number }[]
            ).map(({ key, label, step }) => (
              <div key={key}>
                <label className="text-xs text-gray-500">{label}</label>
                <input
                  type="number"
                  step={step}
                  className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                    text-sm text-white focus:outline-none focus:border-green-500"
                  value={config[key] as number}
                  onChange={(e) => setConfig({ ...config, [key]: parseFloat(e.target.value) || 0 })}
                />
              </div>
            ))}

            <div>
              <label className="text-xs text-gray-500">Notes for agent</label>
              <textarea
                rows={2}
                className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                  text-sm text-white focus:outline-none focus:border-green-500 resize-none"
                placeholder="e.g. focus on momentum strategies"
                value={config.notes}
                onChange={(e) => setConfig({ ...config, notes: e.target.value })}
              />
            </div>

            <button
              onClick={handleRun}
              disabled={running}
              className="w-full py-2.5 bg-green-600 hover:bg-green-700 text-white rounded-lg
                text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {running ? (
                <><Loader size={14} className="animate-spin" /> Agent Running...</>
              ) : (
                <><Play size={14} /> Run Agent Backtest</>
              )}
            </button>

            {running && (
              <p className="text-xs text-gray-500 text-center">
                Agent is testing strategies. Results appear automatically when done (~60 s).
              </p>
            )}
          </div>

          {/* Previous runs */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-300">Previous Runs</h3>
              <button onClick={loadRuns} className="text-gray-600 hover:text-gray-400">
                <RefreshCw size={12} />
              </button>
            </div>
            <div className="space-y-2 max-h-64 overflow-auto">
              {runs.map((run) => (
                <button
                  key={run.id}
                  onClick={() => openRun(run)}
                  className={`w-full text-left p-2.5 rounded-lg border text-xs transition-colors ${
                    selectedRun?.id === run.id
                      ? 'bg-gray-800 border-green-500/30'
                      : 'bg-gray-800/50 border-gray-700/50 hover:bg-gray-800'
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <span className="text-white">{run.assets?.slice(0, 3).join(', ')}</span>
                    <span
                      className={
                        run.status === 'completed'
                          ? 'text-green-400'
                          : run.status === 'running'
                          ? 'text-yellow-400'
                          : 'text-red-400'
                      }
                    >
                      {run.status}
                    </span>
                  </div>
                  <p className="text-gray-600 mt-0.5">
                    {new Date(run.created_at).toLocaleDateString()}
                    {run.results?.best_strategy && (
                      <span className="ml-2 text-blue-400">✓ {run.results.best_strategy.name}</span>
                    )}
                  </p>
                </button>
              ))}
              {runs.length === 0 && (
                <p className="text-gray-600 text-center py-4">No runs yet</p>
              )}
            </div>
          </div>
        </div>

        {/* ── Results Panel ── */}
        <div className="xl:col-span-3 space-y-4">
          {selectedRun && r ? (
            <>
              {/* Tab navigation */}
              <div className="flex gap-2 border-b border-gray-800 pb-1">
                {(['overview', 'strategies', 'trades', 'chart'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-4 py-1.5 text-sm rounded-t-lg capitalize ${
                      activeTab === tab
                        ? 'text-white bg-gray-800 border-b-2 border-green-500'
                        : 'text-gray-500 hover:text-gray-300'
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {/* OVERVIEW */}
              {activeTab === 'overview' && (
                <div className="space-y-4">
                  {r.best_strategy && (
                    <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-4">
                      <p className="text-xs text-green-400 mb-1">RECOMMENDED STRATEGY</p>
                      <p className="text-lg font-bold text-white">{r.best_strategy.name}</p>
                      <p className="text-sm text-gray-400">{r.best_strategy.description}</p>
                    </div>
                  )}

                  {bestMetrics && (
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      {[
                        { label: 'Total Return',  value: `${bestMetrics.total_return_pct?.toFixed(2)}%`,  good: (bestMetrics.total_return_pct ?? 0) >= 0 },
                        { label: 'Sharpe Ratio',  value: bestMetrics.sharpe_ratio?.toFixed(2) ?? '—',     good: (bestMetrics.sharpe_ratio ?? 0) > 1 },
                        { label: 'Max Drawdown',  value: `${bestMetrics.max_drawdown_pct?.toFixed(2)}%`,  good: false },
                        { label: 'Win Rate',      value: `${bestMetrics.win_rate?.toFixed(1)}%`,          good: (bestMetrics.win_rate ?? 0) >= 50 },
                        { label: 'Total Trades',  value: String(bestMetrics.total_trades ?? 0),           good: null },
                        { label: 'Profit Factor', value: bestMetrics.profit_factor?.toFixed(2) ?? '—',   good: (bestMetrics.profit_factor ?? 0) > 1.5 },
                      ].map((m) => (
                        <div key={m.label} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
                          <span className="text-xs text-gray-500">{m.label}</span>
                          <p
                            className={`text-2xl font-bold mt-1 ${
                              m.good === null ? 'text-white' : m.good ? 'text-green-400' : 'text-red-400'
                            }`}
                          >
                            {m.value}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}

                  {selectedRun.equity_curve && selectedRun.equity_curve.length > 0 && (
                    <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
                      <PnLChart data={selectedRun.equity_curve} title="Best Strategy — Equity Curve" />
                    </div>
                  )}

                  {r.ranking_analysis && (
                    <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
                      <h4 className="text-sm font-semibold text-gray-300 mb-3">Agent Analysis</h4>
                      <pre className="text-sm text-gray-400 whitespace-pre-wrap font-sans leading-relaxed">
                        {r.ranking_analysis}
                      </pre>
                    </div>
                  )}

                  {r.recommendations && (
                    <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-5">
                      <h4 className="text-sm font-semibold text-blue-400 mb-2">Recommendations</h4>
                      <p className="text-sm text-gray-300 leading-relaxed">{r.recommendations}</p>
                    </div>
                  )}
                </div>
              )}

              {/* STRATEGIES */}
              {activeTab === 'strategies' && (
                <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
                  {r.strategy_selection_reasoning && (
                    <div className="p-4 border-b border-gray-800 text-sm text-gray-400">
                      <span className="text-gray-500">Selection rationale: </span>
                      {r.strategy_selection_reasoning}
                    </div>
                  )}
                  <div className="overflow-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-gray-500 border-b border-gray-800">
                          <th className="p-3">Strategy</th>
                          <th className="p-3">Asset</th>
                          <th className="p-3 text-right">Return</th>
                          <th className="p-3 text-right">Sharpe</th>
                          <th className="p-3 text-right">Max DD</th>
                          <th className="p-3 text-right">Win%</th>
                          <th className="p-3 text-right">Trades</th>
                          <th className="p-3 text-right">PF</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...allStrategies]
                          .sort((a, b) => b.sharpe_ratio - a.sharpe_ratio)
                          .map((s, i) => {
                            const isBest =
                              s.strategy_name === r.best_strategy?.name &&
                              s.asset === bestMetrics?.asset;
                            return (
                              <tr key={i} className={`border-b border-gray-800/50 ${isBest ? 'bg-green-500/5' : ''}`}>
                                <td className="p-3 font-mono text-xs text-gray-300">
                                  {isBest && <span className="text-green-400 mr-1">★</span>}
                                  {s.strategy_name}
                                </td>
                                <td className="p-3 text-white">{s.asset}</td>
                                <td className={`p-3 text-right font-mono ${s.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {s.total_return_pct?.toFixed(2)}%
                                </td>
                                <td className={`p-3 text-right font-mono ${s.sharpe_ratio >= 1 ? 'text-green-400' : 'text-gray-400'}`}>
                                  {s.sharpe_ratio?.toFixed(2)}
                                </td>
                                <td className="p-3 text-right font-mono text-red-400">
                                  {s.max_drawdown_pct?.toFixed(2)}%
                                </td>
                                <td className={`p-3 text-right font-mono ${s.win_rate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                                  {s.win_rate?.toFixed(1)}%
                                </td>
                                <td className="p-3 text-right text-gray-400">{s.total_trades}</td>
                                <td className={`p-3 text-right font-mono ${s.profit_factor >= 1.5 ? 'text-green-400' : 'text-gray-400'}`}>
                                  {s.profit_factor?.toFixed(2)}
                                </td>
                              </tr>
                            );
                          })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TRADES */}
              {activeTab === 'trades' && (
                <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
                  <div className="p-4 border-b border-gray-800 flex justify-between items-center">
                    <span className="text-sm text-gray-400">
                      Best strategy trades ({selectedRun.trades?.length ?? 0})
                    </span>
                    <div className="flex gap-4 text-xs">
                      <span className="text-green-400">
                        ↑ {selectedRun.trades?.filter((t) => t.pnl > 0).length ?? 0} wins
                      </span>
                      <span className="text-red-400">
                        ↓ {selectedRun.trades?.filter((t) => t.pnl <= 0).length ?? 0} losses
                      </span>
                    </div>
                  </div>
                  <div className="max-h-96 overflow-auto">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-gray-900">
                        <tr className="text-left text-gray-500 border-b border-gray-800">
                          <th className="p-3">Entry Date</th>
                          <th className="p-3">Exit Date</th>
                          <th className="p-3 text-right">Entry</th>
                          <th className="p-3 text-right">Exit</th>
                          <th className="p-3 text-right">P&amp;L</th>
                          <th className="p-3 text-right">%</th>
                          <th className="p-3 text-right">Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(selectedRun.trades || []).map((t, i) => (
                          <tr key={i} className="border-b border-gray-800/50">
                            <td className="p-3 text-gray-400 text-xs">{t.entry_date?.slice(0, 10)}</td>
                            <td className="p-3 text-gray-400 text-xs">{t.exit_date?.slice(0, 10)}</td>
                            <td className="p-3 text-right font-mono text-xs text-gray-300">
                              {t.entry_price?.toFixed(2)}
                            </td>
                            <td className="p-3 text-right font-mono text-xs text-gray-300">
                              {t.exit_price?.toFixed(2)}
                            </td>
                            <td
                              className={`p-3 text-right font-mono text-xs ${
                                t.pnl > 0 ? 'text-green-400' : 'text-red-400'
                              }`}
                            >
                              ${t.pnl?.toFixed(2)}
                            </td>
                            <td
                              className={`p-3 text-right font-mono text-xs ${
                                t.pnl_pct > 0 ? 'text-green-400' : 'text-red-400'
                              }`}
                            >
                              {t.pnl_pct?.toFixed(2)}%
                            </td>
                            <td className="p-3 text-right text-xs text-gray-600">{t.exit_reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* CHART */}
              {activeTab === 'chart' && (
                <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
                  <div className="flex gap-2 flex-wrap">
                    {selectedRun.assets?.map((asset) => (
                      <button
                        key={asset}
                        onClick={() => loadOhlcv(asset)}
                        className="px-3 py-1 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg"
                      >
                        {asset}
                      </button>
                    ))}
                  </div>
                  <CandlestickChart
                    bars={ohlcvBars}
                    trades={tradeMarkers}
                    height={480}
                    title="Price chart with trade entries"
                  />
                  <p className="text-xs text-gray-600">
                    Green arrows = trade entries. Labels show realized P&amp;L.
                  </p>
                </div>
              )}
            </>
          ) : (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center text-gray-600">
              <TrendingUp size={40} className="mx-auto mb-3 opacity-20" />
              <p className="text-lg">Configure and run an agent backtest</p>
              <p className="text-sm mt-1">
                The agent autonomously tests multiple strategies and recommends the best one for your conditions.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
