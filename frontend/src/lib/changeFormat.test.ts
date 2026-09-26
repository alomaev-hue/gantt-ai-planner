import { describeChange, formatChangeValue } from "./changeFormat";

test("describes a plain field change with ru date formatting", () => {
  expect(
    describeChange({ task_id: 5, task_name: "Дизайн", field: "start", before: "2026-09-21", after: "2026-09-23" }),
  ).toBe("начало 21.09.2026 → 23.09.2026");
});

test("describes created/deleted without before/after arrow", () => {
  expect(describeChange({ task_id: 1, task_name: "X", field: "created" })).toBe("добавлена");
  expect(describeChange({ task_id: 1, task_name: "X", field: "deleted" })).toBe("удалена");
});

test("formats missing values as a dash", () => {
  expect(formatChangeValue("assignee", null)).toBe("—");
  expect(formatChangeValue("assignee", undefined)).toBe("—");
  expect(formatChangeValue("assignee", "")).toBe("—");
});

test("passes non-date values through as strings", () => {
  expect(formatChangeValue("duration", 6)).toBe("6");
  expect(formatChangeValue("assignee", "Олег")).toBe("Олег");
});
