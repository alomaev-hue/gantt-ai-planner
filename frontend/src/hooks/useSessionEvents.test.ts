import { parsePlanChanged } from "./useSessionEvents";

test("parses changed_task_ids from the plan_changed payload", () => {
  expect(parsePlanChanged(JSON.stringify({ type: "plan_changed", version: 3, changed_task_ids: [1, 2] }))).toEqual([
    1, 2,
  ]);
});

test("defaults to [] when changed_task_ids is missing", () => {
  expect(parsePlanChanged(JSON.stringify({ type: "plan_changed", version: 3 }))).toEqual([]);
});

test("defaults to [] on malformed JSON instead of throwing", () => {
  expect(parsePlanChanged("not json")).toEqual([]);
});

test("whole-plan replacements (import, reset) highlight nothing", () => {
  for (const source of ["import", "reset", "seed"]) {
    expect(parsePlanChanged(JSON.stringify({ type: "plan_changed", source, changed_task_ids: [1, 2] }))).toEqual([]);
  }
  expect(parsePlanChanged(JSON.stringify({ type: "plan_changed", source: "agent", changed_task_ids: [3] }))).toEqual([3]);
});
