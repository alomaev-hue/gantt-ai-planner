import { buildTaskOps, formFromTask, needsRebase, rebaseForm, validateTaskForm, type TaskForm } from "./taskOps";
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

test("validateTaskForm rejects too long description", () => {
  const base = formFromTask(task);
  expect(validateTaskForm({ ...base, description: "a".repeat(2001) })).not.toBeNull();
  expect(validateTaskForm({ ...base, description: "a".repeat(2000) })).toBeNull();
});

test("validateTaskForm rejects too long assignee", () => {
  const base = formFromTask(task);
  expect(validateTaskForm({ ...base, assignee: "a".repeat(101) })).not.toBeNull();
  expect(validateTaskForm({ ...base, assignee: "a".repeat(100) })).toBeNull();
});

test("buildTaskOps diffs against baseline, not the live task, once a baseline is given", () => {
  // The server (agent) changed duration 4 -> 5 server-side; the user is mid-edit of `name` only.
  // Diffing directly against `task` (already updated to duration 5) would hide the fact that the
  // *form* still shows the old duration 4 as unedited — but here baseline still says 4, so no
  // spurious duration op appears, only the name edit the user actually made.
  const serverUpdated: ScheduledTask = { ...task, duration: 5 };
  const baseline = { ...formFromTask(task), duration: 5 }; // rebased alongside the server change
  const form = { ...baseline, name: "Дизайн v2" };
  expect(buildTaskOps(serverUpdated, form, baseline)).toEqual([{ op: "update_task", id: 7, name: "Дизайн v2" }]);
});

test("rebaseForm pulls fresh server values into untouched fields, leaves edited fields alone", () => {
  const baseline = formFromTask(task);
  const form = { ...baseline, name: "Дизайн v2" }; // user is editing name only
  const fresh = { ...baseline, assignee: "Игорь", duration: 6 }; // server changed elsewhere

  const result = rebaseForm(form, baseline, fresh);

  expect(result.form).toEqual({ ...fresh, name: "Дизайн v2" });
  expect(result.baseline).toEqual({ ...fresh, name: baseline.name });
});

test("rebaseForm is a no-op when the fresh values match the baseline", () => {
  const baseline = formFromTask(task);
  const form = { ...baseline, name: "Дизайн v2" };
  const result = rebaseForm(form, baseline, baseline);
  expect(result.form).toEqual(form);
  expect(result.baseline).toEqual(baseline);
});

const base: TaskForm = { name: "A", description: "", assignee: "", duration: 3, constraint: null };

test("needsRebase is true when an untouched field changed server-side", () => {
  const form = { ...base, name: "A edited" };
  expect(needsRebase(form, base, { ...base, duration: 5 })).toBe(true);
});

test("needsRebase is false when only a field the user is editing changed server-side", () => {
  // rebaseForm would leave `name` alone in both form and baseline, so reporting this as stale
  // would re-trigger the render-time setState forever ("Too many re-renders").
  const form = { ...base, name: "A edited" };
  const fresh = { ...base, name: "A renamed elsewhere" };
  expect(needsRebase(form, base, fresh)).toBe(false);
  const rebased = rebaseForm(form, base, fresh);
  expect(needsRebase(rebased.form, rebased.baseline, fresh)).toBe(false);
});

test("needsRebase is false when the server snapshot matches the baseline", () => {
  expect(needsRebase({ ...base, name: "x" }, base, { ...base })).toBe(false);
});

test("after a rebase the fresh snapshot no longer needs one", () => {
  const form = { ...base, name: "A edited" };
  const fresh = { ...base, duration: 5, name: "A renamed elsewhere" };
  const rebased = rebaseForm(form, base, fresh);
  expect(rebased.form).toEqual({ ...base, name: "A edited", duration: 5 });
  expect(needsRebase(rebased.form, rebased.baseline, fresh)).toBe(false);
});
