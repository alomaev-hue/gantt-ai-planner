import { fireEvent, render, screen } from "@testing-library/react";
import { DiffSummary } from "./DiffSummary";

test("expands and focuses task", () => {
  const onFocus = vi.fn();
  render(<DiffSummary summary="Изменено задач: 1" onFocusTask={onFocus}
    changes={[{ task_id: 5, task_name: "Дизайн", field: "start", before: "2026-09-21", after: "2026-09-23" }]} />);
  fireEvent.click(screen.getByText("Изменено задач: 1"));
  const line = screen.getByText(/начало 21\.09\.2026 → 23\.09\.2026/);
  fireEvent.click(line);
  expect(onFocus).toHaveBeenCalledWith(5);
});
