import { useMemo, useState, useEffect } from 'react';
import { Inbox, Search, CheckCircle2, RotateCcw, Eye } from 'lucide-react';
import { useIssueTriage } from './hooks/useIssueTriage';
import { HeaderBar } from './components/HeaderBar';
import { InvestigationColumn } from './components/InvestigationColumn';
import { MetricsPanel } from './components/MetricsPanel';
import type { Investigation } from './types/investigation';

function App() {
  const {
    investigations,
    stats,
    uptimeStart,
    telemetryLog,
    connected,
    launchFix,
    approveInvestigation,
    resetInvestigations,
  } = useIssueTriage();

  // Log telemetry to browser console instead of showing in UI
  useEffect(() => {
    if (telemetryLog.length > 0) {
      const latest = telemetryLog[telemetryLog.length - 1];
      console.log(`[triage] ${latest.investigation_id}: ${latest.text}`);
    }
  }, [telemetryLog]);

  const [showMetrics, setShowMetrics] = useState(false);
  const investigationList = useMemo(() => Object.values(investigations), [investigations]);

  // Sort newest-first (highest created_at first) for all columns
  const sortNewestFirst = (a: Investigation, b: Investigation) => (b.created_at ?? 0) - (a.created_at ?? 0);

  const queued = useMemo(
    () => investigationList.filter((inv: Investigation) => inv.status === 'QUEUED').sort(sortNewestFirst),
    [investigationList]
  );

  const active = useMemo(
    () => investigationList.filter((inv: Investigation) =>
      ['INVESTIGATING', 'INVESTIGATION_COMPLETE', 'LAUNCHING', 'FIX_IN_PROGRESS'].includes(inv.status)
    ).sort(sortNewestFirst),
    [investigationList]
  );

  const pendingReview = useMemo(
    () => investigationList.filter((inv: Investigation) => inv.status === 'PENDING_REVIEW').sort(sortNewestFirst),
    [investigationList]
  );

  const completed = useMemo(
    () => investigationList.filter((inv: Investigation) =>
      ['RESOLVED', 'ROUTED', 'CLOSED', 'FAILED'].includes(inv.status)
    ).sort(sortNewestFirst),
    [investigationList]
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
              Auto-fix <span className="font-semibold">{stats.auto_fix_count}</span>
            </span>
            <span className="flex items-center gap-1.5 text-app-warning">
              <span className="w-2 h-2 rounded-full bg-app-warning" />
              Needs Review <span className="font-semibold">{stats.needs_review_count}</span>
            </span>
            <span className="flex items-center gap-1.5 text-app-danger">
              <span className="w-2 h-2 rounded-full bg-app-danger" />
              Escalate <span className="font-semibold">{stats.escalate_count}</span>
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
          <button
            onClick={() => { if (window.confirm('Clear all investigations and reset the dashboard?')) resetInvestigations(); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-app-border
              bg-white hover:bg-red-50 text-xs font-medium text-app-text-secondary
              hover:text-red-600 transition-all shadow-sm"
            title="Reset dashboard — clear all investigations"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset
          </button>
        </div>
      </div>

      {/* Four-column layout */}
      <div className="flex-1 grid grid-cols-4 divide-x divide-app-border min-h-0">
        {/* Queue */}
        <InvestigationColumn
          title="Queue"
          investigations={queued}
          icon={<Inbox className="w-4 h-4 text-app-primary" />}
          accentColor="text-app-text-secondary"
          compact
          emptyText="No issues queued"
        />

        {/* In Progress */}
        <InvestigationColumn
          title="In Progress"
          investigations={active}
          icon={<Search className="w-4 h-4 text-app-warning" />}
          accentColor="text-app-text-secondary"
          onLaunch={launchFix}
          emptyText="No active investigations"
        />

        {/* Pending Review */}
        <InvestigationColumn
          title="Pending Review"
          investigations={pendingReview}
          icon={<Eye className="w-4 h-4 text-purple-500" />}
          accentColor="text-app-text-secondary"
          onApprove={approveInvestigation}
          emptyText="No items pending review"
        />

        {/* Resolved */}
        <InvestigationColumn
          title="Resolved"
          investigations={completed}
          icon={<CheckCircle2 className="w-4 h-4 text-app-success" />}
          accentColor="text-app-text-secondary"
          compact
          emptyText="No resolved issues"
        />
      </div>

      {/* Metrics Modal */}
      {showMetrics && (
        <MetricsPanel investigations={investigationList} onClose={() => setShowMetrics(false)} />
      )}
    </div>
  );
}

export default App
