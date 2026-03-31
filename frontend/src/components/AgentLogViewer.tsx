import type { AgentRun } from '../types';

interface Props {
  run: AgentRun | null;
}

export default function AgentLogViewer({ run }: Props) {
  if (!run) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 text-center text-gray-600">
        No agent run selected
      </div>
    );
  }

  const statusColor = {
    running: 'text-yellow-400',
    completed: 'text-green-400',
    failed: 'text-red-400',
  }[run.status];

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <div className="p-4 border-b border-gray-800 flex items-center justify-between">
        <div>
          <h3 className="font-medium text-white">
            Run {run.id.slice(0, 8)}...
          </h3>
          <p className="text-xs text-gray-500">
            {run.trigger_type} &middot; {new Date(run.started_at).toLocaleString()}
          </p>
        </div>
        <span className={`text-sm font-medium ${statusColor}`}>
          {run.status.toUpperCase()}
        </span>
      </div>

      <div className="p-4 max-h-96 overflow-auto font-mono text-xs space-y-1">
        {run.logs.map((log, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-gray-600 shrink-0">
              {new Date(log.timestamp).toLocaleTimeString()}
            </span>
            <span className="text-blue-400 shrink-0">[{log.node}]</span>
            <span className="text-gray-300">{log.message}</span>
          </div>
        ))}
        {run.logs.length === 0 && (
          <p className="text-gray-600">No logs available</p>
        )}
      </div>

      {run.error_message && (
        <div className="p-4 border-t border-gray-800 bg-red-500/5">
          <p className="text-xs text-red-400">{run.error_message}</p>
        </div>
      )}
    </div>
  );
}
