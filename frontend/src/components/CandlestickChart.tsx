import { useEffect, useRef } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
  type IChartApi,
  type CandlestickData,
  type Time,
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
}

export default function CandlestickChart({
  bars,
  trades = [],
  height = 400,
  title,
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

    // Candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });

    const candleData: CandlestickData[] = bars
      .map((b) => {
        const t = b.timestamp.slice(0, 10); // "YYYY-MM-DD"
        return {
          time: t as Time,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        };
      })
      .sort((a, b) => (a.time < b.time ? -1 : 1));

    candleSeries.setData(candleData);

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
      bars
        .map((b) => ({
          time: b.timestamp.slice(0, 10) as Time,
          value: b.volume,
          color: b.close >= b.open ? '#166534' : '#7f1d1d',
        }))
        .sort((a, b) => (a.time < b.time ? -1 : 1))
    );

    // Trade markers
    if (trades.length > 0) {
      const markers = trades
        .map((t) => ({
          time: t.timestamp.slice(0, 10) as Time,
          position: t.direction === 'BUY' ? ('belowBar' as const) : ('aboveBar' as const),
          color: t.direction === 'BUY' ? '#22c55e' : '#ef4444',
          shape: t.direction === 'BUY' ? ('arrowUp' as const) : ('arrowDown' as const),
          text: t.label || t.direction,
          size: 1,
        }))
        .sort((a, b) => (a.time < b.time ? -1 : 1));
      createSeriesMarkers(candleSeries, markers);
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
  }, [bars, trades, height]);

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
