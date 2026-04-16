import { useState } from 'react';
import { Play, CheckCircle2, Clock, AlertTriangle, XCircle, Circle, Loader2, ExternalLink, ChevronDown, ChevronUp, BookOpen, ArrowRight, Eye } from 'lucide-react';
import type { Investigation, InvestigationClassification, TelemetryStep } from '../types/investigation';

interface InvestigationCardProps {
  investigation: Investigation;
  onLaunch?: (investigationId: string) => void;
  onRoute?: (investigationId: string, action: string) => void;
  compact?: boolean;
}

function classificationBadge(c: InvestigationClassification | null) {
  if (!c) return null;
  const config: Record<string, { label: string; style: string }> = {
    AUTO_FIX: { label: 'Auto-fix', style: 'bg-app-success-light text-app-success' },
    NEEDS_REVIEW: { label: 'Needs Review', style: 'bg-app-warning-light text-app-warning' },
    ESCALATE: { label: 'Escalate', style: 'bg-app-danger-light text-app-danger' },
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
    case 'RESOLVED':
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

export function InvestigationCard({ investigation, onLaunch, onRoute, compact }: InvestigationCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isActive = ['INVESTIGATING', 'FIX_IN_PROGRESS', 'LAUNCHING'].includes(investigation.status);
  const isAutoFixReady = investigation.status === 'INVESTIGATION_COMPLETE' && investigation.classification === 'AUTO_FIX';
  const isNeedsReview = investigation.status === 'INVESTIGATION_COMPLETE' && investigation.classification === 'NEEDS_REVIEW';
  const isEscalate = investigation.status === 'INVESTIGATION_COMPLETE' && investigation.classification === 'ESCALATE';

  const borderStyle = isActive ? 'border-app-primary/30 shadow-sm shadow-app-primary/5' :
    isAutoFixReady ? 'border-app-success/40 shadow-sm' :
    investigation.status === 'RESOLVED' ? 'border-app-success/20' :
    investigation.status === 'FAILED' ? 'border-app-danger/20' :
    'border-app-border';

  const isClickable = compact;
  const showDetails = !compact || expanded;

  return (
    <div
      className={`rounded-lg border ${borderStyle} bg-white p-4 transition-all duration-300 animate-fade-in ${
        isClickable ? 'cursor-pointer hover:shadow-md hover:border-app-primary/30' : ''
      }`}
      onClick={isClickable ? () => setExpanded(!expanded) : undefined}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {statusDot(investigation.status)}
          <span className="text-xs font-mono text-app-primary font-semibold">{investigation.id}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {classificationBadge(investigation.classification)}
          <ElapsedTimer startedAt={investigation.started_at} completedAt={investigation.completed_at} />
          {isClickable && (
            expanded
              ? <ChevronUp className="w-3.5 h-3.5 text-app-text-muted" />
              : <ChevronDown className="w-3.5 h-3.5 text-app-text-muted" />
          )}
        </div>
      </div>

      {/* Title */}
      <h3 className="text-sm font-medium text-app-text mt-2 line-clamp-2">
        {investigation.issue_title}
      </h3>

      {/* Issue link + playbook badge */}
      <div className="flex items-center gap-2 mt-1 flex-wrap">
        {investigation.issue_url && (
          <a
            href={investigation.issue_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-app-text-muted hover:text-app-primary"
            onClick={(e) => e.stopPropagation()}
          >
            #{investigation.issue_number}
          </a>
        )}
        {investigation.playbook_name && (
          investigation.playbook_id ? (
            <a
              href={`https://app.devin.ai/org/${import.meta.env.VITE_DEVIN_ORG_SLUG || 'jessie-young-demo'}/settings/playbooks/${investigation.playbook_id.replace('playbook-', '')}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-app-text-muted hover:text-app-primary bg-app-panel px-1.5 py-0.5 rounded"
              onClick={(e) => e.stopPropagation()}
            >
              <BookOpen className="w-3 h-3" />
              {investigation.playbook_name}
            </a>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs text-app-text-muted bg-app-panel px-1.5 py-0.5 rounded">
              <BookOpen className="w-3 h-3" />
              {investigation.playbook_name}
            </span>
          )
        )}
      </div>

      {/* Investigation Timeline */}
      {showDetails && investigation.telemetry.length > 0 && (
        <InvestigationTimeline steps={investigation.telemetry} />
      )}

      {/* Investigation Report Summary */}
      {showDetails && investigation.investigation_report && (
        <div className="mt-3 p-3 rounded-lg bg-app-panel border border-app-border-light">
          <div className="text-xs font-medium text-app-text-secondary mb-1">Root Cause</div>
          <p className="text-xs text-app-text-secondary line-clamp-3">
            {investigation.investigation_report.root_cause}
          </p>
          {investigation.investigation_report.fix_confidence > 0 && (
            <div className="flex items-center gap-2 mt-2">
              <span className="text-xs text-app-text-muted">Confidence</span>
              <div className="flex-1 h-1.5 bg-app-border rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    investigation.investigation_report.fix_confidence >= 80 ? 'bg-app-success' :
                    investigation.investigation_report.fix_confidence >= 50 ? 'bg-app-warning' :
                    'bg-app-danger'
                  }`}
                  style={{ width: `${investigation.investigation_report.fix_confidence}%` }}
                />
              </div>
              <span className="text-xs font-medium text-app-text-secondary">
                {investigation.investigation_report.fix_confidence}%
              </span>
            </div>
          )}
        </div>
      )}

      {/* Apply Fix button */}
      {isAutoFixReady && onLaunch && (
        <button
          onClick={(e) => { e.stopPropagation(); onLaunch(investigation.id); }}
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

      {/* Route to Team button for NEEDS_REVIEW */}
      {isNeedsReview && onRoute && (
        <button
          onClick={(e) => { e.stopPropagation(); onRoute(investigation.id, 'route'); }}
          className="mt-4 w-full py-2.5 rounded-lg text-sm font-semibold
            bg-app-warning text-white
            hover:opacity-90
            transition-all duration-200
            flex items-center justify-center gap-2 shadow-sm"
        >
          <Eye className="w-4 h-4" />
          Route to Team
        </button>
      )}

      {/* Escalate button for ESCALATE */}
      {isEscalate && onRoute && (
        <button
          onClick={(e) => { e.stopPropagation(); onRoute(investigation.id, 'route'); }}
          className="mt-4 w-full py-2.5 rounded-lg text-sm font-semibold
            bg-app-danger text-white
            hover:opacity-90
            transition-all duration-200
            flex items-center justify-center gap-2 shadow-sm"
        >
          <ArrowRight className="w-4 h-4" />
          Escalate to Lead
        </button>
      )}

      {/* PR link for completed investigations */}
      {showDetails && investigation.pr_url && (
        <a
          href={investigation.pr_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-app-primary hover:text-app-primary-hover"
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink className="w-3.5 h-3.5" />
          View Pull Request
        </a>
      )}

      {/* Error display */}
      {investigation.error && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-app-danger">
          <AlertTriangle className="w-3.5 h-3.5" />
          {investigation.error}
        </div>
      )}
    </div>
  );
}
