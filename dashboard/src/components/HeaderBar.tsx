import { useEffect, useState } from 'react';
import { Activity, Wifi, WifiOff, TrendingDown, TrendingUp } from 'lucide-react';

interface HeaderBarProps {
  active: number;
  completed: number;
  queued: number;
  total: number;
  resolvedToday: number;
  uptimeStart: number;
  connected: boolean;
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function HeaderBar({ active, completed, queued, total, resolvedToday, uptimeStart, connected }: HeaderBarProps) {
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
    <header className="border-b border-app-border bg-white px-6 py-3">
      <div className="flex items-center justify-between">
        {/* Left: Title & Status */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-app-primary flex items-center justify-center">
              <Activity className="w-[1.125rem] h-[1.125rem] text-white" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-app-text">
                Issue Triage
              </h1>
              <p className="text-xs text-app-text-muted">Automated issue investigation</p>
            </div>
          </div>
          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
            connected
              ? 'bg-app-success-light text-app-success'
              : 'bg-app-danger-light text-app-danger'
          }`}>
            {connected ? (
              <Wifi className="w-3 h-3" />
            ) : (
              <WifiOff className="w-3 h-3" />
            )}
            {connected ? 'Connected' : 'Disconnected'}
          </div>
        </div>

        {/* Center: Uptime */}
        <div className="text-center">
          <div className="text-xs text-app-text-muted font-medium">Uptime</div>
          <div className="text-lg font-mono text-app-text-secondary tracking-wide">{uptime}</div>
        </div>

        {/* Right: Stats */}
        <div className="flex items-center gap-5">
          <StatBadge label="Queued" value={queued} dotColor="bg-app-primary" />
          <StatBadge label="In Progress" value={active} dotColor="bg-app-warning" />
          <StatBadge label="Resolved" value={completed} dotColor="bg-app-success" />
          <StatBadge label="Resolved Today" value={resolvedToday} dotColor="bg-app-success" />
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-app-panel border border-app-border">
            <span className="text-xs font-medium text-app-text-secondary">In/Out</span>
            <span className="text-sm font-semibold text-app-text">{total}/{completed}</span>
            {backlogTrend === 'shrinking' ? (
              <TrendingDown className="w-3.5 h-3.5 text-app-success" />
            ) : backlogTrend === 'growing' ? (
              <TrendingUp className="w-3.5 h-3.5 text-app-danger" />
            ) : null}
          </div>
        </div>
      </div>
    </header>
  );
}

function StatBadge({ label, value, dotColor }: { label: string; value: number; dotColor: string }) {
  return (
    <div className="text-center">
      <div className="flex items-center gap-1.5 text-xs text-app-text-muted font-medium">
        <span className={`w-2 h-2 rounded-full ${dotColor}`} />
        {label}
      </div>
      <div className="text-lg font-semibold text-app-text">{value}</div>
    </div>
  );
}
