// Shared with DiffSummary (chat diff) and TaskHistory (task modal history) so both describe a
// `Change` the same way: same Russian field labels, same date formatting for date-valued fields.
import type { Change, ChangeField } from "@/api/types";
import { formatRu } from "@/lib/dates";

export const FIELD_LABELS: Record<ChangeField, string> = {
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

export function formatChangeValue(field: ChangeField, value: Change["before"]): string {
  if (value === null || value === undefined || value === "") return "—";
  if (DATE_FIELDS.has(field) && typeof value === "string") return formatRu(value);
  return String(value);
}

export function describeChange(change: Change): string {
  const label = FIELD_LABELS[change.field];
  if (change.field === "created" || change.field === "deleted") return label;
  return `${label} ${formatChangeValue(change.field, change.before)} → ${formatChangeValue(change.field, change.after)}`;
}
