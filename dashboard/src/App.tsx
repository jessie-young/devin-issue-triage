import { useMemo } from 'react';
import { Inbox, Radar, CheckCircle2 } from 'lucide-react';
import { useMissionControl } from './hooks/useMissionControl';
import { HeaderBar } from './components/HeaderBar';
import { MissionColumn } from './components/MissionColumn';
import { TelemetryStrip } from './components/TelemetryStrip';
import { FileMissionInput } from './components/FileMissionInput';
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
    <div className="h-screen flex flex-col bg-nasa-navy text-nasa-text overflow-hidden">
      {/* Blueprint grid background */}
      <div className="fixed inset-0 pointer-events-none opacity-5"
        style={{
          backgroundImage: `
            linear-gradient(rgba(6, 182, 212, 0.3) 1px, transparent 1px),
            linear-gradient(90deg, rgba(6, 182, 212, 0.3) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
        }}
      />

      {/* Header */}
      <HeaderBar
        active={stats.active}
        completed={stats.completed}
        queued={stats.queued}
        total={stats.total}
        uptimeStart={uptimeStart}
        connected={connected}
      />

      {/* Manual file mission input bar */}
      <div className="flex items-center justify-between px-6 py-2 border-b border-nasa-border/30 bg-nasa-dark/40">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3 text-xs font-mono">
            <span className="text-nasa-green">
              STRIKE <span className="font-bold">{stats.strike_count}</span>
            </span>
            <span className="text-nasa-amber">
              ASSIST <span className="font-bold">{stats.assist_count}</span>
            </span>
            <span className="text-nasa-red">
              COMMAND <span className="font-bold">{stats.command_count}</span>
            </span>
          </div>
        </div>
        <FileMissionInput onFile={fileMission} />
      </div>

      {/* Three-column layout */}
      <div className="flex-1 grid grid-cols-4 divide-x divide-nasa-border/30 min-h-0 relative z-10">
        {/* Left: Mission Queue */}
        <MissionColumn
          title="Mission Queue"
          missions={queued}
          icon={<Inbox className="w-4 h-4 text-nasa-cyan" />}
          accentColor="text-nasa-cyan"
          compact
          emptyText="No missions queued"
        />

        {/* Center: Active Missions (wider) */}
        <div className="col-span-2">
          <MissionColumn
            title="Active Missions"
            missions={active}
            icon={<Radar className="w-4 h-4 text-nasa-amber" />}
            accentColor="text-nasa-amber"
            onLaunch={launchFix}
            emptyText="No active investigations"
          />
        </div>

        {/* Right: Completed Missions */}
        <MissionColumn
          title="Completed"
          missions={completed}
          icon={<CheckCircle2 className="w-4 h-4 text-nasa-green" />}
          accentColor="text-nasa-green"
          compact
          emptyText="No completed missions"
        />
      </div>

      {/* Telemetry Strip */}
      <TelemetryStrip entries={telemetryLog} />
    </div>
  );
}

export default App
