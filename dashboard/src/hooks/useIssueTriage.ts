import { useState, useEffect, useCallback, useRef } from 'react';
import type { Investigation, DashboardState, TelemetryLogEntry, SSEEvent } from '../types/investigation';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001';

export function useIssueTriage() {
  const [investigations, setInvestigations] = useState<Record<string, Investigation>>({});
  const [stats, setStats] = useState({
    active: 0, completed: 0, queued: 0, total: 0, resolved_today: 0,
    auto_fix_count: 0, needs_review_count: 0, escalate_count: 0,
  });
  const [uptimeStart, setUptimeStart] = useState<number>(Date.now() / 1000);
  const [telemetryLog, setTelemetryLog] = useState<TelemetryLogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const addLogEntry = useCallback((investigationId: string, text: string) => {
    setTelemetryLog(prev => {
      const entry: TelemetryLogEntry = {
        timestamp: Date.now() / 1000,
        investigation_id: investigationId,
        text,
      };
      const next = [...prev, entry];
      return next.slice(-200);
    });
  }, []);

  const recalcStats = useCallback((investigationMap: Record<string, Investigation>) => {
    const all = Object.values(investigationMap);
    const todayStart = new Date();
    todayStart.setUTCHours(0, 0, 0, 0);
    const todayStartSec = todayStart.getTime() / 1000;
    setStats({
      active: all.filter(m => ['INVESTIGATING', 'INVESTIGATION_COMPLETE', 'FIX_IN_PROGRESS', 'LAUNCHING'].includes(m.status)).length,
      completed: all.filter(m => ['RESOLVED', 'ROUTED', 'CLOSED'].includes(m.status)).length,
      queued: all.filter(m => m.status === 'QUEUED').length,
      total: all.length,
      resolved_today: all.filter(m =>
        ['RESOLVED', 'ROUTED', 'CLOSED'].includes(m.status) &&
        m.completed_at != null && m.completed_at >= todayStartSec
      ).length,
      auto_fix_count: all.filter(m => m.classification === 'AUTO_FIX').length,
      needs_review_count: all.filter(m => m.classification === 'NEEDS_REVIEW').length,
      escalate_count: all.filter(m => m.classification === 'ESCALATE').length,
    });
  }, []);

  // Fetch initial state
  const fetchState = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/investigations/state`);
      if (!resp.ok) return;
      const data: DashboardState = await resp.json();
      setInvestigations(data.investigations);
      setStats(data.stats);
      setUptimeStart(data.uptime_start);
    } catch {
      // Will retry on reconnect
    }
  }, []);

  // Connect to SSE
  useEffect(() => {
    fetchState();

    const connect = () => {
      const es = new EventSource(`${API_BASE}/investigations/stream`);
      eventSourceRef.current = es;

      es.onopen = () => setConnected(true);
      es.onerror = () => {
        setConnected(false);
        es.close();
        setTimeout(connect, 3000);
      };

      es.addEventListener('investigation_created', (e) => {
        const event: SSEEvent = JSON.parse(e.data);
        addLogEntry(event.investigation_id, `Investigation ${event.investigation_id} created: ${event.data.title || ''}`);
        fetchState();
      });

      es.addEventListener('investigation_updated', (e) => {
        const event: SSEEvent = JSON.parse(e.data);
        const newStatus = event.data.status as string | undefined;
        // If status changed to a terminal/phase state, do a full refetch for accurate data
        // Note: RESOLVED log entry is handled by the dedicated investigation_resolved event handler
        if (newStatus && ['RESOLVED', 'ROUTED', 'CLOSED', 'FAILED', 'FIX_IN_PROGRESS', 'LAUNCHING'].includes(newStatus)) {
          fetchState();
        } else {
          setInvestigations(prev => {
            const updated = { ...prev };
            if (updated[event.investigation_id]) {
              updated[event.investigation_id] = { ...updated[event.investigation_id], ...event.data } as Investigation;
            }
            recalcStats(updated);
            return updated;
          });
        }
      });

      es.addEventListener('telemetry_update', (e) => {
        const event: SSEEvent = JSON.parse(e.data);
        const stepId = event.data.step_id as string;
        const status = event.data.status as string;
        const detail = event.data.detail as string | undefined;

        setInvestigations(prev => {
          const updated = { ...prev };
          const investigation = updated[event.investigation_id];
          if (investigation) {
            updated[event.investigation_id] = {
              ...investigation,
              telemetry: investigation.telemetry.map(s =>
                s.id === stepId ? { ...s, status, timestamp: Date.now() / 1000, detail: detail || s.detail } : s
              ),
            } as Investigation;
          }
          return updated;
        });

        if (detail) {
          addLogEntry(event.investigation_id, detail);
        }
      });

      es.addEventListener('telemetry_raw', (e) => {
        const event: SSEEvent = JSON.parse(e.data);
        addLogEntry(event.investigation_id, event.data.text as string);
      });

      es.addEventListener('investigation_complete', (e) => {
        const event: SSEEvent = JSON.parse(e.data);
        addLogEntry(event.investigation_id, `Investigation complete — ${event.data.classification} (confidence: ${event.data.confidence})`);
        fetchState();
      });

      es.addEventListener('investigation_resolved', (e) => {
        const event: SSEEvent = JSON.parse(e.data);
        const prUrl = event.data.pr_url as string | undefined;
        addLogEntry(event.investigation_id, `RESOLVED${prUrl ? ` — PR: ${prUrl}` : ''}`);
        fetchState();
      });

      es.addEventListener('investigations_cleared', () => {
        addLogEntry('SYSTEM', 'Dashboard reset — all investigations cleared');
        fetchState();
      });
    };

    connect();

    return () => {
      eventSourceRef.current?.close();
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [fetchState, addLogEntry, recalcStats]);

  // Launch a fix
  const launchFix = useCallback(async (investigationId: string) => {
    try {
      // Optimistic update — immediately show status change on the card
      setInvestigations(prev => {
        const updated = { ...prev };
        if (updated[investigationId]) {
          updated[investigationId] = { ...updated[investigationId], status: 'LAUNCHING' as Investigation['status'] };
        }
        recalcStats(updated);
        return updated;
      });

      const resp = await fetch(`${API_BASE}/investigations/launch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ investigation_id: investigationId }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'Launch failed');
      }
      addLogEntry(investigationId, 'Apply Fix initiated');
      await fetchState();
      // Poll for updates during fix (every 3s for 60s)
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      let polls = 0;
      pollIntervalRef.current = setInterval(async () => {
        polls++;
        try {
          await fetchState();
        } catch {
          // Network error during poll — will retry on next tick
        }
        if (polls >= 20) {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      }, 3000);
    } catch (err) {
      addLogEntry(investigationId, `Launch error: ${err}`);
      // Revert optimistic update on error
      await fetchState();
    }
  }, [addLogEntry, fetchState, recalcStats]);

  // Reset all investigations (clear the board)
  const resetInvestigations = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/investigations/reset`, { method: 'POST' });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'Reset failed');
      }
      addLogEntry('SYSTEM', 'Dashboard reset requested');
      await fetchState();
    } catch (err) {
      addLogEntry('SYSTEM', `Reset error: ${err}`);
    }
  }, [addLogEntry, fetchState]);

  // Kick off all queued investigations at once
  const investigateAll = useCallback(async () => {
    try {
      // Optimistic update — immediately mark all QUEUED as INVESTIGATING
      setInvestigations(prev => {
        const updated = { ...prev };
        for (const id of Object.keys(updated)) {
          if (updated[id].status === 'QUEUED') {
            updated[id] = { ...updated[id], status: 'INVESTIGATING' as Investigation['status'] };
          }
        }
        recalcStats(updated);
        return updated;
      });

      const resp = await fetch(`${API_BASE}/investigations/investigate-all`, {
        method: 'POST',
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'Investigate all failed');
      }
      const data = await resp.json();
      addLogEntry('SYSTEM', `Started ${data.started} investigations`);
      await fetchState();
      // Poll for updates as investigations complete
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      let polls = 0;
      pollIntervalRef.current = setInterval(async () => {
        polls++;
        try {
          await fetchState();
        } catch {
          // Network error during poll — will retry on next tick
        }
        if (polls >= 20) {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      }, 3000);
    } catch (err) {
      addLogEntry('SYSTEM', `Investigate all error: ${err}`);
      await fetchState();
    }
  }, [addLogEntry, fetchState, recalcStats]);

  // File a manual investigation
  const fileInvestigation = useCallback(async (issueInput: string) => {
    try {
      const body: Record<string, unknown> = {};
      if (issueInput.includes('github.com')) {
        body.issue_url = issueInput;
      } else {
        body.issue_number = parseInt(issueInput, 10);
      }
      const resp = await fetch(`${API_BASE}/investigations/file`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'File investigation failed');
      }
      const data = await resp.json();
      addLogEntry(data.investigation_id, 'Manual investigation filed');
      await fetchState();
    } catch (err) {
      addLogEntry('SYSTEM', `File investigation error: ${err}`);
    }
  }, [addLogEntry, fetchState]);

  return {
    investigations,
    stats,
    uptimeStart,
    telemetryLog,
    connected,
    launchFix,
    investigateAll,
    fileInvestigation,
    resetInvestigations,
  };
}
