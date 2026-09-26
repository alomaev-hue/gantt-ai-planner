import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { streamChat } from "@/api/chatStream";
import type { Change, ChatMessage } from "@/api/types";
import { PLAN_KEY } from "./usePlan";

export const CHAT_HISTORY_KEY = ["chat", "history"];

// Human labels for the tool-call status line shown while the agent is working.
const TOOL_LABELS: Record<string, string> = {
  apply_operations: "применяю изменения",
  get_plan: "смотрю план",
  find_tasks: "ищу задачи",
  get_task: "смотрю задачу",
  get_resource_load: "проверяю загрузку",
  undo: "отменяю",
};

export interface StreamingState {
  text: string;
  status: string | null;
}

let localIdSeq = 0;
function localMessage(role: ChatMessage["role"], content: string, meta: ChatMessage["meta"] = {}): ChatMessage {
  localIdSeq -= 1;
  return { id: localIdSeq, role, content, created_at: new Date().toISOString(), meta };
}

export function useChat(): {
  messages: ChatMessage[];
  streaming: StreamingState | null;
  send(text: string): Promise<void>;
  error: string | null;
} {
  const queryClient = useQueryClient();
  const historyQuery = useQuery({ queryKey: CHAT_HISTORY_KEY, queryFn: api.chatHistory });
  // Optimistic messages for the turn in flight (the user's text + the streamed reply). They sit
  // on top of the persisted history and are cleared once the invalidated history query has
  // re-fetched and (now) contains them — deriving `messages` this way needs no effect to keep a
  // separate copy of `historyQuery.data` in sync.
  const [turnMessages, setTurnMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState<StreamingState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sendingRef = useRef(false);

  const messages = useMemo(
    () => [...(historyQuery.data ?? []), ...turnMessages],
    [historyQuery.data, turnMessages],
  );

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sendingRef.current) return;
      sendingRef.current = true;
      setError(null);
      setTurnMessages((prev) => [...prev, localMessage("user", trimmed)]);
      let accumulated = "";
      let status: string | null = null;
      setStreaming({ text: "", status: null });
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        for await (const event of streamChat(trimmed, controller.signal)) {
          switch (event.type) {
            case "text_delta":
              accumulated += event.text;
              setStreaming({ text: accumulated, status });
              break;
            case "tool_started":
              status = `Выполняю: ${TOOL_LABELS[event.name] ?? event.name}`;
              setStreaming({ text: accumulated, status });
              break;
            case "tool_finished":
              break;
            case "plan_changed":
              void queryClient.invalidateQueries({ queryKey: PLAN_KEY });
              break;
            case "done": {
              const changes: Change[] = event.changes ?? [];
              setTurnMessages((prev) => [
                ...prev,
                localMessage("assistant", accumulated, { summary: event.summary, changes }),
              ]);
              // The Gantt highlight for these ids comes from `useSessionEvents`' own
              // `plan_changed` bus event (published for every apply, including this one), not
              // from here.
              break;
            }
            case "error":
              // A failed turn is saved by the server as the assistant's reply, so it shows once,
              // as that bubble. `agent_busy` is the exception: that turn never started and
              // nothing was saved (its message is dropped), so it goes to the error line.
              if (event.code === "agent_busy") {
                setError(event.message);
              } else {
                setTurnMessages((prev) => [...prev, localMessage("assistant", event.message, { error: event.code })]);
              }
              break;
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Не удалось отправить сообщение");
      } finally {
        setStreaming(null);
        abortRef.current = null;
        sendingRef.current = false;
        await queryClient.invalidateQueries({ queryKey: CHAT_HISTORY_KEY });
        void queryClient.invalidateQueries({ queryKey: PLAN_KEY });
        setTurnMessages([]);
      }
    },
    [queryClient],
  );

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  return { messages, streaming, send, error };
}
