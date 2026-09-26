import { readStoredTheme, resolveIsDark, writeStoredTheme } from "./useTheme";

afterEach(() => vi.restoreAllMocks());

test("resolveIsDark: system follows the OS preference, light/dark are fixed", () => {
  expect(resolveIsDark("system", true)).toBe(true);
  expect(resolveIsDark("system", false)).toBe(false);
  expect(resolveIsDark("light", true)).toBe(false);
  expect(resolveIsDark("dark", false)).toBe(true);
});

test("readStoredTheme returns a valid stored mode", () => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue("dark");
  expect(readStoredTheme()).toBe("dark");
});

test("readStoredTheme ignores garbage and returns null", () => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue("neon");
  expect(readStoredTheme()).toBeNull();
});

test("readStoredTheme swallows a throwing localStorage", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(readStoredTheme()).toBeNull();
});

test("writeStoredTheme swallows a throwing localStorage", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(() => writeStoredTheme("dark")).not.toThrow();
});
