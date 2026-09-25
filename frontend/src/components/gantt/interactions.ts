// Turns raw SVAR bar-drag / bar-resize / link-draw events into backend Operations. The backend
// is the source of truth for scheduling, so we never compute a full reschedule here — we only
// classify *what the user did* (moved vs. resized) and emit the matching Operation; the server
// recomputes everything else on `POST /api/plan/operations`.
import { addDays, parseISODate, toISODate, workdaysBetweenInclusive } from "@/lib/dates";
import type { AddDependencyOp, MoveTaskOp, Operation, ScheduledTask, UpdateTaskOp } from "@/api/types";

function sameDate(a: Date, b: Date): boolean {
  return a.getTime() === b.getTime();
}

function daysBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

// `newEndExclusive` matches SVAR's own bar semantics (end = inclusive end + 1 day), same as
// `toSvarTasks` in mapping.ts, so callers can hand it the task straight from the Gantt store.
export function interpretBarChange(before: ScheduledTask, newStart: Date, newEndExclusive: Date): Operation | null {
  const oldStart = parseISODate(before.start);
  const oldEndExclusive = addDays(parseISODate(before.end), 1);

  const startChanged = !sameDate(oldStart, newStart);
  const endChanged = !sameDate(oldEndExclusive, newEndExclusive);
  if (!startChanged && !endChanged) return null;

  const oldLengthDays = daysBetween(oldStart, oldEndExclusive);
  const newLengthDays = daysBetween(newStart, newEndExclusive);

  if (oldLengthDays === newLengthDays) {
    const op: MoveTaskOp = { op: "move_task", id: before.id, start_date: toISODate(newStart) };
    return op;
  }
  if (!startChanged && endChanged) {
    const newEndInclusive = addDays(newEndExclusive, -1);
    const op: UpdateTaskOp = {
      op: "update_task",
      id: before.id,
      duration: Math.max(1, workdaysBetweenInclusive(oldStart, newEndInclusive)),
    };
    return op;
  }
  // Both start and end moved (e.g. the whole bar was dragged while also spanning a different
  // number of days) — the start the user dropped it on wins, mirroring a plain move.
  const op: MoveTaskOp = { op: "move_task", id: before.id, start_date: toISODate(newStart) };
  return op;
}

export function linkToOperation(source: number, target: number): AddDependencyOp {
  return { op: "add_dependency", predecessor_id: source, successor_id: target, lag: 0 };
}
