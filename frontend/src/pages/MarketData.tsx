import { useEffect, useState } from 'react';
import { RefreshCw, BarChart2, TrendingUp } from 'lucide-react';
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
  const [chartMode, setChartMode] = useState<'candle' | 'line'>('candle');
  const [bars, setBars] = useState<OHLCVBar[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchData(selectedAsset, timeframe);
  }, [selectedAsset, timeframe]);

  async function fetchData(asset: string, tf: string) {
    setLoading(true);
    const tfCfg = TIMEFRAMES.find(t => t.value === tf) ?? TIMEFRAMES[0];
    try {
      const { data } = await api.get('/data/ohlcv', {
        params: { asset, timeframe: tf, limit: tfCfg.limit },
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
          <div className="flex items-center gap-2 shrink-0">
            {/* Chart mode toggle */}
            <div className="flex bg-gray-800 rounded-lg p-0.5">
              <button
                onClick={() => setChartMode('candle')}
                title="Candlestick"
                className={`px-2 py-1 rounded-md transition-colors ${chartMode === 'candle' ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300'}`}
              >
                <BarChart2 size={14} />
              </button>
              <button
                onClick={() => setChartMode('line')}
                title="Line"
                className={`px-2 py-1 rounded-md transition-colors ${chartMode === 'line' ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300'}`}
              >
                <TrendingUp size={14} />
              </button>
            </div>
            {/* Timeframe tabs */}
            <div className="flex bg-gray-800 rounded-lg p-0.5">
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
        </div>

        {/* Candlestick chart */}
        {loading ? (
          <div className="flex items-center justify-center" style={{ height: 420 }}>
            <div className="text-gray-600 text-sm">Loading {bars.length > 0 ? 'new timeframe...' : 'chart...'}</div>
          </div>
        ) : (
          <CandlestickChart bars={bars} height={420} mode={chartMode} />
        )}
        {!loading && bars.length > 0 && (
          <p className="text-xs text-gray-700 text-right mt-1">{bars.length} bars · {timeframe.toUpperCase()} · from Supabase</p>
        )}
      </div>
    </div>
  );
}
