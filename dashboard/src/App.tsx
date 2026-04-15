import { useMemo, useState } from 'react';
import { Inbox, Search, CheckCircle2 } from 'lucide-react';
import { useMissionControl } from './hooks/useMissionControl';
import { HeaderBar } from './components/HeaderBar';
import { MissionColumn } from './components/MissionColumn';
import { TelemetryStrip } from './components/TelemetryStrip';
import { FileMissionInput } from './components/FileMissionInput';
import { MetricsPanel } from './components/MetricsPanel';
import type { Mission } from './types/mission';

function App() {
  const {
    missions,
    stats,
    uptimeStart,
    telemetryLog,
    connected,
    launchFix,
    fileMission,
  } = useMissionControl();

  const [showMetrics, setShowMetrics] = useState(false);
  const missionList = useMemo(() => Object.values(missions), [missions]);

  const queued = useMemo(
    () => missionList.filter((m: Mission) => m.status === 'QUEUED'),
    [missionList]
  );

  const active = useMemo(
    () => missionList.filter((m: Mission) =>
      ['INVESTIGATING', 'INVESTIGATION_COMPLETE', 'LAUNCHING', 'FIX_IN_PROGRESS'].includes(m.status)
    ),
    [missionList]
  );

  const completed = useMemo(
    () => missionList.filter((m: Mission) =>
      ['MISSION_COMPLETE', 'ROUTED', 'CLOSED', 'FAILED'].includes(m.status)
    ),
    [missionList]
  );

  return (
    <div className="h-screen flex flex-col bg-app-bg text-app-text overflow-hidden">
      {/* Header */}
      <HeaderBar
        active={stats.active}
        completed={stats.completed}
        queued={stats.queued}
        total={stats.total}
        resolvedToday={stats.resolved_today}
        uptimeStart={uptimeStart}
        connected={connected}
      />

      {/* Classification summary & actions bar */}
      <div className="flex items-center justify-between px-6 py-2 border-b border-app-border bg-white">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3 text-xs font-medium">
            <span className="flex items-center gap-1.5 text-app-success">
              <span className="w-2 h-2 rounded-full bg-app-success" />
              Auto-fix <span className="font-semibold">{stats.strike_count}</span>
            </span>
            <span className="flex items-center gap-1.5 text-app-warning">
              <span className="w-2 h-2 rounded-full bg-app-warning" />
              Needs Review <span className="font-semibold">{stats.assist_count}</span>
            </span>
            <span className="flex items-center gap-1.5 text-app-danger">
              <span className="w-2 h-2 rounded-full bg-app-danger" />
              Escalate <span className="font-semibold">{stats.command_count}</span>
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowMetrics(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-app-border
              bg-white hover:bg-app-panel text-xs font-medium text-app-text-secondary
              hover:text-app-text transition-all shadow-sm"
          >
            Metrics
          </button>
          <FileMissionInput onFile={fileMission} />
        </div>
      </div>

      {/* Three-column layout */}
      <div className="flex-1 grid grid-cols-4 divide-x divide-app-border min-h-0">
        {/* Left: Queue */}
        <MissionColumn
          title="Queue"
          missions={queued}
          icon={<Inbox className="w-4 h-4 text-app-primary" />}
          accentColor="text-app-text-secondary"
          compact
          emptyText="No issues queued"
        />

        {/* Center: In Progress (wider) */}
        <div className="col-span-2">
          <MissionColumn
            title="In Progress"
            missions={active}
            icon={<Search className="w-4 h-4 text-app-warning" />}
            accentColor="text-app-text-secondary"
            onLaunch={launchFix}
            emptyText="No active investigations"
          />
        </div>

        {/* Right: Resolved */}
        <MissionColumn
          title="Resolved"
          missions={completed}
          icon={<CheckCircle2 className="w-4 h-4 text-app-success" />}
          accentColor="text-app-text-secondary"
          compact
          emptyText="No resolved issues"
        />
      </div>

      {/* Activity Log */}
      <TelemetryStrip entries={telemetryLog} />

      {/* Metrics Modal */}
      {showMetrics && (
        <MetricsPanel missions={missionList} onClose={() => setShowMetrics(false)} />
      )}
    </div>
  );
}

export default App
