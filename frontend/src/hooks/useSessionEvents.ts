import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ensureSession } from "@/api/client";
import { PLAN_KEY } from "./usePlan";

const RECONNECT_DELAY_MS = 2000;

interface AgentStatusPayload {
  busy?: boolean;
}

// Opens the session-wide live event stream (GET /api/events): `agent_status` toggles the busy
// flag surfaced here, `plan_changed` invalidates the plan query and notifies the caller (so a
// second tab of the same session, or a background tool call, refreshes the Gantt too). On a
// stream error it closes, re-establishes the session, and reconnects after a short delay.
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

    const handlePlanChanged = () => {
      void queryClient.invalidateQueries({ queryKey: PLAN_KEY });
      onPlanChangedRef.current([]);
    };

    const connect = () => {
      if (stopped) return;
      const es = new EventSource("/api/events");
      source = es;
      es.addEventListener("agent_status", handleAgentStatus);
      es.addEventListener("plan_changed", handlePlanChanged);
      es.onerror = () => {
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
      source?.close();
    };
  }, [queryClient]);

  return { agentBusy };
}
