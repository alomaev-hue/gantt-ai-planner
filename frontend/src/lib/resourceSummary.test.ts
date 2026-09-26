import type { ScheduledPlan, ScheduledTask } from "@/api/types";
import { computeResourceSummary, ruPlural } from "./resourceSummary";

test("ruPlural picks the right Russian plural form, including the x11-x14 exception", () => {
  expect(ruPlural(1, "задача", "задачи", "задач")).toBe("задача");
  expect(ruPlural(2, "задача", "задачи", "задач")).toBe("задачи");
  expect(ruPlural(5, "задача", "задачи", "задач")).toBe("задач");
  expect(ruPlural(11, "задача", "задачи", "задач")).toBe("задач");
  expect(ruPlural(21, "задача", "задачи", "задач")).toBe("задача");
});

function task(overrides: Partial<ScheduledTask>): ScheduledTask {
  return {
    id: 1,
    name: "Задача",
    description: "",
    assignee: null,
    duration: 1,
    constraint_start: null,
    start: "2026-09-21",
    end: "2026-09-21",
    slack: 0,
    is_critical: false,
    constrained_by: "project_start",
    overallocated_with: [],
    ...overrides,
  };
}

function plan(tasks: ScheduledTask[]): ScheduledPlan {
  return {
    project_start: "2026-09-21",
    project_end: "2026-09-30",
    last_id: tasks.length,
    tasks,
    dependencies: [],
    critical_path: [],
  };
}

test("groups tasks by assignee and sums workdays", () => {
  const summary = computeResourceSummary(
    plan([
      task({ id: 1, assignee: "Олег", duration: 2, start: "2026-09-21", end: "2026-09-22" }),
      task({ id: 2, assignee: "Олег", duration: 3, start: "2026-09-23", end: "2026-09-25" }),
      task({ id: 3, assignee: "Ирина", duration: 1, start: "2026-09-21", end: "2026-09-21" }),
    ]),
  );
  expect(summary.map((s) => s.assignee)).toEqual(["Ирина", "Олег"]);
  const oleg = summary.find((s) => s.assignee === "Олег")!;
  expect(oleg.taskCount).toBe(2);
  expect(oleg.workdays).toBe(5);
  expect(oleg.spanStart).toBe("2026-09-21");
  expect(oleg.spanEnd).toBe("2026-09-25");
});

test("groups tasks without an assignee under null, sorted last", () => {
  const summary = computeResourceSummary(
    plan([task({ id: 1, assignee: null }), task({ id: 2, assignee: "Аня" })]),
  );
  expect(summary.map((s) => s.assignee)).toEqual(["Аня", null]);
  expect(summary.find((s) => s.assignee === null)?.taskCount).toBe(1);
});

test("treats a blank-string assignee the same as no assignee", () => {
  const summary = computeResourceSummary(plan([task({ id: 1, assignee: "  " })]));
  expect(summary).toEqual([expect.objectContaining({ assignee: null, taskCount: 1 })]);
});

test("derives conflict pairs from overallocated_with, deduped and only within the group", () => {
  const summary = computeResourceSummary(
    plan([
      task({ id: 1, assignee: "Олег", overallocated_with: [2] }),
      task({ id: 2, assignee: "Олег", overallocated_with: [1] }),
      task({ id: 3, assignee: "Олег" }),
    ]),
  );
  const oleg = summary.find((s) => s.assignee === "Олег")!;
  expect(oleg.conflicts).toEqual([{ a: 1, b: 2 }]);
});

test("returns no groups for an empty plan", () => {
  expect(computeResourceSummary(plan([]))).toEqual([]);
});
