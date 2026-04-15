import { useMemo } from 'react';
import { BarChart3, X, Clock, TrendingDown, AlertTriangle } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, CartesianGrid,
} from 'recharts';
import type { Investigation } from '../types/investigation';

interface MetricsPanelProps {
  investigations: Investigation[];
  onClose: () => void;
}

const COLORS = {
  autoFix: '#059669',
  needsReview: '#d97706',
  escalate: '#dc2626',
  primary: '#4f46e5',
  info: '#0284c7',
  ageFresh: '#059669',
  ageModerate: '#d97706',
  ageStale: '#dc2626',
};

export function MetricsPanel({ investigations, onClose }: MetricsPanelProps) {
  // Issues resolved over time (group by day)
  const resolvedOverTime = useMemo(() => {
    const resolved = investigations.filter(m =>
      ['RESOLVED', 'ROUTED', 'CLOSED'].includes(m.status) && m.completed_at
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
  }, [investigations]);

  // Average investigation time
  const avgInvestigationTime = useMemo(() => {
    const withTime = investigations.filter(m => m.elapsed_seconds && m.elapsed_seconds > 0);
    if (withTime.length === 0) return 0;
    const total = withTime.reduce((sum, m) => sum + (m.elapsed_seconds || 0), 0);
    return Math.round(total / withTime.length);
  }, [investigations]);

  // Classification distribution (pie chart)
  const classificationDist = useMemo(() => {
    const counts = { AUTO_FIX: 0, NEEDS_REVIEW: 0, ESCALATE: 0 };
    investigations.forEach(m => {
      if (m.classification && m.classification in counts) {
        counts[m.classification as keyof typeof counts]++;
      }
    });
    return [
      { name: 'Auto-fix', value: counts.AUTO_FIX, color: COLORS.autoFix },
      { name: 'Needs Review', value: counts.NEEDS_REVIEW, color: COLORS.needsReview },
      { name: 'Escalate', value: counts.ESCALATE, color: COLORS.escalate },
    ].filter(d => d.value > 0);
  }, [investigations]);

  // Module-level issue distribution
  const moduleDistribution = useMemo(() => {
    const modules: Record<string, number> = {};
    investigations.forEach(m => {
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
  }, [investigations]);

  // Backlog trajectory (cumulative issues in vs out)
  const backlogTrajectory = useMemo(() => {
    const allSorted = [...investigations].sort((a, b) => a.created_at - b.created_at);
    let opened = 0;
    let resolved = 0;
    const points: { label: string; backlog: number }[] = [];
    allSorted.forEach((m, i) => {
      opened++;
      if (['RESOLVED', 'ROUTED', 'CLOSED'].includes(m.status)) {
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
  }, [investigations]);

  // Median time to resolution (seconds)
  const medianResolutionTime = useMemo(() => {
    const resolved = investigations.filter(
      m => ['RESOLVED', 'ROUTED', 'CLOSED'].includes(m.status) && m.completed_at && m.created_at
    );
    if (resolved.length === 0) return 0;
    const durations = resolved
      .map(m => (m.completed_at! - m.created_at))
      .sort((a, b) => a - b);
    const mid = Math.floor(durations.length / 2);
    return durations.length % 2 === 0
      ? (durations[mid - 1] + durations[mid]) / 2
      : durations[mid];
  }, [investigations]);

  // Resolution rate (resolved / total)
  const resolutionRate = useMemo(() => {
    if (investigations.length === 0) return 0;
    const resolved = investigations.filter(
      m => ['RESOLVED', 'ROUTED', 'CLOSED'].includes(m.status)
    ).length;
    return Math.round((resolved / investigations.length) * 100);
  }, [investigations]);

  // Oldest open issue age (in hours)
  const oldestOpenAge = useMemo(() => {
    const now = Date.now() / 1000;
    const open = investigations.filter(
      m => !['RESOLVED', 'ROUTED', 'CLOSED'].includes(m.status)
    );
    if (open.length === 0) return null;
    const oldest = open.reduce((prev, curr) =>
      curr.created_at < prev.created_at ? curr : prev
    );
    return {
      hours: Math.round((now - oldest.created_at) / 3600),
      issueNumber: oldest.issue_number,
    };
  }, [investigations]);

  // Issue age distribution (open issues grouped by age bucket)
  const issueAgeDistribution = useMemo(() => {
    const now = Date.now() / 1000;
    const open = investigations.filter(
      m => !['RESOLVED', 'ROUTED', 'CLOSED'].includes(m.status)
    );
    const buckets = [
      { label: '< 1h', min: 0, max: 3600, count: 0, color: COLORS.ageFresh },
      { label: '1-6h', min: 3600, max: 21600, count: 0, color: COLORS.ageFresh },
      { label: '6-24h', min: 21600, max: 86400, count: 0, color: COLORS.ageModerate },
      { label: '1-3d', min: 86400, max: 259200, count: 0, color: COLORS.ageModerate },
      { label: '3-7d', min: 259200, max: 604800, count: 0, color: COLORS.ageStale },
      { label: '> 7d', min: 604800, max: Infinity, count: 0, color: COLORS.ageStale },
    ];
    open.forEach(m => {
      const age = now - m.created_at;
      const bucket = buckets.find(b => age >= b.min && age < b.max);
      if (bucket) bucket.count++;
    });
    return buckets;
  }, [investigations]);

  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) {
      const m = Math.floor(seconds / 60);
      const s = Math.floor(seconds % 60);
      return `${m}m ${s}s`;
    }
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
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

        {/* Summary stats — row 1 */}
        <div className="grid grid-cols-4 gap-4 px-6 pt-4 pb-2">
          <StatCard label="Total Issues" value={investigations.length} />
          <StatCard
            label="Resolved"
            value={investigations.filter(m => ['RESOLVED', 'ROUTED', 'CLOSED'].includes(m.status)).length}
          />
          <StatCard label="Avg Investigation" value={formatTime(avgInvestigationTime)} />
          <StatCard
            label="Auto-fix Rate"
            value={
              investigations.length > 0
                ? `${Math.round((investigations.filter(m => m.classification === 'AUTO_FIX').length / investigations.length) * 100)}%`
                : '0%'
            }
          />
        </div>
        {/* Summary stats — row 2 */}
        <div className="grid grid-cols-4 gap-4 px-6 pb-4 pt-2 border-b border-app-border">
          <StatCard
            label="Median Resolution"
            value={medianResolutionTime > 0 ? formatTime(medianResolutionTime) : '—'}
            icon={<Clock className="w-3.5 h-3.5 text-app-primary" />}
          />
          <StatCard
            label="Resolution Rate"
            value={`${resolutionRate}%`}
            icon={<TrendingDown className="w-3.5 h-3.5 text-app-success" />}
          />
          <StatCard
            label="Open Issues"
            value={investigations.filter(m => !['RESOLVED', 'ROUTED', 'CLOSED'].includes(m.status)).length}
          />
          <StatCard
            label="Oldest Open"
            value={oldestOpenAge ? `${oldestOpenAge.hours}h (#${oldestOpenAge.issueNumber})` : '—'}
            icon={<AlertTriangle className="w-3.5 h-3.5 text-app-warning" />}
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
                  <Bar dataKey="count" fill={COLORS.autoFix} radius={[4, 4, 0, 0]} />
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

          {/* Issue age distribution */}
          <ChartCard title="Open Issue Age Distribution">
            {issueAgeDistribution.some(b => b.count > 0) ? (
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={issueAgeDistribution}>
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {issueAgeDistribution.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
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

function StatCard({ label, value, icon }: { label: string; value: string | number; icon?: React.ReactNode }) {
  return (
    <div className="text-center p-3 rounded-lg bg-app-panel border border-app-border">
      <div className="text-xs font-medium text-app-text-muted flex items-center justify-center gap-1">
        {icon}
        {label}
      </div>
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
