import { useEffect, useRef } from 'react';
import { List } from 'lucide-react';
import type { TelemetryLogEntry } from '../types/investigation';

interface TelemetryStripProps {
  entries: TelemetryLogEntry[];
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function TelemetryStrip({ entries }: TelemetryStripProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries]);

  return (
    <div className="border-t border-app-border bg-white">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-app-border">
        <List className="w-3.5 h-3.5 text-app-text-muted" />
        <span className="text-xs font-medium text-app-text-secondary">Activity Log</span>
        <span className="text-xs text-app-text-muted">{entries.length} events</span>
      </div>
      <div ref={scrollRef} className="h-28 overflow-y-auto px-4 py-1 font-mono text-xs">
        {entries.length === 0 ? (
          <div className="text-app-text-muted py-2">Waiting for activity...</div>
        ) : (
          entries.map((entry, i) => (
            <div key={i} className="flex gap-3 py-0.5 hover:bg-app-panel/50 rounded">
              <span className="text-app-text-muted flex-shrink-0">{formatTime(entry.timestamp)}</span>
              <span className="text-app-primary flex-shrink-0 w-24 truncate font-medium">{entry.investigation_id}</span>
              <span className="text-app-text-secondary truncate">{entry.text}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
