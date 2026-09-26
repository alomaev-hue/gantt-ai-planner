import { render, screen } from "@testing-library/react";
import { ProjectDates } from "./ProjectDates";

test("shows the project start and end dates", () => {
  render(<ProjectDates start="2026-09-07" end="2026-11-25" />);
  expect(screen.getByText("Старт 07.09.2026 · Окончание 25.11.2026")).toBeInTheDocument();
});
