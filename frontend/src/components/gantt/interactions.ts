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
// Returns the operations for one batch (empty when nothing changed).
export function interpretBarChange(before: ScheduledTask, newStart: Date, newEndExclusive: Date): Operation[] {
  const oldStart = parseISODate(before.start);
  const oldEndExclusive = addDays(parseISODate(before.end), 1);

  const startChanged = !sameDate(oldStart, newStart);
  const endChanged = !sameDate(oldEndExclusive, newEndExclusive);
  if (!startChanged && !endChanged) return [];

  const oldLengthDays = daysBetween(oldStart, oldEndExclusive);
  const newLengthDays = daysBetween(newStart, newEndExclusive);
  const move: MoveTaskOp = { op: "move_task", id: before.id, start_date: toISODate(newStart) };
  const durationUntil = (start: Date): UpdateTaskOp => ({
    op: "update_task",
    id: before.id,
    duration: Math.max(1, workdaysBetweenInclusive(start, addDays(newEndExclusive, -1))),
  });

  if (oldLengthDays === newLengthDays) return [move];
  // Right edge dragged: same start, new length.
  if (!startChanged) return [durationUntil(oldStart)];
  // Left edge dragged: new start, same end — both the start constraint and the length change.
  if (!endChanged) return [move, durationUntil(newStart)];
  // Both start and end moved by different amounts (not a plain drag or edge resize) — the start
  // the user dropped it on wins, mirroring a plain move.
  return [move];
}

export function linkToOperation(source: number, target: number): AddDependencyOp {
  return { op: "add_dependency", predecessor_id: source, successor_id: target, lag: 0 };
}
