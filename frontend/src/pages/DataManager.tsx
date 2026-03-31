import { useEffect, useState, useRef } from 'react';
import { Download, RefreshCw, CheckCircle, AlertCircle, Loader } from 'lucide-react';
import api from '../lib/api';
import CandlestickChart from '../components/CandlestickChart';

interface AssetStatus {
  asset: string;
  market_type: string;
  timeframe: string;
  bar_count: number;
  start_date: string | null;
  end_date: string | null;
}

interface OHLCVBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

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

export default function DataManager() {
  const [statuses, setStatuses] = useState<AssetStatus[]>([]);
  const [loadRunning, setLoadRunning] = useState(false);
  const [chartAsset, setChartAsset] = useState<string>('BTC');
  const [bars, setBars] = useState<OHLCVBar[]>([]);
  const [loadingChart, setLoadingChart] = useState(false);
  const [singleLoading, setSingleLoading] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    loadStatuses();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  useEffect(() => {
    loadChart(chartAsset);
  }, [chartAsset]);

  async function loadStatuses() {
    try {
      const { data } = await api.get('/data/status');
      setStatuses(data.assets || []);
    } catch { /* silent */ }
  }

  async function loadChart(asset: string) {
    setLoadingChart(true);
    try {
      const { data } = await api.get(`/data/ohlcv/${asset}`, {
        params: { timeframe: '1d', limit: 365 },
      });
      setBars(data.bars || []);
    } catch {
      setBars([]);
    } finally {
      setLoadingChart(false);
    }
  }

  async function handleLoadAll() {
    setLoadRunning(true);
    await api.post('/data/load-all', {
      crypto_assets: ALL_ASSETS.filter(a => a.type === 'crypto').map(a => a.symbol),
      forex_pairs: ALL_ASSETS.filter(a => a.type === 'forex').map(a => a.symbol),
    });

    // Poll until complete
    pollRef.current = setInterval(async () => {
      try {
        const { data } = await api.get('/data/load-status');
        if (!data.running) {
          setLoadRunning(false);
          if (pollRef.current) clearInterval(pollRef.current);
          await loadStatuses();
          await loadChart(chartAsset);
        }
      } catch { /* ignore */ }
    }, 5000);
  }

  async function handleLoadSingle(asset: string, type: string) {
    setSingleLoading(asset);
    try {
      await api.post('/data/load-asset', { asset, market_type: type });
      await loadStatuses();
      if (asset === chartAsset) await loadChart(asset);
    } finally {
      setSingleLoading(null);
    }
  }

  function getStatus(asset: string): AssetStatus | undefined {
    return statuses.find(s => s.asset === asset && s.timeframe === '1d');
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Data Manager</h2>
        <div className="flex gap-3">
          <button
            onClick={loadStatuses}
            className="px-3 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 text-sm
              flex items-center gap-2"
          >
            <RefreshCw size={14} /> Refresh
          </button>
          <button
            onClick={handleLoadAll}
            disabled={loadRunning}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm
              flex items-center gap-2 disabled:opacity-50"
          >
            {loadRunning
              ? <><Loader size={14} className="animate-spin" /> Loading all...</>
              : <><Download size={14} /> Load All Assets</>
            }
          </button>
        </div>
      </div>

      {loadRunning && (
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4 text-sm text-blue-400">
          Fetching historical data from Alpha Vantage for all assets (this takes several minutes due to API rate limits).
          The page will auto-refresh when complete.
        </div>
      )}

      {/* Asset grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {ALL_ASSETS.map(({ symbol, type }) => {
          const s = getStatus(symbol);
          const hasData = s && s.bar_count > 0;
          const isLoading = singleLoading === symbol;
          return (
            <div
              key={symbol}
              onClick={() => setChartAsset(symbol)}
              className={`bg-gray-900 rounded-xl border p-3 cursor-pointer transition-all ${
                chartAsset === symbol
                  ? 'border-green-500/50 ring-1 ring-green-500/20'
                  : 'border-gray-800 hover:border-gray-600'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-semibold text-white">{symbol}</span>
                {hasData
                  ? <CheckCircle size={14} className="text-green-400" />
                  : <AlertCircle size={14} className="text-gray-600" />
                }
              </div>
              <span className={`text-xs px-1.5 py-0.5 rounded ${
                type === 'crypto'
                  ? 'bg-yellow-500/10 text-yellow-400'
                  : 'bg-blue-500/10 text-blue-400'
              }`}>
                {type}
              </span>
              {s ? (
                <div className="text-xs text-gray-500 mt-1">
                  <p>{s.bar_count.toLocaleString()} bars</p>
                  <p>{s.start_date?.slice(0, 7)} → {s.end_date?.slice(0, 7)}</p>
                </div>
              ) : (
                <p className="text-xs text-gray-600 mt-1">No data</p>
              )}
              <button
                onClick={(e) => { e.stopPropagation(); handleLoadSingle(symbol, type); }}
                disabled={isLoading || loadRunning}
                className="mt-2 w-full text-xs py-1 rounded bg-gray-800 hover:bg-gray-700
                  text-gray-400 disabled:opacity-40 flex items-center justify-center gap-1"
              >
                {isLoading
                  ? <><Loader size={10} className="animate-spin" /> Loading</>
                  : <><Download size={10} /> {hasData ? 'Update' : 'Load'}</>
                }
              </button>
            </div>
          );
        })}
      </div>

      {/* Chart */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-300">{chartAsset} — Daily OHLCV</h3>
          {!loadingChart && bars.length > 0 && (
            <span className="text-xs text-gray-600">{bars.length} bars</span>
          )}
        </div>
        {loadingChart ? (
          <div className="flex items-center justify-center h-96 text-gray-600">
            <Loader size={24} className="animate-spin" />
          </div>
        ) : (
          <CandlestickChart bars={bars} height={400} />
        )}
      </div>
    </div>
  );
}
