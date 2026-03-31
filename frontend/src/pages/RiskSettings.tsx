import { useEffect, useState } from 'react';
import { Save } from 'lucide-react';
import api from '../lib/api';
import type { RiskConfig } from '../types';

const defaultConfig: RiskConfig = {
  max_position_pct: 5,
  max_daily_loss_pct: 3,
  max_open_positions: 3,
  default_stop_loss_pct: 2,
  default_take_profit_pct: 4,
  min_risk_reward_ratio: 2,
  max_correlated_positions: 2,
  drawdown_threshold_pct: 10,
  drawdown_reduction_pct: 50,
};

const fields: Array<{ key: keyof RiskConfig; label: string; suffix: string; description: string }> = [
  { key: 'max_position_pct', label: 'Max Position Size', suffix: '%', description: 'Maximum portfolio % per trade' },
  { key: 'max_daily_loss_pct', label: 'Max Daily Loss', suffix: '%', description: 'Circuit breaker — halts trading if reached' },
  { key: 'max_open_positions', label: 'Max Open Positions', suffix: '', description: 'Maximum concurrent trades' },
  { key: 'default_stop_loss_pct', label: 'Default Stop Loss', suffix: '%', description: 'Default stop-loss distance from entry' },
  { key: 'default_take_profit_pct', label: 'Default Take Profit', suffix: '%', description: 'Default take-profit distance from entry' },
  { key: 'min_risk_reward_ratio', label: 'Min Risk/Reward Ratio', suffix: ':1', description: 'Minimum reward relative to risk' },
  { key: 'max_correlated_positions', label: 'Max Correlated Positions', suffix: '', description: 'Limit on positions in correlated assets' },
  { key: 'drawdown_threshold_pct', label: 'Drawdown Threshold', suffix: '%', description: 'When drawdown exceeds this, reduce positions' },
  { key: 'drawdown_reduction_pct', label: 'Drawdown Position Reduction', suffix: '%', description: 'Reduce position sizes by this % during drawdown' },
];

export default function RiskSettings() {
  const [config, setConfig] = useState<RiskConfig>(defaultConfig);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get<RiskConfig>('/risk/config').then(({ data }) => {
      setConfig({ ...defaultConfig, ...data });
    });
  }, []);

  async function handleSave() {
    setSaving(true);
    try {
      await api.put('/risk/config', config);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  }

  function updateField(key: keyof RiskConfig, value: string) {
    const num = parseFloat(value);
    if (!isNaN(num)) {
      setConfig((prev) => ({ ...prev, [key]: num }));
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Risk Management</h2>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm
            flex items-center gap-2 disabled:opacity-50"
        >
          <Save size={14} />
          {saving ? 'Saving...' : saved ? 'Saved!' : 'Save'}
        </button>
      </div>

      <div className="bg-gray-900 rounded-xl border border-gray-800 divide-y divide-gray-800">
        {fields.map(({ key, label, suffix, description }) => (
          <div key={key} className="p-4 flex items-center justify-between">
            <div>
              <p className="text-white text-sm font-medium">{label}</p>
              <p className="text-xs text-gray-500">{description}</p>
            </div>
            <div className="flex items-center gap-1">
              <input
                type="number"
                step={key === 'max_open_positions' || key === 'max_correlated_positions' ? 1 : 0.5}
                value={config[key] ?? ''}
                onChange={(e) => updateField(key, e.target.value)}
                className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm
                  text-white text-right font-mono focus:outline-none focus:border-green-500"
              />
              {suffix && <span className="text-gray-500 text-sm">{suffix}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
