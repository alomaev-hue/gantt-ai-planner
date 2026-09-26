import { render, screen } from "@testing-library/react";
import { GanttLegend } from "./GanttLegend";

test("every legend item explains itself on hover", () => {
  render(<GanttLegend />);
  for (const label of ["Обычная задача", "Критический путь", "Перегрузка", "Изменено", "Старт проекта"]) {
    expect(screen.getByText(label).closest("[title]")?.getAttribute("title")).toBeTruthy();
  }
  expect(screen.getByText("Критический путь").closest("[title]")?.getAttribute("title")).toMatch(/резерв 0/);
});
