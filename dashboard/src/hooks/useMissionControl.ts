import { useState, useEffect, useCallback, useRef } from 'react';
import type { Mission, DashboardState, TelemetryLogEntry, SSEEvent } from '../types/mission';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001';

export function useMissionControl() {
  const [missions, setMissions] = useState<Record<string, Mission>>({});
  const [stats, setStats] = useState({
    active: 0, completed: 0, queued: 0, total: 0, resolved_today: 0,
    strike_count: 0, assist_count: 0, command_count: 0,
  });
  const [uptimeStart, setUptimeStart] = useState<number>(Date.now() / 1000);
  const [telemetryLog, setTelemetryLog] = useState<TelemetryLogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const addLogEntry = useCallback((missionId: string, text: string) => {
    setTelemetryLog(prev => {
      const entry: TelemetryLogEntry = {
        timestamp: Date.now() / 1000,
        mission_id: missionId,
        text,
      };
      const next = [...prev, entry];
      return next.slice(-200);
    });
  }, []);

  const recalcStats = useCallback((missionMap: Record<string, Mission>) => {
    const all = Object.values(missionMap);
    const todayStart = new Date();
    todayStart.setUTCHours(0, 0, 0, 0);
    const todayStartSec = todayStart.getTime() / 1000;
    setStats({
      active: all.filter(m => ['INVESTIGATING', 'INVESTIGATION_COMPLETE', 'FIX_IN_PROGRESS', 'LAUNCHING'].includes(m.status)).length,
      completed: all.filter(m => ['MISSION_COMPLETE', 'ROUTED', 'CLOSED'].includes(m.status)).length,
      queued: all.filter(m => m.status === 'QUEUED').length,
      total: all.length,
      resolved_today: all.filter(m =>
        ['MISSION_COMPLETE', 'ROUTED', 'CLOSED'].includes(m.status) &&
        m.completed_at != null && m.completed_at >= todayStartSec
      ).length,
      strike_count: all.filter(m => m.classification === 'STRIKE').length,
      assist_count: all.filter(m => m.classification === 'ASSIST').length,
      command_count: all.filter(m => m.classification === 'COMMAND').length,
    });
  }, []);

  // Fetch initial state
  const fetchState = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/missions/state`);
      if (!resp.ok) return;
      const data: DashboardState = await resp.json();
      setMissions(data.missions);
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
      const es = new EventSource(`${API_BASE}/missions/stream`);
      eventSourceRef.current = es;

      es.onopen = () => setConnected(true);
      es.onerror = () => {
        setConnected(false);
        es.close();
        setTimeout(connect, 3000);
      };

      es.addEventListener('mission_created', (e) => {
        const event: SSEEvent = JSON.parse(e.data);
        addLogEntry(event.mission_id, `Mission ${event.mission_id} created: ${event.data.title || ''}`);
        fetchState();
      });

      es.addEventListener('mission_updated', (e) => {
        const event: SSEEvent = JSON.parse(e.data);
        const newStatus = event.data.status as string | undefined;
        // If status changed to a terminal/phase state, do a full refetch for accurate data
        // Note: MISSION_COMPLETE log entry is handled by the dedicated mission_complete event handler
        if (newStatus && ['MISSION_COMPLETE', 'ROUTED', 'CLOSED', 'FAILED', 'FIX_IN_PROGRESS', 'LAUNCHING'].includes(newStatus)) {
          fetchState();
        } else {
          setMissions(prev => {
            const updated = { ...prev };
            if (updated[event.mission_id]) {
              updated[event.mission_id] = { ...updated[event.mission_id], ...event.data } as Mission;
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

        setMissions(prev => {
          const updated = { ...prev };
          const mission = updated[event.mission_id];
          if (mission) {
            updated[event.mission_id] = {
              ...mission,
              telemetry: mission.telemetry.map(s =>
                s.id === stepId ? { ...s, status, timestamp: Date.now() / 1000, detail: detail || s.detail } : s
              ),
            } as Mission;
          }
          return updated;
        });

        if (detail) {
          addLogEntry(event.mission_id, detail);
        }
      });

      es.addEventListener('telemetry_raw', (e) => {
        const event: SSEEvent = JSON.parse(e.data);
        addLogEntry(event.mission_id, event.data.text as string);
      });

      es.addEventListener('investigation_complete', (e) => {
        const event: SSEEvent = JSON.parse(e.data);
        addLogEntry(event.mission_id, `Investigation complete — ${event.data.classification} (confidence: ${event.data.confidence})`);
        fetchState();
      });

      es.addEventListener('mission_complete', (e) => {
        const event: SSEEvent = JSON.parse(e.data);
        const prUrl = event.data.pr_url as string | undefined;
        addLogEntry(event.mission_id, `MISSION COMPLETE${prUrl ? ` — PR: ${prUrl}` : ''}`);
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
  const launchFix = useCallback(async (missionId: string) => {
    try {
      const resp = await fetch(`${API_BASE}/missions/launch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mission_id: missionId }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'Launch failed');
      }
      addLogEntry(missionId, 'Apply Fix initiated');
      await fetchState();
      // Poll for updates during simulated fix (every 2s for 20s)
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      let polls = 0;
      pollIntervalRef.current = setInterval(async () => {
        polls++;
        try {
          await fetchState();
        } catch {
          // Network error during poll — will retry on next tick
        }
        if (polls >= 10) {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      }, 2000);
    } catch (err) {
      addLogEntry(missionId, `Launch error: ${err}`);
    }
  }, [addLogEntry, fetchState]);

  // File a manual mission
  const fileMission = useCallback(async (issueInput: string) => {
    try {
      const body: Record<string, unknown> = {};
      if (issueInput.includes('github.com')) {
        body.issue_url = issueInput;
      } else {
        body.issue_number = parseInt(issueInput, 10);
      }
      const resp = await fetch(`${API_BASE}/missions/file`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'File mission failed');
      }
      const data = await resp.json();
      addLogEntry(data.mission_id, 'Manual mission filed');
      await fetchState();
    } catch (err) {
      addLogEntry('SYSTEM', `File mission error: ${err}`);
    }
  }, [addLogEntry, fetchState]);

  return {
    missions,
    stats,
    uptimeStart,
    telemetryLog,
    connected,
    launchFix,
    fileMission,
  };
}
