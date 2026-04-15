import { useMemo } from 'react';
import { BarChart3, X } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, CartesianGrid,
} from 'recharts';
import type { Mission } from '../types/mission';

interface MetricsPanelProps {
  missions: Mission[];
  onClose: () => void;
}

const COLORS = {
  strike: '#059669',
  assist: '#d97706',
  command: '#dc2626',
  primary: '#4f46e5',
};

export function MetricsPanel({ missions, onClose }: MetricsPanelProps) {
  // Issues resolved over time (group by day)
  const resolvedOverTime = useMemo(() => {
    const resolved = missions.filter(m =>
      ['MISSION_COMPLETE', 'ROUTED', 'CLOSED'].includes(m.status) && m.completed_at
    );
    const dayMap: Record<string, number> = {};
    resolved.forEach(m => {
      const d = new Date((m.completed_at || 0) * 1000);
      const key = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      dayMap[key] = (dayMap[key] || 0) + 1;
    });
    return Object.entries(dayMap)
      .map(([date, count]) => ({ date, count }))
      .sort((a, b) => new Date(a.date + ' 2026').getTime() - new Date(b.date + ' 2026').getTime());
  }, [missions]);

  // Average investigation time
  const avgInvestigationTime = useMemo(() => {
    const withTime = missions.filter(m => m.elapsed_seconds && m.elapsed_seconds > 0);
    if (withTime.length === 0) return 0;
    const total = withTime.reduce((sum, m) => sum + (m.elapsed_seconds || 0), 0);
    return Math.round(total / withTime.length);
  }, [missions]);

  // Classification distribution (pie chart)
  const classificationDist = useMemo(() => {
    const counts = { STRIKE: 0, ASSIST: 0, COMMAND: 0 };
    missions.forEach(m => {
      if (m.classification && m.classification in counts) {
        counts[m.classification as keyof typeof counts]++;
      }
    });
    return [
      { name: 'Auto-fix', value: counts.STRIKE, color: COLORS.strike },
      { name: 'Needs Review', value: counts.ASSIST, color: COLORS.assist },
      { name: 'Escalate', value: counts.COMMAND, color: COLORS.command },
    ].filter(d => d.value > 0);
  }, [missions]);

  // Module-level issue distribution
  const moduleDistribution = useMemo(() => {
    const modules: Record<string, number> = {};
    missions.forEach(m => {
      const report = m.investigation_report;
      if (report?.relevant_files) {
        report.relevant_files.forEach(f => {
          const match = f.match(/src\/modules\/(\w+)\//);
          if (match) {
            const mod = match[1];
            modules[mod] = (modules[mod] || 0) + 1;
          }
        });
      }
    });
    return Object.entries(modules)
      .map(([module, count]) => ({ module, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8);
  }, [missions]);

  // Backlog trajectory (cumulative issues in vs out)
  const backlogTrajectory = useMemo(() => {
    const allSorted = [...missions].sort((a, b) => a.created_at - b.created_at);
    let opened = 0;
    let resolved = 0;
    const points: { label: string; backlog: number }[] = [];
    allSorted.forEach((m, i) => {
      opened++;
      if (['MISSION_COMPLETE', 'ROUTED', 'CLOSED'].includes(m.status)) {
        resolved++;
      }
      if (i % Math.max(1, Math.floor(allSorted.length / 10)) === 0 || i === allSorted.length - 1) {
        points.push({
          label: `#${m.issue_number}`,
          backlog: opened - resolved,
        });
      }
    });
    return points;
  }, [missions]);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}m ${s}s`;
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-6" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl border border-app-border w-full max-w-4xl max-h-[85vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-app-border">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-app-primary" />
            <h2 className="text-lg font-semibold text-app-text">Metrics</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-app-text-muted hover:text-app-text hover:bg-app-panel transition-all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Summary stats */}
        <div className="grid grid-cols-4 gap-4 px-6 py-4 border-b border-app-border">
          <StatCard label="Total Issues" value={missions.length} />
          <StatCard
            label="Resolved"
            value={missions.filter(m => ['MISSION_COMPLETE', 'ROUTED', 'CLOSED'].includes(m.status)).length}
          />
          <StatCard label="Avg Investigation" value={formatTime(avgInvestigationTime)} />
          <StatCard
            label="Auto-fix Rate"
            value={
              missions.length > 0
                ? `${Math.round((missions.filter(m => m.classification === 'STRIKE').length / missions.length) * 100)}%`
                : '0%'
            }
          />
        </div>

        {/* Charts grid */}
        <div className="grid grid-cols-2 gap-6 p-6">
          {/* Classification distribution */}
          <ChartCard title="Classification Distribution">
            {classificationDist.length > 0 ? (
              <div className="flex items-center gap-4">
                <ResponsiveContainer width="50%" height={160}>
                  <PieChart>
                    <Pie
                      data={classificationDist}
                      dataKey="value"
                      cx="50%"
                      cy="50%"
                      outerRadius={60}
                      innerRadius={35}
                    >
                      {classificationDist.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-2">
                  {classificationDist.map(d => (
                    <div key={d.name} className="flex items-center gap-2 text-xs">
                      <span className="w-3 h-3 rounded-full" style={{ backgroundColor: d.color }} />
                      <span className="text-app-text-secondary">{d.name}</span>
                      <span className="font-semibold text-app-text">{d.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyChart />
            )}
          </ChartCard>

          {/* Module distribution */}
          <ChartCard title="Issues by Module">
            {moduleDistribution.length > 0 ? (
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={moduleDistribution} layout="vertical">
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="module" type="category" tick={{ fontSize: 11 }} width={90} />
                  <Tooltip />
                  <Bar dataKey="count" fill={COLORS.primary} radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart />
            )}
          </ChartCard>

          {/* Issues resolved over time */}
          <ChartCard title="Issues Resolved Over Time">
            {resolvedOverTime.length > 0 ? (
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={resolvedOverTime}>
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill={COLORS.strike} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart />
            )}
          </ChartCard>

          {/* Backlog trajectory */}
          <ChartCard title="Backlog Trajectory">
            {backlogTrajectory.length > 0 ? (
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={backlogTrajectory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="backlog"
                    stroke={COLORS.primary}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart />
            )}
          </ChartCard>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="text-center p-3 rounded-lg bg-app-panel border border-app-border">
      <div className="text-xs font-medium text-app-text-muted">{label}</div>
      <div className="text-xl font-semibold text-app-text mt-1">{value}</div>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-app-border rounded-lg p-4">
      <h3 className="text-sm font-semibold text-app-text mb-3">{title}</h3>
      {children}
    </div>
  );
}

function EmptyChart() {
  return (
    <div className="h-40 flex items-center justify-center text-sm text-app-text-muted">
      No data yet
    </div>
  );
}
