import { interpretBarChange, linkToOperation, linkDeletionToOperation } from "./interactions";
import { parseISODate } from "@/lib/dates";
import type { ScheduledTask } from "@/api/types";

const t: ScheduledTask = { id: 3, name: "X", description: "", assignee: null, duration: 3, constraint_start: null,
  start: "2026-09-21", end: "2026-09-23", slack: 0, is_critical: false, constrained_by: "project_start", overallocated_with: [] };

test("drag keeps length → move_task", () => {
  expect(interpretBarChange(t, parseISODate("2026-09-28"), parseISODate("2026-10-01")))
    .toEqual([{ op: "move_task", id: 3, start_date: "2026-09-28" }]);
});
test("resize end → duration in workdays", () => {
  expect(interpretBarChange(t, parseISODate("2026-09-21"), parseISODate("2026-09-29")))
    .toEqual([{ op: "update_task", id: 3, duration: 6 }]); // Mon 21 .. Mon 28 inclusive = 6 workdays
});
test("resize left edge outwards → new start and a longer duration, end stays", () => {
  // Thu 17 .. Wed 23 inclusive = 5 workdays
  expect(interpretBarChange(t, parseISODate("2026-09-17"), parseISODate("2026-09-24"))).toEqual([
    { op: "move_task", id: 3, start_date: "2026-09-17" },
    { op: "update_task", id: 3, duration: 5 },
  ]);
});
test("resize left edge inwards → later start and a shorter duration, end stays", () => {
  expect(interpretBarChange(t, parseISODate("2026-09-22"), parseISODate("2026-09-24"))).toEqual([
    { op: "move_task", id: 3, start_date: "2026-09-22" },
    { op: "update_task", id: 3, duration: 2 },
  ]);
});
test("no change → no operations", () => {
  expect(interpretBarChange(t, parseISODate("2026-09-21"), parseISODate("2026-09-24"))).toEqual([]);
});
test("link → add_dependency", () => {
  expect(linkToOperation(1, 3)).toEqual({ op: "add_dependency", predecessor_id: 1, successor_id: 3, lag: 0 });
});

test("deleting a chart link → remove_dependency for that link's pair", () => {
  // SVAR link ids are 1-based positions in plan.dependencies (see toSvarLinks).
  const deps = [
    { predecessor_id: 1, successor_id: 3, lag: 0 },
    { predecessor_id: 2, successor_id: 4, lag: 1 },
  ];
  expect(linkDeletionToOperation(deps, 2)).toEqual({ op: "remove_dependency", predecessor_id: 2, successor_id: 4 });
  expect(linkDeletionToOperation(deps, "1")).toEqual({ op: "remove_dependency", predecessor_id: 1, successor_id: 3 });
  expect(linkDeletionToOperation(deps, 3)).toBeNull();
});
