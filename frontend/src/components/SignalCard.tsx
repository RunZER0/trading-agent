import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { TradingSignal } from '../types';

interface Props {
  signal: TradingSignal;
  onClick?: () => void;
}

const directionConfig = {
  BUY: { color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/20', icon: TrendingUp },
  SELL: { color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20', icon: TrendingDown },
  HOLD: { color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/20', icon: Minus },
};

export default function SignalCard({ signal, onClick }: Props) {
  const config = directionConfig[signal.direction];
  const Icon = config.icon;

  return (
    <div
      onClick={onClick}
      className={`rounded-xl border ${config.border} ${config.bg} p-4 cursor-pointer
        hover:brightness-110 transition-all`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold text-white">{signal.asset}</span>
          <span className="text-xs text-gray-500 uppercase">{signal.market_type}</span>
        </div>
        <div className={`flex items-center gap-1 font-bold ${config.color}`}>
          <Icon size={16} />
          {signal.direction}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-gray-500">Confidence</span>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-gray-700 rounded-full">
              <div
                className={`h-full rounded-full ${
                  signal.confidence >= 75 ? 'bg-green-500' :
                  signal.confidence >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                }`}
                style={{ width: `${signal.confidence}%` }}
              />
            </div>
            <span className="text-white font-mono">{signal.confidence}%</span>
          </div>
        </div>
        <div>
          <span className="text-gray-500">Entry</span>
          <p className="text-white font-mono">
            {signal.entry_price?.toFixed(2) ?? '—'}
          </p>
        </div>
        <div>
          <span className="text-gray-500">Stop Loss</span>
          <p className="text-red-400 font-mono">
            {signal.stop_loss?.toFixed(2) ?? '—'}
          </p>
        </div>
        <div>
          <span className="text-gray-500">Take Profit</span>
          <p className="text-green-400 font-mono">
            {signal.take_profit?.toFixed(2) ?? '—'}
          </p>
        </div>
      </div>

      <p className="text-xs text-gray-600 mt-3">
        {new Date(signal.created_at).toLocaleString()}
      </p>
    </div>
  );
}
