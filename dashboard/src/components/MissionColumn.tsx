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
  emptyText = 'No issues',
}: MissionColumnProps) {
  return (
    <div className="flex flex-col h-full min-w-0">
      {/* Column Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-app-border bg-white">
        {icon}
        <span className={`text-sm font-semibold ${accentColor}`}>
          {title}
        </span>
        <span className="ml-auto text-xs font-medium text-app-text-muted bg-app-panel px-2 py-0.5 rounded-full">
          {missions.length}
        </span>
      </div>

      {/* Scrollable list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {missions.length === 0 ? (
          <div className="text-center py-8 text-sm text-app-text-muted">
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
