import { useEffect, useState } from 'react';
import api from '../lib/api';
import type { PortfolioPosition, TradeRecord } from '../types';

export default function Portfolio() {
  const [positions, setPositions] = useState<PortfolioPosition[]>([]);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [totalValue, setTotalValue] = useState(0);
  const [totalPnl, setTotalPnl] = useState(0);

  useEffect(() => {
    async function load() {
      const [pRes, tRes] = await Promise.all([
        api.get('/portfolio'),
        api.get('/portfolio/trades?limit=30'),
      ]);
      setPositions(pRes.data.positions);
      setTotalValue(pRes.data.total_value);
      setTotalPnl(pRes.data.total_unrealized_pnl);
      setTrades(tRes.data.trades);
    }
    load();
  }, []);

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white">Portfolio</h2>

      {/* Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <span className="text-sm text-gray-500">Total Value</span>
          <p className="text-2xl font-bold text-white">${totalValue.toFixed(2)}</p>
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <span className="text-sm text-gray-500">Unrealized P&L</span>
          <p className={`text-2xl font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${totalPnl.toFixed(2)}
          </p>
        </div>
      </div>

      {/* Open Positions */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-3">Open Positions</h3>
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-500">
                <th className="text-left p-3">Asset</th>
                <th className="text-right p-3">Qty</th>
                <th className="text-right p-3">Avg Entry</th>
                <th className="text-right p-3">Current</th>
                <th className="text-right p-3">P&L</th>
              </tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center p-6 text-gray-600">
                    No open positions
                  </td>
                </tr>
              ) : (
                positions.map((p) => (
                  <tr key={p.id} className="border-b border-gray-800/50">
                    <td className="p-3 text-white font-medium">{p.asset}</td>
                    <td className="p-3 text-right font-mono text-gray-300">{p.quantity.toFixed(4)}</td>
                    <td className="p-3 text-right font-mono text-gray-300">{p.avg_entry_price.toFixed(4)}</td>
                    <td className="p-3 text-right font-mono text-gray-300">{p.current_price.toFixed(4)}</td>
                    <td className={`p-3 text-right font-mono ${p.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${p.unrealized_pnl.toFixed(2)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Trade History */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-3">Trade History</h3>
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-500">
                <th className="text-left p-3">Asset</th>
                <th className="text-left p-3">Dir</th>
                <th className="text-right p-3">Entry</th>
                <th className="text-right p-3">Exit</th>
                <th className="text-right p-3">P&L</th>
                <th className="text-right p-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center p-6 text-gray-600">
                    No trades yet
                  </td>
                </tr>
              ) : (
                trades.map((t) => (
                  <tr key={t.id} className="border-b border-gray-800/50">
                    <td className="p-3 text-white">{t.asset}</td>
                    <td className={`p-3 ${t.direction === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                      {t.direction}
                    </td>
                    <td className="p-3 text-right font-mono text-gray-300">{t.entry_price.toFixed(4)}</td>
                    <td className="p-3 text-right font-mono text-gray-300">{t.exit_price?.toFixed(4) ?? '—'}</td>
                    <td className={`p-3 text-right font-mono ${(t.pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {t.pnl != null ? `$${t.pnl.toFixed(2)}` : '—'}
                    </td>
                    <td className="p-3 text-right">
                      <span className={`text-xs px-2 py-1 rounded-full ${
                        t.status === 'open' ? 'bg-blue-500/10 text-blue-400' :
                        t.status === 'closed' ? 'bg-gray-700 text-gray-300' :
                        'bg-yellow-500/10 text-yellow-400'
                      }`}>
                        {t.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
