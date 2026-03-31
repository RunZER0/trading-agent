import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';

interface Props {
  data: Array<{ timestamp: string; equity: number }>;
  title?: string;
}

export default function PnLChart({ data, title = 'Equity Curve' }: Props) {
  if (!data.length) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-600">
        No data available
      </div>
    );
  }

  const startEquity = data[0]?.equity ?? 0;
  const endEquity = data[data.length - 1]?.equity ?? 0;
  const isPositive = endEquity >= startEquity;

  return (
    <div>
      {title && (
        <h3 className="text-sm font-medium text-gray-400 mb-2">{title}</h3>
      )}
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="timestamp"
            tick={{ fontSize: 10, fill: '#6b7280' }}
            tickFormatter={(v) => {
              const d = new Date(v);
              return `${d.getMonth() + 1}/${d.getDate()}`;
            }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: '#6b7280' }}
            tickFormatter={(v) => `$${v.toLocaleString()}`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1f2937',
              border: '1px solid #374151',
              borderRadius: '8px',
              fontSize: '12px',
            }}
            labelFormatter={(l) => new Date(l).toLocaleDateString()}
            formatter={(value: number) => [`$${value.toFixed(2)}`, 'Equity']}
          />
          <Line
            type="monotone"
            dataKey="equity"
            stroke={isPositive ? '#22c55e' : '#ef4444'}
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
