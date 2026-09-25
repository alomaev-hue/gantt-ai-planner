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
// `clear_constraint` if it was removed. `[]` if the form matches the task exactly.
export function buildTaskOps(task: ScheduledTask, form: TaskForm): Operation[] {
  const ops: Operation[] = [];

  const name = form.name.trim();
  const description = form.description.trim();
  const assignee = form.assignee.trim();
  const currentName = task.name.trim();
  const currentDescription = task.description.trim();
  const currentAssignee = (task.assignee ?? "").trim();

  const update: UpdateTaskOp = { op: "update_task", id: task.id };
  let changed = false;
  if (name !== currentName) {
    update.name = name;
    changed = true;
  }
  if (description !== currentDescription) {
    update.description = description;
    changed = true;
  }
  if (assignee !== currentAssignee) {
    update.assignee = assignee;
    changed = true;
  }
  if (form.duration !== task.duration) {
    update.duration = form.duration;
    changed = true;
  }
  if (changed) ops.push(update);

  if (form.constraint !== task.constraint_start) {
    if (form.constraint) {
      const move: MoveTaskOp = { op: "move_task", id: task.id, start_date: form.constraint };
      ops.push(move);
    } else {
      ops.push({ op: "clear_constraint", id: task.id });
    }
  }

  return ops;
}

// Client-side validation shown inline in the task modal before a save is attempted.
export function validateTaskForm(form: TaskForm): string | null {
  const name = form.name.trim();
  if (name.length < 1 || name.length > 200) {
    return "Название должно быть от 1 до 200 символов";
  }
  if (!Number.isInteger(form.duration) || form.duration < 1 || form.duration > 999) {
    return "Длительность должна быть целым числом от 1 до 999 дней";
  }
  return null;
}
