import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import api from '../lib/api';
import type { OHLCVBar } from '../types';

const DEFAULT_ASSETS = ['BTC', 'ETH', 'SOL', 'EUR/USD', 'GBP/USD', 'USD/JPY'];

export default function MarketData() {
  const [selectedAsset, setSelectedAsset] = useState('BTC');
  const [bars, setBars] = useState<OHLCVBar[]>([]);
  const [latest, setLatest] = useState<OHLCVBar | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchData(selectedAsset);
  }, [selectedAsset]);

  async function fetchData(asset: string) {
    setLoading(true);
    const marketType = asset.includes('/') ? 'forex' : 'crypto';
    try {
      const { data } = await api.get(`/market/${asset}/snapshot`, {
        params: { market_type: marketType },
      });
      setBars(data.bars || []);
      setLatest(data.latest);
    } catch {
      setBars([]);
      setLatest(null);
    } finally {
      setLoading(false);
    }
  }

  const chartData = bars.map((b) => ({
    date: b.timestamp,
    price: b.close,
    volume: b.volume,
  }));

  const priceChange = bars.length >= 2
    ? ((bars[bars.length - 1].close - bars[bars.length - 2].close) / bars[bars.length - 2].close * 100)
    : 0;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white">Market Data</h2>

      {/* Asset selector */}
      <div className="flex gap-2 flex-wrap">
        {DEFAULT_ASSETS.map((asset) => (
          <button
            key={asset}
            onClick={() => setSelectedAsset(asset)}
            className={`px-4 py-2 rounded-lg text-sm transition-colors ${
              selectedAsset === asset
                ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                : 'bg-gray-900 text-gray-400 border border-gray-800 hover:bg-gray-800'
            }`}
          >
            {asset}
          </button>
        ))}
      </div>

      {/* Price header */}
      {latest && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <div className="flex items-center gap-4">
            <div>
              <p className="text-sm text-gray-500">{selectedAsset}</p>
              <p className="text-3xl font-bold text-white">${latest.close.toFixed(2)}</p>
            </div>
            <span className={`text-lg font-medium ${priceChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
            </span>
          </div>
          <div className="grid grid-cols-4 gap-4 mt-4 text-sm">
            <div>
              <span className="text-gray-500">Open</span>
              <p className="text-gray-300 font-mono">{latest.open.toFixed(2)}</p>
            </div>
            <div>
              <span className="text-gray-500">High</span>
              <p className="text-green-400 font-mono">{latest.high.toFixed(2)}</p>
            </div>
            <div>
              <span className="text-gray-500">Low</span>
              <p className="text-red-400 font-mono">{latest.low.toFixed(2)}</p>
            </div>
            <div>
              <span className="text-gray-500">Volume</span>
              <p className="text-gray-300 font-mono">{latest.volume.toLocaleString()}</p>
            </div>
          </div>
        </div>
      )}

      {/* Price chart */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <h3 className="text-sm font-medium text-gray-400 mb-4">Price Chart</h3>
        {loading ? (
          <div className="h-64 flex items-center justify-center text-gray-600">Loading...</div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#6b7280' }}
                tickFormatter={(v) => {
                  const d = new Date(v);
                  return `${d.getMonth() + 1}/${d.getDate()}`;
                }}
              />
              <YAxis
                tick={{ fontSize: 10, fill: '#6b7280' }}
                domain={['auto', 'auto']}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1f2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
                formatter={(value: number) => [`$${value.toFixed(2)}`, 'Price']}
              />
              <Line
                type="monotone"
                dataKey="price"
                stroke={priceChange >= 0 ? '#22c55e' : '#ef4444'}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
