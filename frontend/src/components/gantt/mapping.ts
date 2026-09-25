import type { ScheduledPlan } from "@/api/types";
import { addDays, parseISODate } from "@/lib/dates";
import type { IScaleConfig } from "@svar-ui/react-gantt";

export type Zoom = "day" | "week" | "month";

export interface SvarTask {
  id: number; text: string; start: Date; end: Date; type: "task" | "critical" | "changed";
  progress: number; assignee: string; workDays: number; conflict: boolean;
}
export interface SvarLink { id: number; source: number; target: number; type: "e2s" }

export function toSvarTasks(plan: ScheduledPlan, highlighted: ReadonlySet<number>): SvarTask[] {
  return plan.tasks.map((t) => ({
    id: t.id,
    text: t.name,
    start: parseISODate(t.start),
    end: addDays(parseISODate(t.end), 1),
    type: highlighted.has(t.id) ? "changed" : t.is_critical ? "critical" : "task",
    progress: 0,
    assignee: t.assignee ?? "",
    workDays: t.duration,
    conflict: t.overallocated_with.length > 0,
  }));
}

export function toSvarLinks(plan: ScheduledPlan): SvarLink[] {
  return plan.dependencies.map((d, i) => ({ id: i + 1, source: d.predecessor_id, target: d.successor_id, type: "e2s" }));
}

// SVAR IScaleConfig = {unit, step, format?, css?} (@svar-ui/gantt-store). `format` strings use
// SVAR's own token syntax (%F full month, %M short month, %j day-of-month, %Y year); the
// RuLocale wrapper supplies the Russian month/day words those tokens render.
export const ZOOM_PRESETS: Record<Zoom, { scales: IScaleConfig[]; cellWidth: number }> = {
  day: {
    scales: [
      { unit: "month", step: 1, format: "%F %Y" },
      { unit: "day", step: 1, format: "%j" },
    ],
    cellWidth: 38,
  },
  week: {
    scales: [
      { unit: "month", step: 1, format: "%F %Y" },
      { unit: "week", step: 1, format: "Нед. %W" },
    ],
    cellWidth: 100,
  },
  month: {
    scales: [
      { unit: "year", step: 1, format: "%Y" },
      { unit: "month", step: 1, format: "%F" },
    ],
    cellWidth: 130,
  },
};
