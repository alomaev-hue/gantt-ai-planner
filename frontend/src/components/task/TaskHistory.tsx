import type { TaskHistoryEntry, VersionSource } from "@/api/types";
import { useTaskHistory } from "@/hooks/useTaskHistory";
import { describeChange } from "@/lib/changeFormat";
import { formatRuDateTime } from "@/lib/dates";

const SOURCE_LABELS: Record<VersionSource, string> = {
  user: "вы",
  agent: "агент",
  mcp: "MCP",
  import: "импорт",
  reset: "сброс",
  seed: "демо",
};

function HistoryEntry({ entry, onFocusTask }: { entry: TaskHistoryEntry; onFocusTask(id: number): void }) {
  return (
    <li className="rounded-md border border-border p-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          Версия {entry.version} · {SOURCE_LABELS[entry.source]}
        </span>
        <span>{formatRuDateTime(entry.created_at)}</span>
      </div>
      <ul className="mt-1 flex flex-col gap-0.5">
        {entry.changes.map((change, index) => {
          const focusable = change.field !== "deleted";
          return (
            <li key={`${change.field}-${index}`}>
              <button
                type="button"
                disabled={!focusable}
                className="text-left text-sm text-foreground hover:underline disabled:no-underline"
                onClick={() => {
                  if (focusable) onFocusTask(change.task_id);
                }}
              >
                {describeChange(change)}
              </button>
            </li>
          );
        })}
      </ul>
    </li>
  );
}

export function TaskHistory({
  taskId,
  version,
  onFocusTask,
}: {
  taskId: number;
  version: number;
  onFocusTask(id: number): void;
}) {
  const { data, isLoading, isError } = useTaskHistory(taskId, version);

  return (
    <div className="flex flex-col gap-2 text-sm">
      <h3 className="font-medium text-foreground">История</h3>
      {isLoading && <p className="text-muted-foreground">Загрузка истории…</p>}
      {isError && <p className="text-destructive">Не удалось загрузить историю задачи</p>}
      {data && data.length === 0 && <p className="text-muted-foreground">Изменений пока не было</p>}
      {data && data.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {data.map((entry) => (
            <HistoryEntry key={entry.version} entry={entry} onFocusTask={onFocusTask} />
          ))}
        </ul>
      )}
    </div>
  );
}
