import { useEffect, useState } from 'react';
import { Activity, Radio, Wifi, WifiOff, TrendingDown, TrendingUp } from 'lucide-react';

interface HeaderBarProps {
  active: number;
  completed: number;
  queued: number;
  total: number;
  uptimeStart: number;
  connected: boolean;
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function HeaderBar({ active, completed, queued, total, uptimeStart, connected }: HeaderBarProps) {
  const [uptime, setUptime] = useState('00:00:00');

  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = Date.now() / 1000 - uptimeStart;
      setUptime(formatUptime(elapsed));
    }, 1000);
    return () => clearInterval(interval);
  }, [uptimeStart]);

  const backlogTrend = queued > active ? 'growing' : queued < completed ? 'shrinking' : 'stable';

  return (
    <header className="border-b border-nasa-border bg-nasa-dark/80 backdrop-blur-sm px-6 py-3">
      <div className="flex items-center justify-between">
        {/* Left: Title & Status */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Radio className="w-5 h-5 text-nasa-cyan animate-pulse" />
            <h1 className="text-xl font-bold tracking-wider text-nasa-text font-sans">
              MISSION CONTROL
            </h1>
          </div>
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded border border-nasa-border bg-nasa-navy">
            {connected ? (
              <Wifi className="w-3.5 h-3.5 text-nasa-green" />
            ) : (
              <WifiOff className="w-3.5 h-3.5 text-nasa-red" />
            )}
            <span className={`text-xs font-mono ${connected ? 'text-nasa-green' : 'text-nasa-red'}`}>
              {connected ? 'CONNECTED' : 'DISCONNECTED'}
            </span>
          </div>
        </div>

        {/* Center: Mission Clock */}
        <div className="flex items-center gap-6">
          <div className="text-center">
            <div className="text-xs text-nasa-muted font-sans uppercase tracking-wider">Mission Clock</div>
            <div className="text-2xl font-mono text-nasa-cyan tracking-widest">{uptime}</div>
          </div>
        </div>

        {/* Right: Stats */}
        <div className="flex items-center gap-6">
          <StatBadge label="QUEUED" value={queued} color="text-nasa-cyan" />
          <StatBadge label="ACTIVE" value={active} color="text-nasa-amber" />
          <StatBadge label="COMPLETE" value={completed} color="text-nasa-green" />
          <div className="flex items-center gap-1.5 px-3 py-1 rounded border border-nasa-border bg-nasa-navy">
            <Activity className="w-3.5 h-3.5 text-nasa-muted" />
            <span className="text-xs font-sans text-nasa-muted uppercase">Backlog</span>
            <span className="text-sm font-mono text-nasa-text font-bold">{total}</span>
            {backlogTrend === 'shrinking' ? (
              <TrendingDown className="w-3.5 h-3.5 text-nasa-green" />
            ) : backlogTrend === 'growing' ? (
              <TrendingUp className="w-3.5 h-3.5 text-nasa-red" />
            ) : null}
          </div>
        </div>
      </div>
    </header>
  );
}

function StatBadge({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="text-center">
      <div className="text-xs text-nasa-muted font-sans uppercase tracking-wider">{label}</div>
      <div className={`text-lg font-mono font-bold ${color}`}>{value}</div>
    </div>
  );
}
