import { addDays, formatRu, nextMonday, parseISODate, toISODate } from "./dates";

test("parse/format keep local calendar date", () => {
  const d = parseISODate("2026-09-21");
  expect(d.getFullYear()).toBe(2026);
  expect(d.getMonth()).toBe(8);
  expect(d.getDate()).toBe(21);
  expect(toISODate(d)).toBe("2026-09-21");
  expect(formatRu("2026-09-21")).toBe("21.09.2026");
  expect(toISODate(addDays(d, 11))).toBe("2026-10-02");
});

test("nextMonday", () => {
  expect(toISODate(nextMonday(parseISODate("2026-09-21")))).toBe("2026-09-21"); // Monday
  expect(toISODate(nextMonday(parseISODate("2026-09-25")))).toBe("2026-09-28"); // Friday
  expect(toISODate(nextMonday(parseISODate("2026-09-27")))).toBe("2026-09-28"); // Sunday
});
