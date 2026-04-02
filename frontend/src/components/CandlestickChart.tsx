import { useEffect, useRef } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  AreaSeries,
  HistogramSeries,
  createSeriesMarkers,
  type IChartApi,
  type CandlestickData,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';

interface OHLCVBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface TradeMarker {
  timestamp: string;
  direction: 'BUY' | 'SELL';
  price: number;
  label?: string;
}

interface CandlestickChartProps {
  bars: OHLCVBar[];
  trades?: TradeMarker[];
  height?: number;
  title?: string;
  mode?: 'candle' | 'line';
}

/** Convert ISO timestamp → lightweight-charts Time.
 *  Daily bars ("YYYY-MM-DD") use string form.
 *  Intraday bars use Unix seconds (UTCTimestamp). */
function toChartTime(ts: string): Time {
  if (ts.length > 10) {
    return Math.floor(new Date(ts).getTime() / 1000) as UTCTimestamp;
  }
  return ts.slice(0, 10) as Time;
}

export default function CandlestickChart({
  bars,
  trades = [],
  height = 400,
  title,
  mode = 'candle',
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || bars.length === 0) return;

    // Destroy previous chart instance
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#111827' },
        textColor: '#9ca3af',
        fontFamily: "'Inter', monospace",
      },
      grid: {
        vertLines: { color: '#1f2937' },
        horzLines: { color: '#1f2937' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#4b5563', width: 1, style: 3 },
        horzLine: { color: '#4b5563', width: 1, style: 3 },
      },
      rightPriceScale: { borderColor: '#374151' },
      timeScale: {
        borderColor: '#374151',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // Price series — candlestick or area/line
    const sortedBars = [...bars].sort((a, b) =>
      toChartTime(a.timestamp) < toChartTime(b.timestamp) ? -1 : 1
    );

    let priceSeries: ReturnType<typeof chart.addSeries>;

    if (mode === 'candle') {
      const cs = chart.addSeries(CandlestickSeries, {
        upColor: '#22c55e',
        downColor: '#ef4444',
        borderUpColor: '#22c55e',
        borderDownColor: '#ef4444',
        wickUpColor: '#22c55e',
        wickDownColor: '#ef4444',
      });
      cs.setData(
        sortedBars.map((b) => ({
          time: toChartTime(b.timestamp),
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        } as CandlestickData))
      );
      priceSeries = cs;
    } else {
      const as = chart.addSeries(AreaSeries, {
        lineColor: '#22c55e',
        topColor: 'rgba(34,197,94,0.25)',
        bottomColor: 'rgba(34,197,94,0.01)',
        lineWidth: 2,
      });
      as.setData(
        sortedBars.map((b) => ({
          time: toChartTime(b.timestamp),
          value: b.close,
        }))
      );
      priceSeries = as;
    }

    // Volume histogram
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#1d4ed8',
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    });
    chart.priceScale('vol').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeries.setData(
      sortedBars.map((b) => ({
        time: toChartTime(b.timestamp),
        value: b.volume,
        color: b.close >= b.open ? '#166534' : '#7f1d1d',
      }))
    );

    // Trade markers
    if (trades.length > 0) {
      const markers = trades
        .map((t) => ({
          time: toChartTime(t.timestamp),
          position: t.direction === 'BUY' ? ('belowBar' as const) : ('aboveBar' as const),
          color: t.direction === 'BUY' ? '#22c55e' : '#ef4444',
          shape: t.direction === 'BUY' ? ('arrowUp' as const) : ('arrowDown' as const),
          text: t.label || t.direction,
          size: 1,
        }))
        .sort((a, b) => (a.time < b.time ? -1 : 1));
      createSeriesMarkers(priceSeries, markers);
    }

    chart.timeScale().fitContent();

    // Responsive resize
    const observer = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [bars, trades, height, mode]);

  return (
    <div className="w-full">
      {title && (
        <p className="text-sm font-medium text-gray-400 mb-2">{title}</p>
      )}
      <div
        ref={containerRef}
        style={{ height }}
        className="w-full rounded-lg overflow-hidden"
      />
      {bars.length === 0 && (
        <div
          className="flex items-center justify-center text-gray-600 text-sm rounded-lg bg-gray-900"
          style={{ height }}
        >
          No data — load historical data first
        </div>
      )}
    </div>
  );
}
