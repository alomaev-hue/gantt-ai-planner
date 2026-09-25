import { closestTaskId, toSvarLinks, toSvarTasks } from "./mapping";
import type { ScheduledPlan } from "@/api/types";

const plan: ScheduledPlan = {
  project_start: "2026-09-21", project_end: "2026-09-25", last_id: 2, critical_path: [1],
  tasks: [
    { id: 1, name: "A", description: "", assignee: "Анна", duration: 3, constraint_start: null,
      start: "2026-09-21", end: "2026-09-23", slack: 0, is_critical: true, constrained_by: "project_start", overallocated_with: [] },
    { id: 2, name: "B", description: "", assignee: null, duration: 1, constraint_start: null,
      start: "2026-09-24", end: "2026-09-24", slack: 1, is_critical: false, constrained_by: "predecessor:1", overallocated_with: [] },
  ],
  dependencies: [{ predecessor_id: 1, successor_id: 2, lag: 0 }],
};

test("tasks map with exclusive end and types", () => {
  const [a, b] = toSvarTasks(plan, new Set([2]));
  expect(a.text).toBe("A");
  expect(a.start.getDate()).toBe(21);
  expect(a.end.getDate()).toBe(24); // inclusive 23 + 1
  expect(a.type).toBe("critical");
  expect(b.type).toBe("changed");
});

test("links are finish-to-start", () => {
  expect(toSvarLinks(plan)).toEqual([{ id: 1, source: 1, target: 2, type: "e2s" }]);
});

test("closestTaskId reads data-id off the clicked element or an ancestor", () => {
  const row = document.createElement("div");
  row.setAttribute("data-id", "7");
  const label = document.createElement("span");
  row.appendChild(label);
  expect(closestTaskId(label)).toBe(7);
  expect(closestTaskId(row)).toBe(7);
});

test("closestTaskId returns null without a data-id ancestor or a non-element target", () => {
  const outside = document.createElement("span");
  expect(closestTaskId(outside)).toBeNull();
  expect(closestTaskId(null)).toBeNull();
});

test("closestTaskId ignores a click on a link connector so link-drawing isn't interrupted", () => {
  const row = document.createElement("div");
  row.setAttribute("data-id", "7");
  const dot = document.createElement("div");
  dot.className = "wx-link wx-right wx-target";
  row.appendChild(dot);
  expect(closestTaskId(dot)).toBeNull();
});
