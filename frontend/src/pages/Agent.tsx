import { useEffect, useState } from 'react';
import { Play, RefreshCw } from 'lucide-react';
import api from '../lib/api';
import AgentLogViewer from '../components/AgentLogViewer';
import type { AgentRun } from '../types';

export default function Agent() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<AgentRun | null>(null);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<string | null>(null);

  useEffect(() => {
    loadRuns();
  }, []);

  async function loadRuns() {
    const { data } = await api.get('/agent/runs?limit=20');
    setRuns(data.runs);
    if (data.runs.length > 0 && !selectedRun) {
      setSelectedRun(data.runs[0]);
    }
  }

  async function triggerRun() {
    setRunning(true);
    setRunResult(null);
    try {
      const { data } = await api.post('/agent/run', null, {
        params: { trigger_type: 'manual' },
      });
      setRunResult(
        `Completed: ${data.signals_generated} signals generated. ` +
        `Errors: ${data.errors?.length ?? 0}`
      );
      await loadRuns();
    } catch (err) {
      setRunResult(`Failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Agent Control</h2>
        <div className="flex gap-3">
          <button
            onClick={loadRuns}
            className="px-4 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 text-sm
              flex items-center gap-2"
          >
            <RefreshCw size={14} /> Refresh
          </button>
          <button
            onClick={triggerRun}
            disabled={running}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm
              flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play size={14} />
            {running ? 'Running...' : 'Run Agent Now'}
          </button>
        </div>
      </div>

      {runResult && (
        <div className={`rounded-lg p-4 text-sm ${
          runResult.startsWith('Completed') ? 'bg-green-500/10 text-green-400 border border-green-500/20'
            : 'bg-red-500/10 text-red-400 border border-red-500/20'
        }`}>
          {runResult}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Run history */}
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-400">Run History</h3>
          {runs.map((run) => (
            <button
              key={run.id}
              onClick={() => setSelectedRun(run)}
              className={`w-full text-left p-3 rounded-lg border text-sm transition-colors ${
                selectedRun?.id === run.id
                  ? 'bg-gray-800 border-green-500/30'
                  : 'bg-gray-900 border-gray-800 hover:bg-gray-800'
              }`}
            >
              <div className="flex justify-between items-center">
                <span className="text-white font-mono text-xs">
                  {run.id.slice(0, 8)}...
                </span>
                <span className={`text-xs ${
                  run.status === 'completed' ? 'text-green-400' :
                  run.status === 'running' ? 'text-yellow-400' : 'text-red-400'
                }`}>
                  {run.status}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {run.trigger_type} &middot; {new Date(run.started_at).toLocaleString()}
              </p>
            </button>
          ))}
        </div>

        {/* Log viewer */}
        <div className="lg:col-span-2">
          <AgentLogViewer run={selectedRun} />
        </div>
      </div>
    </div>
  );
}
