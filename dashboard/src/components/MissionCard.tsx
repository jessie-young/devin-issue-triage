import { Rocket, CheckCircle2, Clock, AlertTriangle, XCircle, Circle, Loader2 } from 'lucide-react';
import type { Mission, MissionClassification, TelemetryStep } from '../types/mission';

interface MissionCardProps {
  mission: Mission;
  onLaunch?: (missionId: string) => void;
  compact?: boolean;
}

function classificationBadge(c: MissionClassification | null) {
  if (!c) return null;
  const styles: Record<string, string> = {
    STRIKE: 'bg-nasa-green/20 text-nasa-green border-nasa-green/40',
    ASSIST: 'bg-nasa-amber/20 text-nasa-amber border-nasa-amber/40',
    COMMAND: 'bg-nasa-red/20 text-nasa-red border-nasa-red/40',
  };
  return (
    <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded border ${styles[c]}`}>
      {c}
    </span>
  );
}

function statusDot(status: string) {
  switch (status) {
    case 'QUEUED':
      return <Circle className="w-3 h-3 text-nasa-cyan animate-pulse fill-nasa-cyan/30" />;
    case 'INVESTIGATING':
    case 'FIX_IN_PROGRESS':
    case 'LAUNCHING':
      return <Loader2 className="w-3 h-3 text-nasa-amber animate-spin" />;
    case 'INVESTIGATION_COMPLETE':
      return <CheckCircle2 className="w-3 h-3 text-nasa-amber" />;
    case 'MISSION_COMPLETE':
      return <CheckCircle2 className="w-3 h-3 text-nasa-green" />;
    case 'ROUTED':
    case 'CLOSED':
      return <CheckCircle2 className="w-3 h-3 text-nasa-muted" />;
    case 'FAILED':
      return <XCircle className="w-3 h-3 text-nasa-red" />;
    default:
      return <Circle className="w-3 h-3 text-nasa-muted" />;
  }
}

function StepIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="w-4 h-4 text-nasa-green flex-shrink-0" />;
    case 'in_progress':
      return <Loader2 className="w-4 h-4 text-nasa-amber animate-spin flex-shrink-0" />;
    case 'failed':
      return <XCircle className="w-4 h-4 text-nasa-red flex-shrink-0" />;
    default:
      return <Circle className="w-4 h-4 text-nasa-muted/40 flex-shrink-0" />;
  }
}

function TelemetryTimeline({ steps }: { steps: TelemetryStep[] }) {
  return (
    <div className="space-y-1.5 mt-3">
      {steps.map((step) => (
        <div key={step.id} className="flex items-center gap-2">
          <StepIcon status={step.status} />
          <span className={`text-xs font-mono ${
            step.status === 'completed' ? 'text-nasa-green' :
            step.status === 'in_progress' ? 'text-nasa-amber' :
            'text-nasa-muted/50'
          }`}>
            {step.label}
          </span>
          {step.status === 'in_progress' && (
            <span className="text-xs text-nasa-amber/60 font-mono">IN PROGRESS...</span>
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
    <div className="flex items-center gap-1 text-xs font-mono text-nasa-muted">
      <Clock className="w-3 h-3" />
      {String(m).padStart(2, '0')}:{String(s).padStart(2, '0')}
    </div>
  );
}

export function MissionCard({ mission, onLaunch, compact }: MissionCardProps) {
  const isActive = ['INVESTIGATING', 'FIX_IN_PROGRESS', 'LAUNCHING'].includes(mission.status);
  const isStrikeReady = mission.status === 'INVESTIGATION_COMPLETE' && mission.classification === 'STRIKE';

  const borderColor = isActive ? 'border-nasa-cyan/50 animate-pulse-glow' :
    isStrikeReady ? 'border-nasa-green/50' :
    mission.status === 'MISSION_COMPLETE' ? 'border-nasa-green/30' :
    mission.status === 'FAILED' ? 'border-nasa-red/30' :
    'border-nasa-border';

  return (
    <div className={`rounded-lg border ${borderColor} bg-nasa-panel p-4 transition-all duration-300 animate-fade-in`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {statusDot(mission.status)}
          <span className="text-xs font-mono text-nasa-cyan font-bold">{mission.id}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {classificationBadge(mission.classification)}
          <ElapsedTimer startedAt={mission.started_at} completedAt={mission.completed_at} />
        </div>
      </div>

      {/* Title */}
      <h3 className="text-sm font-sans text-nasa-text mt-2 line-clamp-2">
        {mission.issue_title}
      </h3>

      {/* Issue link */}
      {mission.issue_url && (
        <a
          href={mission.issue_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-nasa-cyan/60 hover:text-nasa-cyan font-mono mt-1 inline-block"
        >
          #{mission.issue_number}
        </a>
      )}

      {/* Telemetry Timeline (for active/complete missions) */}
      {!compact && mission.telemetry.length > 0 && (
        <TelemetryTimeline steps={mission.telemetry} />
      )}

      {/* Investigation Report Summary */}
      {!compact && mission.investigation_report && (
        <div className="mt-3 p-2 rounded bg-nasa-navy/50 border border-nasa-border/50">
          <div className="text-xs font-mono text-nasa-muted mb-1">ROOT CAUSE</div>
          <p className="text-xs text-nasa-text/80 line-clamp-3">
            {mission.investigation_report.root_cause}
          </p>
          {mission.investigation_report.fix_confidence > 0 && (
            <div className="flex items-center gap-2 mt-2">
              <span className="text-xs font-mono text-nasa-muted">CONFIDENCE</span>
              <div className="flex-1 h-1.5 bg-nasa-navy rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    mission.investigation_report.fix_confidence >= 80 ? 'bg-nasa-green' :
                    mission.investigation_report.fix_confidence >= 50 ? 'bg-nasa-amber' :
                    'bg-nasa-red'
                  }`}
                  style={{ width: `${mission.investigation_report.fix_confidence}%` }}
                />
              </div>
              <span className="text-xs font-mono text-nasa-text">
                {mission.investigation_report.fix_confidence}%
              </span>
            </div>
          )}
        </div>
      )}

      {/* GO FOR LAUNCH button */}
      {isStrikeReady && onLaunch && (
        <button
          onClick={() => onLaunch(mission.id)}
          className="mt-4 w-full py-2.5 rounded-lg font-mono text-sm font-bold uppercase tracking-wider
            bg-nasa-green/20 text-nasa-green border-2 border-nasa-green/50
            hover:bg-nasa-green/30 hover:border-nasa-green
            animate-pulse-glow transition-all duration-200
            flex items-center justify-center gap-2"
        >
          <Rocket className="w-4 h-4" />
          GO FOR LAUNCH
        </button>
      )}

      {/* PR Link for completed missions */}
      {mission.pr_url && (
        <a
          href={mission.pr_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 flex items-center gap-2 text-xs font-mono text-nasa-cyan hover:text-nasa-cyan/80"
        >
          <CheckCircle2 className="w-3.5 h-3.5" />
          View PR
        </a>
      )}

      {/* Error display */}
      {mission.error && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-nasa-red font-mono">
          <AlertTriangle className="w-3.5 h-3.5" />
          {mission.error}
        </div>
      )}
    </div>
  );
}
