import { addDays, formatRu, nextMonday, parseISODate, toISODate, workdaysBetweenInclusive } from "./dates";

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

test("workdaysBetweenInclusive counts Mon-Fri only", () => {
  // Mon 21 .. Wed 23: 3 workdays.
  expect(workdaysBetweenInclusive(parseISODate("2026-09-21"), parseISODate("2026-09-23"))).toBe(3);
  // Mon 21 .. Mon 28: Mon-Fri (5) + weekend Sat 26/Sun 27 skipped + Mon 28 = 6.
  expect(workdaysBetweenInclusive(parseISODate("2026-09-21"), parseISODate("2026-09-28"))).toBe(6);
  // Sat 26 .. Sun 27: pure weekend, 0 workdays.
  expect(workdaysBetweenInclusive(parseISODate("2026-09-26"), parseISODate("2026-09-27"))).toBe(0);
  // Same day, a Monday: 1 workday.
  expect(workdaysBetweenInclusive(parseISODate("2026-09-21"), parseISODate("2026-09-21"))).toBe(1);
});
