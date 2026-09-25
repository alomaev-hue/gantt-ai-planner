import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { usePlan } from "@/hooks/usePlan";
import { useSessionEvents } from "@/hooks/useSessionEvents";
import { CHANGED_TASK_IDS_KEY } from "@/hooks/useChat";
import { SplitLayout } from "@/components/SplitLayout";
import { GanttView } from "@/components/gantt/GanttView";
import { ChatPanel } from "@/components/chat/ChatPanel";
import type { Zoom } from "@/components/gantt/mapping";

function App() {
  const { data, isLoading, isError, error } = usePlan();
  const [zoom] = useState<Zoom>("day");
  const [focusedIds, setFocusedIds] = useState<ReadonlySet<number>>(() => new Set());

  // `useChat` (inside `ChatPanel`) writes the ids touched by the latest agent turn to this
  // query key so the Gantt can pulse them without a bespoke prop between the two subtrees.
  const { data: changedTaskIds = [] } = useQuery<number[]>({
    queryKey: CHANGED_TASK_IDS_KEY,
    queryFn: () => [],
    enabled: false,
    initialData: [],
  });

  const { agentBusy } = useSessionEvents((ids) => {
    if (ids.length) setFocusedIds(new Set(ids));
  });

  const highlighted = useMemo(
    () => new Set([...focusedIds, ...changedTaskIds]),
    [focusedIds, changedTaskIds],
  );

  return (
    <div className="flex h-screen min-h-0 flex-col">
      <header className="flex items-center border-b border-border px-4 py-3">
        <h1 className="text-lg font-semibold">Gantt AI Planner</h1>
      </header>
      <main className="min-h-0 flex-1">
        {isLoading && <div className="p-4 text-muted-foreground">Загрузка плана…</div>}
        {isError && (
          <div className="p-4 text-destructive">
            Не удалось загрузить план: {error instanceof Error ? error.message : "неизвестная ошибка"}
          </div>
        )}
        {data && (
          <SplitLayout
            left={
              <GanttView
                plan={data.plan}
                zoom={zoom}
                highlighted={highlighted}
                readOnly
                onOpenTask={() => {
                  /* Phase 2: opens the task edit modal. */
                }}
              />
            }
            right={
              <ChatPanel onFocusTask={(id) => setFocusedIds(new Set([id]))} agentBusy={agentBusy} />
            }
          />
        )}
      </main>
    </div>
  );
}

export default App;
