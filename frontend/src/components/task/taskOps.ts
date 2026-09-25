import type { MoveTaskOp, Operation, ScheduledTask, UpdateTaskOp } from "@/api/types";

export interface TaskForm {
  name: string;
  description: string;
  assignee: string;
  duration: number;
  constraint: string | null;
}

export function formFromTask(task: ScheduledTask): TaskForm {
  return {
    name: task.name,
    description: task.description,
    assignee: task.assignee ?? "",
    duration: task.duration,
    constraint: task.constraint_start,
  };
}

// One `update_task` op with only the fields that actually changed (assignee "" when cleared),
// plus a `move_task {start_date}` if a "не раньше" constraint was set/changed, or
// `clear_constraint` if it was removed. `[]` if the form matches `baseline` exactly.
//
// Diffing against `baseline` (not the live `task`) rather than `task` directly matters once the
// modal can stay open across a server-side refetch of the same task (agent edit, another tab):
// `baseline` only moves forward for fields the user hasn't touched (see `rebaseForm`), so a
// field the agent changed elsewhere while the user is mid-edit of some *other* field doesn't
// show up as a spurious local diff that Save would silently revert. `task.id` (and any op that
// only needs the id) still comes from the live `task`. `baseline` defaults to `formFromTask(task)`
// so existing 2-arg callers keep diffing directly against the task, unchanged.
export function buildTaskOps(
  task: ScheduledTask,
  form: TaskForm,
  baseline: TaskForm = formFromTask(task),
): Operation[] {
  const ops: Operation[] = [];

  const name = form.name.trim();
  const description = form.description.trim();
  const assignee = form.assignee.trim();
  const baseName = baseline.name.trim();
  const baseDescription = baseline.description.trim();
  const baseAssignee = baseline.assignee.trim();

  const update: UpdateTaskOp = { op: "update_task", id: task.id };
  let changed = false;
  if (name !== baseName) {
    update.name = name;
    changed = true;
  }
  if (description !== baseDescription) {
    update.description = description;
    changed = true;
  }
  if (assignee !== baseAssignee) {
    update.assignee = assignee;
    changed = true;
  }
  if (form.duration !== baseline.duration) {
    update.duration = form.duration;
    changed = true;
  }
  if (changed) ops.push(update);

  if (form.constraint !== baseline.constraint) {
    if (form.constraint) {
      const move: MoveTaskOp = { op: "move_task", id: task.id, start_date: form.constraint };
      ops.push(move);
    } else {
      ops.push({ op: "clear_constraint", id: task.id });
    }
  }

  return ops;
}

// Carries a `baseline` (the form fields as last known from the server) forward when the same
// task refetches with new values: any field the user hasn't edited yet (`form[field] ===
// baseline[field]`) picks up the fresh server value in both `form` and `baseline`; a field the
// user has already started editing (`form[field] !== baseline[field]`) is left alone in both —
// the user's in-progress edit stays, and `baseline` keeps the *pre-edit* value so `buildTaskOps`
// still reports that field as changed.
export function rebaseForm(
  form: TaskForm,
  baseline: TaskForm,
  fresh: TaskForm,
): { form: TaskForm; baseline: TaskForm } {
  const nextForm = { ...form };
  const nextBaseline = { ...baseline };

  if (form.name === baseline.name) {
    nextForm.name = fresh.name;
    nextBaseline.name = fresh.name;
  }
  if (form.description === baseline.description) {
    nextForm.description = fresh.description;
    nextBaseline.description = fresh.description;
  }
  if (form.assignee === baseline.assignee) {
    nextForm.assignee = fresh.assignee;
    nextBaseline.assignee = fresh.assignee;
  }
  if (form.duration === baseline.duration) {
    nextForm.duration = fresh.duration;
    nextBaseline.duration = fresh.duration;
  }
  if (form.constraint === baseline.constraint) {
    nextForm.constraint = fresh.constraint;
    nextBaseline.constraint = fresh.constraint;
  }

  return { form: nextForm, baseline: nextBaseline };
}

// Client-side validation shown inline in the task modal before a save is attempted.
export function validateTaskForm(form: TaskForm): string | null {
  const name = form.name.trim();
  if (name.length < 1 || name.length > 200) {
    return "Название должно быть от 1 до 200 символов";
  }
  if (form.description.trim().length > 2000) {
    return "Описание не должно превышать 2000 символов";
  }
  if (form.assignee.trim().length > 100) {
    return "Имя исполнителя не должно превышать 100 символов";
  }
  if (!Number.isInteger(form.duration) || form.duration < 1 || form.duration > 999) {
    return "Длительность должна быть целым числом от 1 до 999 дней";
  }
  return null;
}
