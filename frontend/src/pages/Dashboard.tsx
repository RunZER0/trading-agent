import { useEffect, useState } from 'react';
import { Activity, TrendingUp, AlertTriangle, Bot } from 'lucide-react';
import api from '../lib/api';
import SignalCard from '../components/SignalCard';
import type { TradingSignal, AgentRun } from '../types';

export default function Dashboard() {
  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [latestRun, setLatestRun] = useState<AgentRun | null>(null);
  const [pnl, setPnl] = useState<{ total_realized_pnl: number; win_rate: number; total_trades: number } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [sigRes, runRes, pnlRes] = await Promise.all([
          api.get('/signals?limit=6'),
          api.get('/agent/runs?limit=1'),
          api.get('/portfolio/pnl'),
        ]);
        setSignals(sigRes.data.signals);
        setLatestRun(runRes.data.runs?.[0] ?? null);
        setPnl(pnlRes.data);
      } catch {
        // handle errors silently on dashboard
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return <div className="flex items-center justify-center h-full text-gray-500">Loading...</div>;
  }

  const stats = [
    {
      label: 'Total P&L',
      value: pnl ? `$${pnl.total_realized_pnl.toFixed(2)}` : '$0.00',
      icon: TrendingUp,
      color: (pnl?.total_realized_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400',
    },
    {
      label: 'Win Rate',
      value: pnl ? `${pnl.win_rate}%` : '0%',
      icon: Activity,
      color: 'text-blue-400',
    },
    {
      label: 'Total Trades',
      value: pnl?.total_trades ?? 0,
      icon: AlertTriangle,
      color: 'text-yellow-400',
    },
    {
      label: 'Agent Status',
      value: latestRun?.status?.toUpperCase() ?? 'IDLE',
      icon: Bot,
      color: latestRun?.status === 'completed' ? 'text-green-400' :
             latestRun?.status === 'running' ? 'text-yellow-400' : 'text-gray-400',
    },
  ];

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white">Dashboard</h2>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s) => (
          <div
            key={s.label}
            className="bg-gray-900 rounded-xl border border-gray-800 p-5"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-500">{s.label}</span>
              <s.icon size={18} className={s.color} />
            </div>
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Recent Signals */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-3">Recent Signals</h3>
        {signals.length === 0 ? (
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center text-gray-600">
            No signals yet. Run the agent to generate trading signals.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {signals.map((sig) => (
              <SignalCard key={sig.id} signal={sig} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
