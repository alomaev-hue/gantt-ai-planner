import { buildTaskOps, formFromTask, validateTaskForm } from "./taskOps";
import type { ScheduledTask } from "@/api/types";

const task: ScheduledTask = {
  id: 7, name: "Дизайн", description: "", assignee: "Мария", duration: 4, constraint_start: null,
  start: "2026-09-21", end: "2026-09-24", slack: 0, is_critical: true, constrained_by: "project_start", overallocated_with: [],
};

test("no changes → no ops", () => {
  expect(buildTaskOps(task, formFromTask(task))).toEqual([]);
});

test("changed fields and new constraint", () => {
  const form = { ...formFromTask(task), assignee: "", duration: 6, constraint: "2026-10-05" };
  expect(buildTaskOps(task, form)).toEqual([
    { op: "update_task", id: 7, assignee: "", duration: 6 },
    { op: "move_task", id: 7, start_date: "2026-10-05" },
  ]);
});

test("removing constraint", () => {
  const constrained = { ...task, constraint_start: "2026-10-05" };
  expect(buildTaskOps(constrained, { ...formFromTask(constrained), constraint: null }))
    .toEqual([{ op: "clear_constraint", id: 7 }]);
});

test("trims whitespace before comparing", () => {
  const form = { ...formFromTask(task), name: `${task.name}  ` };
  expect(buildTaskOps(task, form)).toEqual([]);
});

test("validateTaskForm rejects empty or too long name", () => {
  const base = formFromTask(task);
  expect(validateTaskForm({ ...base, name: "" })).not.toBeNull();
  expect(validateTaskForm({ ...base, name: "a".repeat(201) })).not.toBeNull();
  expect(validateTaskForm(base)).toBeNull();
});

test("validateTaskForm rejects out-of-range duration", () => {
  const base = formFromTask(task);
  expect(validateTaskForm({ ...base, duration: 0 })).not.toBeNull();
  expect(validateTaskForm({ ...base, duration: 1000 })).not.toBeNull();
  expect(validateTaskForm({ ...base, duration: 999 })).toBeNull();
});
