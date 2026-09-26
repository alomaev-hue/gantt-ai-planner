import { render, screen } from "@testing-library/react";
import { GanttLegend } from "./GanttLegend";

test("every legend item explains itself on hover, and the project dates are shown", () => {
  render(<GanttLegend projectStart="2026-09-07" projectEnd="2026-11-17" />);
  for (const label of ["Обычная задача", "Критический путь", "Перегрузка", "Изменено", "Старт проекта"]) {
    expect(screen.getByText(label).closest("[title]")?.getAttribute("title")).toBeTruthy();
  }
  expect(screen.getByText("Критический путь").closest("[title]")?.getAttribute("title")).toMatch(/резерв 0/);
  expect(screen.getByText("Старт 07.09.2026 · Окончание 17.11.2026")).toBeInTheDocument();
});
