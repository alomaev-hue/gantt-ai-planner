import { useState } from "react";
import type { Change, ChangeField } from "@/api/types";
import { formatRu } from "@/lib/dates";
import { cn } from "@/lib/utils";

const FIELD_LABELS: Record<ChangeField, string> = {
  name: "название",
  description: "описание",
  assignee: "исполнитель",
  duration: "длительность",
  constraint_start: "не раньше",
  predecessors: "предшественники",
  start: "начало",
  end: "окончание",
  created: "добавлена",
  deleted: "удалена",
};

const DATE_FIELDS: ReadonlySet<ChangeField> = new Set(["start", "end", "constraint_start"]);

function formatValue(field: ChangeField, value: Change["before"]): string {
  if (value === null || value === undefined || value === "") return "—";
  if (DATE_FIELDS.has(field) && typeof value === "string") return formatRu(value);
  return String(value);
}

function describeChange(change: Change): string {
  const label = FIELD_LABELS[change.field];
  if (change.field === "created" || change.field === "deleted") return label;
  return `${label} ${formatValue(change.field, change.before)} → ${formatValue(change.field, change.after)}`;
}

export function DiffSummary({
  summary,
  changes,
  onFocusTask,
}: {
  summary: string;
  changes: Change[];
  onFocusTask: (id: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="mt-2 overflow-hidden rounded-md border border-border bg-muted/50 text-sm">
      <button
        type="button"
        className="w-full px-2 py-1 text-left font-medium text-foreground hover:bg-accent"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        {summary}
      </button>
      {expanded && (
        <ul className="border-t border-border px-2 py-1">
          {changes.map((change, index) => {
            const focusable = change.field !== "deleted";
            return (
              <li key={`${change.task_id}-${change.field}-${index}`}>
                <button
                  type="button"
                  disabled={!focusable}
                  className={cn(
                    "w-full py-0.5 text-left text-muted-foreground",
                    focusable && "hover:text-foreground hover:underline",
                  )}
                  onClick={() => {
                    if (focusable) onFocusTask(change.task_id);
                  }}
                >
                  №{change.task_id} «{change.task_name}»: {describeChange(change)}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
