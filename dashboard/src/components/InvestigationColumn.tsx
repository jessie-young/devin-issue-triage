import type { Investigation } from '../types/investigation';
import { InvestigationCard } from './InvestigationCard';

interface InvestigationColumnProps {
  title: string;
  investigations: Investigation[];
  icon: React.ReactNode;
  accentColor: string;
  onLaunch?: (investigationId: string) => void;
  onApprove?: (investigationId: string) => void;
  onStartAll?: () => void;
  compact?: boolean;
  emptyText?: string;
}

export function InvestigationColumn({
  title,
  investigations,
  icon,
  accentColor,
  onLaunch,
  onApprove,
  onStartAll,
  compact,
  emptyText = 'No issues',
}: InvestigationColumnProps) {
  return (
    <div className="flex flex-col h-full min-w-0">
      {/* Column Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-app-border bg-white">
        {icon}
        <span className={`text-sm font-semibold ${accentColor}`}>
          {title}
        </span>
        {onStartAll && investigations.length > 0 && (
          <button
            onClick={onStartAll}
            className="ml-2 px-2.5 py-1 rounded-md text-xs font-semibold
              bg-app-primary text-white hover:bg-app-primary-hover
              transition-all duration-200 shadow-sm"
          >
            Start All
          </button>
        )}
        <span className="ml-auto text-xs font-medium text-app-text-muted bg-app-panel px-2 py-0.5 rounded-full">
          {investigations.length}
        </span>
      </div>

      {/* Scrollable list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {investigations.length === 0 ? (
          <div className="text-center py-8 text-sm text-app-text-muted">
            {emptyText}
          </div>
        ) : (
          investigations.map((m) => (
            <InvestigationCard
              key={m.id}
              investigation={m}
              onLaunch={onLaunch}
              onApprove={onApprove}
              compact={compact}
            />
          ))
        )}
      </div>
    </div>
  );
}
