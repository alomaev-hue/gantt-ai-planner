import { fireEvent, render, screen } from "@testing-library/react";
import type { ScheduledPlan, ScheduledTask } from "@/api/types";
import { ResourcePanel } from "./ResourcePanel";

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

const plan: ScheduledPlan = {
  project_start: "2026-09-21",
  project_end: "2026-09-30",
  last_id: 2,
  dependencies: [],
  critical_path: [],
  tasks: [
    task({ id: 1, assignee: "Олег", overallocated_with: [2] }),
    task({ id: 2, assignee: "Олег", overallocated_with: [1] }),
  ],
};

test("is collapsed by default and expands to show per-assignee load", () => {
  render(<ResourcePanel plan={plan} onOpenTask={vi.fn()} />);
  expect(screen.queryByText(/задачи/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Загрузка"));
  expect(screen.getByText("Олег")).toBeInTheDocument();
  expect(screen.getByText(/2 задачи/)).toBeInTheDocument();
});

test("clicking a conflicting task id opens it", () => {
  const onOpenTask = vi.fn();
  render(<ResourcePanel plan={plan} onOpenTask={onOpenTask} />);
  fireEvent.click(screen.getByText("Загрузка"));
  fireEvent.click(screen.getByText("№1"));
  expect(onOpenTask).toHaveBeenCalledWith(1);
});
