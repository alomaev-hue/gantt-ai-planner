import { act, renderHook } from "@testing-library/react";
import { HIGHLIGHT_MS, useFlashHighlight } from "./useFlashHighlight";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test("highlighted ids clear after HIGHLIGHT_MS", () => {
  const { result } = renderHook(() => useFlashHighlight());
  act(() => result.current[1]([1, 2]));
  expect([...result.current[0]]).toEqual([1, 2]);
  act(() => vi.advanceTimersByTime(HIGHLIGHT_MS - 1));
  expect(result.current[0].size).toBe(2);
  act(() => vi.advanceTimersByTime(1));
  expect(result.current[0].size).toBe(0);
});

test("a new highlight replaces the old one and restarts the timer", () => {
  const { result } = renderHook(() => useFlashHighlight());
  act(() => result.current[1]([1]));
  act(() => vi.advanceTimersByTime(1500));
  act(() => result.current[1]([2]));
  act(() => vi.advanceTimersByTime(1500));
  expect([...result.current[0]]).toEqual([2]);
  act(() => vi.advanceTimersByTime(HIGHLIGHT_MS - 1500));
  expect(result.current[0].size).toBe(0);
});

test("an empty highlight clears immediately", () => {
  const { result } = renderHook(() => useFlashHighlight());
  act(() => result.current[1]([1]));
  act(() => result.current[1]([]));
  expect(result.current[0].size).toBe(0);
});

test("HIGHLIGHT_MS matches the spec's 2 s", () => {
  expect(HIGHLIGHT_MS).toBe(2000);
});
