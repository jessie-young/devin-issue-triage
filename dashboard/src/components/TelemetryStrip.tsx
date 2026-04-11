import { useEffect, useRef } from 'react';
import { Terminal } from 'lucide-react';
import type { TelemetryLogEntry } from '../types/mission';

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
    <div className="border-t border-nasa-border bg-nasa-navy/80 backdrop-blur-sm">
      <div className="flex items-center gap-2 px-4 py-1.5 border-b border-nasa-border/50">
        <Terminal className="w-3.5 h-3.5 text-nasa-cyan" />
        <span className="text-xs font-mono text-nasa-muted uppercase tracking-wider">Telemetry Feed</span>
        <span className="text-xs font-mono text-nasa-cyan/50">{entries.length} events</span>
      </div>
      <div ref={scrollRef} className="h-32 overflow-y-auto px-4 py-1 font-mono text-xs">
        {entries.length === 0 ? (
          <div className="text-nasa-muted/40 py-2">Awaiting telemetry data...</div>
        ) : (
          entries.map((entry, i) => (
            <div key={i} className="flex gap-3 py-0.5 hover:bg-nasa-panel/30">
              <span className="text-nasa-muted/60 flex-shrink-0">{formatTime(entry.timestamp)}</span>
              <span className="text-nasa-cyan/80 flex-shrink-0 w-24 truncate">{entry.mission_id}</span>
              <span className="text-nasa-text/70 truncate">{entry.text}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
