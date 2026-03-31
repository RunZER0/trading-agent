import { useState, useEffect, useCallback } from 'react';
import api from '../lib/api';
import type { TradingSignal } from '../types';

export function useSignals(filters?: { asset?: string; direction?: string }) {
  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSignals = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filters?.asset) params.set('asset', filters.asset);
      if (filters?.direction) params.set('direction', filters.direction);
      const { data } = await api.get(`/signals?${params}`);
      setSignals(data.signals);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch signals');
    } finally {
      setLoading(false);
    }
  }, [filters?.asset, filters?.direction]);

  useEffect(() => { fetchSignals(); }, [fetchSignals]);

  return { signals, loading, error, refresh: fetchSignals };
}
