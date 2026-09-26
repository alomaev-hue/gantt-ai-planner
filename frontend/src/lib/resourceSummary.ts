// Pure computation behind ResourcePanel's «Загрузка» panel: per-assignee load, derived entirely
// client-side from the already-scheduled plan (no extra request). Tasks with no assignee are
// grouped under `assignee: null` ("Без исполнителя" is the presentation's job, not this module's).
import type { ScheduledPlan, ScheduledTask } from "@/api/types";

export interface ResourceConflict {
  a: number;
  b: number;
}

export interface ResourceSummary {
  assignee: string | null;
  taskCount: number;
  workdays: number;
  spanStart: string | null;
  spanEnd: string | null;
  conflicts: ResourceConflict[];
}

function conflictPairs(tasks: ScheduledTask[]): ResourceConflict[] {
  const ids = new Set(tasks.map((t) => t.id));
  const seen = new Set<string>();
  const pairs: ResourceConflict[] = [];
  for (const task of tasks) {
    for (const otherId of task.overallocated_with) {
      if (!ids.has(otherId)) continue; // only pairs within this assignee's own tasks
      const [a, b] = task.id < otherId ? [task.id, otherId] : [otherId, task.id];
      const key = `${a}-${b}`;
      if (seen.has(key)) continue;
      seen.add(key);
      pairs.push({ a, b });
    }
  }
  return pairs.sort((x, y) => x.a - y.a || x.b - y.b);
}

// Russian plural forms for a count noun ("1 задача", "2 задачи", "5 задач", "11 задач" — the
// x11-x14 exception is the part that's easy to get wrong by hand).
export function ruPlural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}

export function computeResourceSummary(plan: ScheduledPlan): ResourceSummary[] {
  // Grouped the way the backend scheduler groups for overallocation (trimmed, case-folded), so
  // «Иван Петров» and «иван петров» are one row whose conflict pairs are within its own tasks
  // rather than two rows that each drop the other's ids. The first spelling seen is displayed.
  const groups = new Map<string | null, { assignee: string | null; tasks: ScheduledTask[] }>();
  for (const task of plan.tasks) {
    const display = task.assignee?.trim() || null;
    const key = display === null ? null : display.toLocaleLowerCase("ru");
    const group = groups.get(key);
    if (group) group.tasks.push(task);
    else groups.set(key, { assignee: display, tasks: [task] });
  }

  const summaries: ResourceSummary[] = [];
  for (const { assignee, tasks } of groups.values()) {
    const starts = tasks.map((t) => t.start).sort();
    const ends = tasks.map((t) => t.end).sort();
    summaries.push({
      assignee,
      taskCount: tasks.length,
      workdays: tasks.reduce((sum, t) => sum + t.duration, 0),
      spanStart: starts[0] ?? null,
      spanEnd: ends[ends.length - 1] ?? null,
      conflicts: conflictPairs(tasks),
    });
  }

  return summaries.sort((a, b) => {
    if (a.assignee == null) return 1;
    if (b.assignee == null) return -1;
    return a.assignee.localeCompare(b.assignee, "ru");
  });
}
