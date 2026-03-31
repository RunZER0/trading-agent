import { useEffect, useState } from 'react';
import { Play, Download } from 'lucide-react';
import api from '../lib/api';
import PnLChart from '../components/PnLChart';
import type { BacktestRun, BacktestConfig } from '../types';

const defaultConfig: BacktestConfig = {
  assets: ['BTC', 'ETH'],
  timeframe: '1d',
  start_date: '2025-01-01',
  end_date: '2026-03-01',
  initial_capital: 10000,
  strategy_params: { signal_interval: 5, max_position_pct: 5 },
};

export default function Backtest() {
  const [config, setConfig] = useState<BacktestConfig>(defaultConfig);
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<BacktestRun | null>(null);
  const [running, setRunning] = useState(false);
  const [loadingData, setLoadingData] = useState(false);

  useEffect(() => {
    loadRuns();
  }, []);

  async function loadRuns() {
    const { data } = await api.get('/backtest/runs');
    setRuns(data.runs);
  }

  async function handleLoadData() {
    setLoadingData(true);
    try {
      await api.post('/backtest/load-data', {
        assets: config.assets,
        timeframe: config.timeframe,
      });
    } finally {
      setLoadingData(false);
    }
  }

  async function handleRun() {
    setRunning(true);
    try {
      const { data } = await api.post('/backtest/run', config);
      setSelectedRun(data);
      await loadRuns();
    } finally {
      setRunning(false);
    }
  }

  async function viewRun(id: string) {
    const { data } = await api.get(`/backtest/runs/${id}`);
    setSelectedRun(data);
  }

  const r = selectedRun?.results;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white">Backtesting</h2>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Config panel */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
          <h3 className="text-sm font-medium text-gray-400">Configuration</h3>

          <div>
            <label className="text-xs text-gray-500">Assets (comma-separated)</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white mt-1
                focus:outline-none focus:border-green-500"
              value={config.assets.join(',')}
              onChange={(e) => setConfig({ ...config, assets: e.target.value.split(',').map((s) => s.trim()) })}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500">Start Date</label>
              <input
                type="date"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white mt-1
                  focus:outline-none focus:border-green-500"
                value={config.start_date}
                onChange={(e) => setConfig({ ...config, start_date: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-gray-500">End Date</label>
              <input
                type="date"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white mt-1
                  focus:outline-none focus:border-green-500"
                value={config.end_date}
                onChange={(e) => setConfig({ ...config, end_date: e.target.value })}
              />
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-500">Initial Capital ($)</label>
            <input
              type="number"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white mt-1
                focus:outline-none focus:border-green-500"
              value={config.initial_capital}
              onChange={(e) => setConfig({ ...config, initial_capital: parseFloat(e.target.value) || 10000 })}
            />
          </div>

          <div>
            <label className="text-xs text-gray-500">Timeframe</label>
            <select
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white mt-1
                focus:outline-none focus:border-green-500"
              value={config.timeframe}
              onChange={(e) => setConfig({ ...config, timeframe: e.target.value })}
            >
              <option value="1d">Daily</option>
              <option value="1h">Hourly</option>
            </select>
          </div>

          <div className="flex gap-2 pt-2">
            <button
              onClick={handleLoadData}
              disabled={loadingData}
              className="flex-1 px-3 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 text-sm
                flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <Download size={14} />
              {loadingData ? 'Loading...' : 'Load Data'}
            </button>
            <button
              onClick={handleRun}
              disabled={running}
              className="flex-1 px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm
                flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <Play size={14} />
              {running ? 'Running...' : 'Run Backtest'}
            </button>
          </div>
        </div>

        {/* Results */}
        <div className="lg:col-span-2 space-y-4">
          {selectedRun && r ? (
            <>
              {/* Metrics */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {[
                  { label: 'Total Return', value: `${r.total_return_pct?.toFixed(2)}%`, color: (r.total_return_pct ?? 0) >= 0 ? 'text-green-400' : 'text-red-400' },
                  { label: 'Sharpe Ratio', value: r.sharpe_ratio?.toFixed(2) ?? '—', color: 'text-blue-400' },
                  { label: 'Max Drawdown', value: `${r.max_drawdown_pct?.toFixed(2)}%`, color: 'text-red-400' },
                  { label: 'Win Rate', value: `${r.win_rate?.toFixed(1)}%`, color: 'text-green-400' },
                  { label: 'Total Trades', value: r.total_trades ?? 0, color: 'text-white' },
                  { label: 'Profit Factor', value: r.profit_factor?.toFixed(2) ?? '—', color: 'text-yellow-400' },
                ].map((m) => (
                  <div key={m.label} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
                    <span className="text-xs text-gray-500">{m.label}</span>
                    <p className={`text-xl font-bold ${m.color}`}>{m.value}</p>
                  </div>
                ))}
              </div>

              {/* Equity curve */}
              <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
                <PnLChart data={selectedRun.equity_curve || []} title="Equity Curve" />
              </div>

              {/* Trade list */}
              <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
                <h3 className="text-sm font-medium text-gray-400 p-4 border-b border-gray-800">
                  Backtest Trades ({selectedRun.trades?.length ?? 0})
                </h3>
                <div className="max-h-64 overflow-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-gray-900">
                      <tr className="text-gray-500 border-b border-gray-800">
                        <th className="text-left p-3">Asset</th>
                        <th className="text-left p-3">Dir</th>
                        <th className="text-right p-3">Entry</th>
                        <th className="text-right p-3">Exit</th>
                        <th className="text-right p-3">P&L</th>
                        <th className="text-right p-3">Conf</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(selectedRun.trades || []).map((t, i) => (
                        <tr key={i} className="border-b border-gray-800/50">
                          <td className="p-3 text-white">{t.asset}</td>
                          <td className={`p-3 ${t.direction === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                            {t.direction}
                          </td>
                          <td className="p-3 text-right font-mono text-gray-300">{t.entry_price.toFixed(2)}</td>
                          <td className="p-3 text-right font-mono text-gray-300">{t.exit_price.toFixed(2)}</td>
                          <td className={`p-3 text-right font-mono ${t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            ${t.pnl.toFixed(2)}
                          </td>
                          <td className="p-3 text-right text-gray-400">{t.confidence}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center text-gray-600">
              Configure and run a backtest, or select a previous run from below.
            </div>
          )}

          {/* Previous runs */}
          <div>
            <h3 className="text-sm font-medium text-gray-400 mb-2">Previous Runs</h3>
            <div className="space-y-2">
              {runs.map((run) => (
                <button
                  key={run.id}
                  onClick={() => viewRun(run.id)}
                  className={`w-full text-left p-3 rounded-lg border text-sm transition-colors ${
                    selectedRun?.id === run.id
                      ? 'bg-gray-800 border-green-500/30'
                      : 'bg-gray-900 border-gray-800 hover:bg-gray-800'
                  }`}
                >
                  <div className="flex justify-between">
                    <span className="text-white">{run.name || run.id.slice(0, 8)}</span>
                    <span className={`text-xs ${
                      run.status === 'completed' ? 'text-green-400' :
                      run.status === 'running' ? 'text-yellow-400' : 'text-red-400'
                    }`}>
                      {run.status}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {run.assets?.join(', ')} &middot; {new Date(run.created_at).toLocaleDateString()}
                    {run.results?.total_return_pct != null && (
                      <span className={`ml-2 ${run.results.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {run.results.total_return_pct.toFixed(2)}%
                      </span>
                    )}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
