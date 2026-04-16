import { useState, useCallback } from 'react';
import { Play, CheckCircle2, Clock, AlertTriangle, XCircle, Circle, Loader2, ExternalLink, ChevronDown, ChevronUp, BookOpen, Eye } from 'lucide-react';
import type { Investigation, InvestigationClassification, TelemetryStep } from '../types/investigation';

interface InvestigationCardProps {
  investigation: Investigation;
  onLaunch?: (investigationId: string) => void;
  onApprove?: (investigationId: string) => void;
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

function priorityBadge(priority: number) {
  if (priority >= 80) return { label: 'P0 Critical', style: 'bg-red-600 text-white' };
  if (priority >= 60) return { label: 'P1 High', style: 'bg-orange-500 text-white' };
  if (priority >= 40) return { label: 'P2 Medium', style: 'bg-yellow-400 text-yellow-900' };
  return { label: 'P3 Low', style: 'bg-slate-200 text-slate-600' };
}

function nextStepText(classification: InvestigationClassification | null): string {
  switch (classification) {
    case 'AUTO_FIX': return 'Ready for auto-fix — click Apply Fix';
    case 'NEEDS_REVIEW': return 'Needs human review before proceeding';
    case 'ESCALATE': return 'Requires senior engineering decision';
    default: return 'Investigation in progress';
  }
}

function statusDot(status: string, telemetry?: TelemetryStep[]) {
  switch (status) {
    case 'QUEUED':
      return <Circle className="w-3 h-3 text-app-primary animate-pulse-soft fill-app-primary/20" />;
    case 'INVESTIGATING':
    case 'FIX_IN_PROGRESS':
    case 'LAUNCHING': {
      // If all telemetry steps are completed, show a check instead of spinner
      // (the status transition may lag behind the telemetry updates)
      const allDone = telemetry && telemetry.length > 0 && telemetry.every(s => s.status === 'completed');
      if (allDone) {
        return <CheckCircle2 className="w-3 h-3 text-app-warning" />;
      }
      return <Loader2 className="w-3 h-3 text-app-warning animate-spin" />;
    }
    case 'INVESTIGATION_COMPLETE':
      return <CheckCircle2 className="w-3 h-3 text-app-warning" />;
    case 'PENDING_REVIEW':
      return <Eye className="w-3 h-3 text-purple-500" />;
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

function RootCauseBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const toggle = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setOpen((v) => !v);
  }, []);

  return (
    <div
      className="p-3 rounded-lg bg-app-panel border border-app-border-light cursor-pointer select-none"
      onClick={toggle}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-app-text-secondary">Root Cause</span>
        {open
          ? <ChevronUp className="w-3.5 h-3.5 text-app-text-muted" />
          : <ChevronDown className="w-3.5 h-3.5 text-app-text-muted" />}
      </div>
      <p className={`text-xs text-app-text-secondary mt-1 ${open ? '' : 'line-clamp-3'}`}>
        {text}
      </p>
    </div>
  );
}

export function InvestigationCard({ investigation, onLaunch, onApprove, compact }: InvestigationCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isActive = ['INVESTIGATING', 'FIX_IN_PROGRESS', 'LAUNCHING'].includes(investigation.status);
  const isAutoFixReady = investigation.status === 'INVESTIGATION_COMPLETE' && investigation.classification === 'AUTO_FIX';
  const needsManualIntervention = investigation.status === 'INVESTIGATION_COMPLETE' && (investigation.classification === 'NEEDS_REVIEW' || investigation.classification === 'ESCALATE');
  const isPendingReview = investigation.status === 'PENDING_REVIEW';

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
          {statusDot(investigation.status, investigation.telemetry)}
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

      {/* Priority + Confidence + Next Steps bar */}
      {showDetails && investigation.investigation_report && (() => {
        const pb = priorityBadge(investigation.priority);
        return (
          <div className="mt-3 space-y-2">
            {/* Priority & Confidence row */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-xs font-bold px-2.5 py-1 rounded-md shadow-sm ${pb.style}`}>
                {pb.label}
              </span>
              {investigation.investigation_report.fix_confidence > 0 && (
                <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
                  investigation.investigation_report.fix_confidence >= 80 ? 'bg-app-success-light text-app-success' :
                  investigation.investigation_report.fix_confidence >= 50 ? 'bg-app-warning-light text-app-warning' :
                  'bg-app-danger-light text-app-danger'
                }`}>
                  {investigation.investigation_report.fix_confidence}% confidence
                </span>
              )}
            </div>
            {/* Next step */}
            <div className="text-xs text-app-text-muted italic">
              Next: {nextStepText(investigation.classification)}
            </div>
            {/* Root cause — expandable */}
            <RootCauseBlock text={investigation.investigation_report.root_cause} />
          </div>
        );
      })()}

      {/* Action buttons row */}
      {(isAutoFixReady || needsManualIntervention || isPendingReview) && (
        <div className="mt-3 flex items-center justify-end gap-2">
          {isAutoFixReady && onLaunch && (
            <button
              onClick={(e) => { e.stopPropagation(); onLaunch(investigation.id); }}
              className="px-3 py-1.5 rounded-md text-xs font-semibold
                bg-app-primary text-white
                hover:bg-app-primary-hover
                transition-all duration-200
                inline-flex items-center gap-1.5 shadow-sm"
            >
              <Play className="w-3.5 h-3.5" />
              Apply Fix
            </button>
          )}
          {needsManualIntervention && investigation.issue_url && (
            <a
              href={investigation.issue_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold
                ${investigation.classification === 'ESCALATE' ? 'bg-app-danger' : 'bg-app-warning'} text-white
                hover:opacity-90
                transition-all duration-200
                inline-flex items-center gap-1.5 shadow-sm`}
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Investigate Manually
            </a>
          )}
          {isPendingReview && (
            <>
              {investigation.pr_url && (
                <a
                  href={investigation.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="px-3 py-1.5 rounded-md text-xs font-semibold
                    bg-app-panel text-app-text-secondary border border-app-border
                    hover:bg-app-panel/80
                    transition-all duration-200
                    inline-flex items-center gap-1.5 shadow-sm"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  View PR
                </a>
              )}
              {onApprove && (
                <button
                  onClick={(e) => { e.stopPropagation(); onApprove(investigation.id); }}
                  className="px-3 py-1.5 rounded-md text-xs font-semibold
                    bg-app-success text-white
                    hover:bg-app-success/90
                    transition-all duration-200
                    inline-flex items-center gap-1.5 shadow-sm"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Approve & Resolve
                </button>
              )}
            </>
          )}
        </div>
      )}

      {/* PR link for resolved/completed investigations (not shown when isPendingReview since the actions row already has a View PR button) */}
      {showDetails && investigation.pr_url && !isPendingReview && (
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
