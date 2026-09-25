import { useState } from "react";
import { usePlan } from "@/hooks/usePlan";
import { SplitLayout } from "@/components/SplitLayout";
import { GanttView } from "@/components/gantt/GanttView";
import type { Zoom } from "@/components/gantt/mapping";

function App() {
  const { data, isLoading, isError, error } = usePlan();
  const [zoom] = useState<Zoom>("day");
  const [highlighted] = useState<ReadonlySet<number>>(() => new Set());

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
              <div className="flex h-full items-center justify-center p-4 text-muted-foreground">
                Чат появится на следующем этапе
              </div>
            }
          />
        )}
      </main>
    </div>
  );
}

export default App;
