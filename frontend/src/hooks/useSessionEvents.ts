import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ensureSession } from "@/api/client";
import { PLAN_KEY } from "./usePlan";

const RECONNECT_DELAY_MS = 2000;

interface AgentStatusPayload {
  busy?: boolean;
}

// backend/app/services/plan_service.py `_publish`: {type, version, source, turn_id, changed_task_ids}.
interface PlanChangedPayload {
  source?: string;
  changed_task_ids?: number[];
}

// Sources that replace the whole plan: every task id is "changed", so highlighting them would
// just paint the entire chart in the highlight colour.
const REPLACING_SOURCES = new Set(["import", "reset", "seed"]);

// Pure so it's easy to unit test: parses the SSE `plan_changed` event's `data` string and
// returns the task ids to highlight — `[]` for a whole-plan replacement, and for
// malformed/missing data instead of throwing.
export function parsePlanChanged(data: string): number[] {
  try {
    const payload = JSON.parse(data) as PlanChangedPayload;
    if (payload.source && REPLACING_SOURCES.has(payload.source)) return [];
    return Array.isArray(payload.changed_task_ids) ? payload.changed_task_ids : [];
  } catch {
    return [];
  }
}

// Opens the session-wide live event stream (GET /api/events): `agent_status` toggles the busy
// flag surfaced here, `plan_changed` invalidates the plan query and reports the ids the change
// touched (so the Gantt can pulse them — this fires for every source: agent, user, mcp, undo,
// not just the tab that made the change; import/reset report none). On a stream error it closes, re-establishes the
// session, and reconnects after a short delay.
export function useSessionEvents(onPlanChanged: (ids: number[]) => void): { agentBusy: boolean } {
  const queryClient = useQueryClient();
  const [agentBusy, setAgentBusy] = useState(false);
  const onPlanChangedRef = useRef(onPlanChanged);

  useEffect(() => {
    onPlanChangedRef.current = onPlanChanged;
  }, [onPlanChanged]);

  useEffect(() => {
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const handleAgentStatus = (event: Event) => {
      try {
        const payload = JSON.parse((event as MessageEvent<string>).data) as AgentStatusPayload;
        setAgentBusy(Boolean(payload.busy));
      } catch {
        /* malformed payload, ignore */
      }
    };

    const handlePlanChanged = (event: Event) => {
      void queryClient.invalidateQueries({ queryKey: PLAN_KEY });
      onPlanChangedRef.current(parsePlanChanged((event as MessageEvent<string>).data));
    };

    const detach = (es: EventSource) => {
      es.removeEventListener("agent_status", handleAgentStatus);
      es.removeEventListener("plan_changed", handlePlanChanged);
    };

    const connect = () => {
      if (stopped) return;
      const es = new EventSource("/api/events");
      source = es;
      es.addEventListener("agent_status", handleAgentStatus);
      es.addEventListener("plan_changed", handlePlanChanged);
      es.onerror = () => {
        detach(es);
        es.close();
        if (stopped) return;
        void ensureSession().catch(() => {
          /* best effort; we reconnect regardless */
        });
        reconnectTimer = setTimeout(() => {
          void queryClient.invalidateQueries({ queryKey: PLAN_KEY });
          connect();
        }, RECONNECT_DELAY_MS);
      };
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (source) {
        detach(source);
        source.close();
      }
    };
  }, [queryClient]);

  return { agentBusy };
}
