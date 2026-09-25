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

// SVAR (@svar-ui/lib-dom `locate`) marks both grid rows and gantt bars with a `data-id`
// attribute holding the task id. We use it to open the task modal only on a genuine pointer
// click (bubbling up from the clicked row/bar to our own container's onClick), instead of
// SVAR's `select-task` API event, which also fires on keyboard grid navigation.
export function closestTaskId(target: EventTarget | null): number | null {
  if (!(target instanceof Element)) return null;
  // A click on a bar's link connector (`.wx-link`, the little dot at each end used to draw a
  // dependency) still bubbles up through the bar's own `[data-id]` element — without this guard
  // it would pop the task modal open *and* cover the target connector before the user's second
  // click can land on it, making it impossible to ever finish drawing a link.
  if (target.closest(".wx-link")) return null;
  const el = target.closest("[data-id]");
  const raw = el?.getAttribute("data-id");
  if (!raw) return null;
  const id = Number(raw);
  return Number.isFinite(id) ? id : null;
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
