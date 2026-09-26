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

// Every change here is for the task whose modal is already open, so a click-to-focus affordance
// (as DiffSummary has, for a chat turn that can touch *other* tasks) would just be a no-op
// "navigate to the task you're already looking at" — plain text lines only (spec review round 1).
function HistoryEntry({ entry }: { entry: TaskHistoryEntry }) {
  return (
    <li className="rounded-md border border-border p-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          Версия {entry.version} · {SOURCE_LABELS[entry.source]}
        </span>
        <span>{formatRuDateTime(entry.created_at)}</span>
      </div>
      <ul className="mt-1 flex flex-col gap-0.5">
        {entry.changes.length === 0 ? (
          <li className="text-sm text-foreground">{entry.summary}</li>
        ) : (
          entry.changes.map((change, index) => (
            <li key={`${change.field}-${index}`} className="text-sm text-foreground">
              {describeChange(change)}
            </li>
          ))
        )}
      </ul>
    </li>
  );
}

export function TaskHistory({ taskId, version }: { taskId: number; version: number }) {
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
            <HistoryEntry key={entry.version} entry={entry} />
          ))}
        </ul>
      )}
    </div>
  );
}
