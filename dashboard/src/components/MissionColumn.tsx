import type { Mission } from '../types/mission';
import { MissionCard } from './MissionCard';

interface MissionColumnProps {
  title: string;
  missions: Mission[];
  icon: React.ReactNode;
  accentColor: string;
  onLaunch?: (missionId: string) => void;
  compact?: boolean;
  emptyText?: string;
}

export function MissionColumn({
  title,
  missions,
  icon,
  accentColor,
  onLaunch,
  compact,
  emptyText = 'No missions',
}: MissionColumnProps) {
  return (
    <div className="flex flex-col h-full min-w-0">
      {/* Column Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-nasa-border/50">
        {icon}
        <span className={`text-xs font-mono font-bold uppercase tracking-wider ${accentColor}`}>
          {title}
        </span>
        <span className="ml-auto text-xs font-mono text-nasa-muted bg-nasa-navy px-2 py-0.5 rounded">
          {missions.length}
        </span>
      </div>

      {/* Scrollable mission list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {missions.length === 0 ? (
          <div className="text-center py-8 text-xs font-mono text-nasa-muted/40">
            {emptyText}
          </div>
        ) : (
          missions.map((m) => (
            <MissionCard
              key={m.id}
              mission={m}
              onLaunch={onLaunch}
              compact={compact}
            />
          ))
        )}
      </div>
    </div>
  );
}
