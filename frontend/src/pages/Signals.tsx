import { useState } from 'react';
import { useSignals } from '../hooks/useSignals';
import SignalCard from '../components/SignalCard';
import type { TradingSignal } from '../types';

export default function Signals() {
  const [assetFilter, setAssetFilter] = useState('');
  const [dirFilter, setDirFilter] = useState('');
  const { signals, loading, refresh } = useSignals({
    asset: assetFilter || undefined,
    direction: dirFilter || undefined,
  });
  const [selected, setSelected] = useState<TradingSignal | null>(null);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Trading Signals</h2>
        <button
          onClick={refresh}
          className="px-4 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 text-sm"
        >
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <input
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
            placeholder-gray-600 focus:outline-none focus:border-green-500"
          placeholder="Filter by asset..."
          value={assetFilter}
          onChange={(e) => setAssetFilter(e.target.value)}
        />
        <select
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
            focus:outline-none focus:border-green-500"
          value={dirFilter}
          onChange={(e) => setDirFilter(e.target.value)}
        >
          <option value="">All Directions</option>
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
          <option value="HOLD">HOLD</option>
        </select>
      </div>

      {loading ? (
        <p className="text-gray-500">Loading signals...</p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Signal cards */}
          <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4">
            {signals.map((sig) => (
              <SignalCard
                key={sig.id}
                signal={sig}
                onClick={() => setSelected(sig)}
              />
            ))}
            {signals.length === 0 && (
              <p className="text-gray-600 col-span-2 text-center py-8">No signals found</p>
            )}
          </div>

          {/* Detail panel */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 h-fit sticky top-6">
            {selected ? (
              <div>
                <h3 className="text-lg font-semibold text-white mb-4">
                  {selected.asset} — {selected.direction}
                </h3>
                <div className="space-y-3 text-sm">
                  <div>
                    <span className="text-gray-500">Confidence</span>
                    <p className="text-white font-mono">{selected.confidence}%</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Entry / SL / TP</span>
                    <p className="text-white font-mono">
                      {selected.entry_price?.toFixed(4)} / {selected.stop_loss?.toFixed(4)} / {selected.take_profit?.toFixed(4)}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-500">Position Size</span>
                    <p className="text-white">{selected.position_size_pct ?? '—'}%</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Reasoning</span>
                    <pre className="text-gray-300 text-xs mt-1 whitespace-pre-wrap bg-gray-800 rounded-lg p-3 max-h-64 overflow-auto">
                      {JSON.stringify(selected.reasoning, null, 2)}
                    </pre>
                  </div>
                  <p className="text-xs text-gray-600">
                    {new Date(selected.created_at).toLocaleString()}
                  </p>
                </div>
              </div>
            ) : (
              <p className="text-gray-600 text-center py-8">Click a signal to view details</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
