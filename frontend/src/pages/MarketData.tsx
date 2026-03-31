import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import api from '../lib/api';
import CandlestickChart from '../components/CandlestickChart';
import type { OHLCVBar } from '../types';

const ALL_ASSETS = [
  { symbol: 'BTC', type: 'crypto' },
  { symbol: 'ETH', type: 'crypto' },
  { symbol: 'SOL', type: 'crypto' },
  { symbol: 'BNB', type: 'crypto' },
  { symbol: 'ADA', type: 'crypto' },
  { symbol: 'EUR/USD', type: 'forex' },
  { symbol: 'GBP/USD', type: 'forex' },
  { symbol: 'USD/JPY', type: 'forex' },
  { symbol: 'AUD/USD', type: 'forex' },
  { symbol: 'USD/CAD', type: 'forex' },
];

const TIMEFRAMES = [
  { label: '1D', value: '1d', limit: 365 },
  { label: '4H', value: '4h', limit: 500 },
  { label: '1H', value: '1h', limit: 720 },
  { label: '15m', value: '15m', limit: 500 },
];

export default function MarketData() {
  const [selectedAsset, setSelectedAsset] = useState('BTC');
  const [timeframe, setTimeframe] = useState('1d');
  const [bars, setBars] = useState<OHLCVBar[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchData(selectedAsset, timeframe);
  }, [selectedAsset, timeframe]);

  async function fetchData(asset: string, tf: string) {
    setLoading(true);
    const tfCfg = TIMEFRAMES.find(t => t.value === tf) ?? TIMEFRAMES[0];
    try {
      const { data } = await api.get(`/data/ohlcv/${encodeURIComponent(asset)}`, {
        params: { timeframe: tf, limit: tfCfg.limit },
      });
      setBars(data.bars || []);
    } catch {
      setBars([]);
    } finally {
      setLoading(false);
    }
  }

  const latest = bars.length > 0 ? bars[bars.length - 1] : null;
  const priceChange = bars.length >= 2
    ? ((bars[bars.length - 1].close - bars[bars.length - 2].close) / bars[bars.length - 2].close * 100)
    : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Market Data</h2>
        <button
          onClick={() => fetchData(selectedAsset, timeframe)}
          className="px-3 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 text-sm flex items-center gap-2"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Asset selector */}
      <div className="flex gap-2 flex-wrap">
        {ALL_ASSETS.map(({ symbol, type }) => (
          <button
            key={symbol}
            onClick={() => setSelectedAsset(symbol)}
            className={`px-4 py-2 rounded-lg text-sm transition-colors border ${
              selectedAsset === symbol
                ? 'bg-green-500/20 text-green-400 border-green-500/30'
                : type === 'crypto'
                  ? 'bg-yellow-500/5 text-yellow-400/70 border-yellow-500/20 hover:bg-yellow-500/10'
                  : 'bg-blue-500/5 text-blue-400/70 border-blue-500/20 hover:bg-blue-500/10'
            }`}
          >
            {symbol}
          </button>
        ))}
      </div>

      {/* Price header + timeframe tabs on same row */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <div className="flex items-start justify-between mb-4">
          {latest ? (
            <div>
              <p className="text-sm text-gray-500 mb-1">{selectedAsset}</p>
              <div className="flex items-baseline gap-3">
                <p className="text-3xl font-bold text-white font-mono">
                  {latest.close >= 1 ? `$${latest.close.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : latest.close.toFixed(5)}
                </p>
                <span className={`text-base font-medium ${priceChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                </span>
              </div>
              <div className="grid grid-cols-4 gap-4 mt-3 text-sm">
                <div><span className="text-gray-500 text-xs">Open</span><p className="text-gray-300 font-mono">{latest.open.toFixed(latest.open >= 1 ? 2 : 5)}</p></div>
                <div><span className="text-gray-500 text-xs">High</span><p className="text-green-400 font-mono">{latest.high.toFixed(latest.high >= 1 ? 2 : 5)}</p></div>
                <div><span className="text-gray-500 text-xs">Low</span><p className="text-red-400 font-mono">{latest.low.toFixed(latest.low >= 1 ? 2 : 5)}</p></div>
                <div><span className="text-gray-500 text-xs">Volume</span><p className="text-gray-300 font-mono">{latest.volume > 0 ? latest.volume.toLocaleString(undefined, {maximumFractionDigits: 0}) : '—'}</p></div>
              </div>
            </div>
          ) : (
            <div className="text-gray-600 text-sm">{loading ? 'Loading...' : 'No data'}</div>
          )}

          {/* Timeframe tabs */}
          <div className="flex bg-gray-800 rounded-lg p-0.5 ml-4 shrink-0">
            {TIMEFRAMES.map(tf => (
              <button
                key={tf.value}
                onClick={() => setTimeframe(tf.value)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  timeframe === tf.value
                    ? 'bg-gray-700 text-white'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </div>

        {/* Candlestick chart */}
        {loading ? (
          <div className="flex items-center justify-center" style={{ height: 420 }}>
            <div className="text-gray-600 text-sm">Loading {bars.length > 0 ? 'new timeframe...' : 'chart...'}</div>
          </div>
        ) : (
          <CandlestickChart bars={bars} height={420} />
        )}
        {!loading && bars.length > 0 && (
          <p className="text-xs text-gray-700 text-right mt-1">{bars.length} bars · {timeframe.toUpperCase()} · from Supabase</p>
        )}
      </div>
    </div>
  );
}


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
    try {
      const { data } = await api.get(`/data/ohlcv/${encodeURIComponent(asset)}`, {
        params: { timeframe: '1d', limit: 365 },
      });
      const fetchedBars: OHLCVBar[] = data.bars || [];
      setBars(fetchedBars);
      setLatest(fetchedBars.length > 0 ? fetchedBars[fetchedBars.length - 1] : null);
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
