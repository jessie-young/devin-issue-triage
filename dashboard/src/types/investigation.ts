export type InvestigationStatus =
  | 'QUEUED'
  | 'INVESTIGATING'
  | 'INVESTIGATION_COMPLETE'
  | 'LAUNCHING'
  | 'FIX_IN_PROGRESS'
  | 'RESOLVED'
  | 'ROUTED'
  | 'CLOSED'
  | 'FAILED';

export type InvestigationClassification = 'AUTO_FIX' | 'NEEDS_REVIEW' | 'ESCALATE';

export interface TelemetryStep {
  id: string;
  label: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  timestamp: number | null;
  detail: string | null;
}

export interface InvestigationReport {
  relevant_files: string[];
  git_history: string[];
  root_cause: string;
  complexity: string;
  fix_confidence: number;
  related_issues: number[];
  classification: InvestigationClassification | null;
  summary: string;
  recommended_fix: string;
}

export interface Investigation {
  id: string;
  issue_number: number;
  issue_title: string;
  issue_body: string;
  issue_url: string;
  issue_labels: string[];
  status: InvestigationStatus;
  classification: InvestigationClassification | null;
  playbook_name: string | null;
  playbook_id: string | null;
  devin_session_id: string | null;
  fix_session_id: string | null;
  investigation_report: InvestigationReport | null;
  telemetry: TelemetryStep[];
  pr_url: string | null;
  created_at: number;
  started_at: number | null;
  completed_at: number | null;
  elapsed_seconds: number | null;
  error: string | null;
}

export interface SSEEvent {
  event_type: string;
  investigation_id: string;
  data: Record<string, unknown>;
  timestamp: number;
}

export interface DashboardStats {
  active: number;
  completed: number;
  queued: number;
  total: number;
  resolved_today: number;
  auto_fix_count: number;
  needs_review_count: number;
  escalate_count: number;
}

export interface DashboardState {
  investigations: Record<string, Investigation>;
  stats: DashboardStats;
  uptime_start: number;
}

export interface TelemetryLogEntry {
  timestamp: number;
  investigation_id: string;
  text: string;
}
