import { Play, CheckCircle2, Clock, AlertTriangle, XCircle, Circle, Loader2, ExternalLink } from 'lucide-react';
import type { Mission, MissionClassification, TelemetryStep } from '../types/mission';

interface MissionCardProps {
  mission: Mission;
  onLaunch?: (missionId: string) => void;
  compact?: boolean;
}

function classificationBadge(c: MissionClassification | null) {
  if (!c) return null;
  const config: Record<string, { label: string; style: string }> = {
    STRIKE: { label: 'Auto-fix', style: 'bg-app-success-light text-app-success' },
    ASSIST: { label: 'Needs Review', style: 'bg-app-warning-light text-app-warning' },
    COMMAND: { label: 'Escalate', style: 'bg-app-danger-light text-app-danger' },
  };
  const { label, style } = config[c] || { label: c, style: 'bg-app-panel text-app-text-muted' };
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${style}`}>
      {label}
    </span>
  );
}

function statusDot(status: string) {
  switch (status) {
    case 'QUEUED':
      return <Circle className="w-3 h-3 text-app-primary animate-pulse-soft fill-app-primary/20" />;
    case 'INVESTIGATING':
    case 'FIX_IN_PROGRESS':
    case 'LAUNCHING':
      return <Loader2 className="w-3 h-3 text-app-warning animate-spin" />;
    case 'INVESTIGATION_COMPLETE':
      return <CheckCircle2 className="w-3 h-3 text-app-warning" />;
    case 'MISSION_COMPLETE':
      return <CheckCircle2 className="w-3 h-3 text-app-success" />;
    case 'ROUTED':
    case 'CLOSED':
      return <CheckCircle2 className="w-3 h-3 text-app-text-muted" />;
    case 'FAILED':
      return <XCircle className="w-3 h-3 text-app-danger" />;
    default:
      return <Circle className="w-3 h-3 text-app-text-muted" />;
  }
}

function StepIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="w-4 h-4 text-app-success flex-shrink-0" />;
    case 'in_progress':
      return <Loader2 className="w-4 h-4 text-app-warning animate-spin flex-shrink-0" />;
    case 'failed':
      return <XCircle className="w-4 h-4 text-app-danger flex-shrink-0" />;
    default:
      return <Circle className="w-4 h-4 text-app-text-muted/40 flex-shrink-0" />;
  }
}

function InvestigationTimeline({ steps }: { steps: TelemetryStep[] }) {
  return (
    <div className="space-y-1 mt-3">
      {steps.map((step) => (
        <div key={step.id} className="flex items-center gap-2">
          <StepIcon status={step.status} />
          <span className={`text-xs ${
            step.status === 'completed' ? 'text-app-success' :
            step.status === 'in_progress' ? 'text-app-warning font-medium' :
            'text-app-text-muted'
          }`}>
            {step.label}
          </span>
          {step.status === 'in_progress' && (
            <span className="text-xs text-app-warning/70">in progress...</span>
          )}
        </div>
      ))}
    </div>
  );
}

function ElapsedTimer({ startedAt, completedAt }: { startedAt: number | null; completedAt: number | null }) {
  if (!startedAt) return null;
  const elapsed = (completedAt || Date.now() / 1000) - startedAt;
  const m = Math.floor(elapsed / 60);
  const s = Math.floor(elapsed % 60);
  return (
    <div className="flex items-center gap-1 text-xs text-app-text-muted">
      <Clock className="w-3 h-3" />
      {String(m).padStart(2, '0')}:{String(s).padStart(2, '0')}
    </div>
  );
}

export function MissionCard({ mission, onLaunch, compact }: MissionCardProps) {
  const isActive = ['INVESTIGATING', 'FIX_IN_PROGRESS', 'LAUNCHING'].includes(mission.status);
  const isStrikeReady = mission.status === 'INVESTIGATION_COMPLETE' && mission.classification === 'STRIKE';

  const borderStyle = isActive ? 'border-app-primary/30 shadow-sm shadow-app-primary/5' :
    isStrikeReady ? 'border-app-success/40 shadow-sm' :
    mission.status === 'MISSION_COMPLETE' ? 'border-app-success/20' :
    mission.status === 'FAILED' ? 'border-app-danger/20' :
    'border-app-border';

  return (
    <div className={`rounded-lg border ${borderStyle} bg-white p-4 transition-all duration-300 animate-fade-in`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {statusDot(mission.status)}
          <span className="text-xs font-mono text-app-primary font-semibold">{mission.id}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {classificationBadge(mission.classification)}
          <ElapsedTimer startedAt={mission.started_at} completedAt={mission.completed_at} />
        </div>
      </div>

      {/* Title */}
      <h3 className="text-sm font-medium text-app-text mt-2 line-clamp-2">
        {mission.issue_title}
      </h3>

      {/* Issue link */}
      {mission.issue_url && (
        <a
          href={mission.issue_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-app-text-muted hover:text-app-primary mt-1 inline-block"
        >
          #{mission.issue_number}
        </a>
      )}

      {/* Investigation Timeline */}
      {!compact && mission.telemetry.length > 0 && (
        <InvestigationTimeline steps={mission.telemetry} />
      )}

      {/* Investigation Report Summary */}
      {!compact && mission.investigation_report && (
        <div className="mt-3 p-3 rounded-lg bg-app-panel border border-app-border-light">
          <div className="text-xs font-medium text-app-text-secondary mb-1">Root Cause</div>
          <p className="text-xs text-app-text-secondary line-clamp-3">
            {mission.investigation_report.root_cause}
          </p>
          {mission.investigation_report.fix_confidence > 0 && (
            <div className="flex items-center gap-2 mt-2">
              <span className="text-xs text-app-text-muted">Confidence</span>
              <div className="flex-1 h-1.5 bg-app-border rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    mission.investigation_report.fix_confidence >= 80 ? 'bg-app-success' :
                    mission.investigation_report.fix_confidence >= 50 ? 'bg-app-warning' :
                    'bg-app-danger'
                  }`}
                  style={{ width: `${mission.investigation_report.fix_confidence}%` }}
                />
              </div>
              <span className="text-xs font-medium text-app-text-secondary">
                {mission.investigation_report.fix_confidence}%
              </span>
            </div>
          )}
        </div>
      )}

      {/* Apply Fix button */}
      {isStrikeReady && onLaunch && (
        <button
          onClick={() => onLaunch(mission.id)}
          className="mt-4 w-full py-2.5 rounded-lg text-sm font-semibold
            bg-app-primary text-white
            hover:bg-app-primary-hover
            transition-all duration-200
            flex items-center justify-center gap-2 shadow-sm"
        >
          <Play className="w-4 h-4" />
          Apply Fix
        </button>
      )}

      {/* PR/Issue Link for completed missions */}
      {mission.pr_url && (
        <a
          href={mission.pr_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-app-primary hover:text-app-primary-hover"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          View Pull Request
        </a>
      )}

      {/* Error display */}
      {mission.error && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-app-danger">
          <AlertTriangle className="w-3.5 h-3.5" />
          {mission.error}
        </div>
      )}
    </div>
  );
}
