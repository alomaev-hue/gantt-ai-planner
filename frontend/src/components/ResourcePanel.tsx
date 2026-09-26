import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { ScheduledPlan } from "@/api/types";
import { formatRu } from "@/lib/dates";
import { computeResourceSummary, ruPlural } from "@/lib/resourceSummary";

export function ResourcePanel({
  plan,
  onOpenTask,
}: {
  plan: ScheduledPlan;
  onOpenTask(id: number): void;
}) {
  const [expanded, setExpanded] = useState(false);
  const summary = computeResourceSummary(plan);

  return (
    <div className="shrink-0 border-t border-border bg-background">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium hover:bg-accent"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <span>Загрузка</span>
        {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {expanded && (
        <div className="max-h-56 overflow-y-auto border-t border-border px-3 py-2 text-sm">
          {summary.length === 0 ? (
            <p className="text-muted-foreground">Нет задач</p>
          ) : (
            <ul className="flex flex-col gap-2.5">
              {summary.map((s) => (
                <li key={s.assignee ?? "\u0000none"}>
                  <div className="font-medium text-foreground">{s.assignee ?? "Без исполнителя"}</div>
                  <div className="text-muted-foreground">
                    {s.taskCount} {ruPlural(s.taskCount, "задача", "задачи", "задач")}
                    {" · "}
                    {s.workdays} {ruPlural(s.workdays, "рабочий день", "рабочих дня", "рабочих дней")}
                    {s.spanStart && s.spanEnd && (
                      <>
                        {" · "}
                        {formatRu(s.spanStart)}–{formatRu(s.spanEnd)}
                      </>
                    )}
                  </div>
                  {s.conflicts.length > 0 && (
                    <div className="mt-0.5 text-amber-600 dark:text-amber-400">
                      Пересечения:{" "}
                      {s.conflicts.map((c, i) => (
                        <span key={`${c.a}-${c.b}`}>
                          {i > 0 && ", "}
                          <button
                            type="button"
                            className="underline hover:text-foreground"
                            onClick={() => onOpenTask(c.a)}
                          >
                            №{c.a}
                          </button>
                          {" ↔ "}
                          <button
                            type="button"
                            className="underline hover:text-foreground"
                            onClick={() => onOpenTask(c.b)}
                          >
                            №{c.b}
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
