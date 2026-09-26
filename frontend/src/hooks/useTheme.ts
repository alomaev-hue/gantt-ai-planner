import { useCallback, useEffect, useState } from "react";

export type ThemeMode = "light" | "dark" | "system";

const STORAGE_KEY = "theme";
const MODES: readonly ThemeMode[] = ["light", "dark", "system"];

// localStorage can throw (private browsing, blocked site data, disabled storage) — every access
// is wrapped so a theme preference is a nice-to-have, never a crash (spec: "persisted in
// localStorage with try/catch").
export function readStoredTheme(): ThemeMode | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return (MODES as string[]).includes(value ?? "") ? (value as ThemeMode) : null;
  } catch {
    return null;
  }
}

export function writeStoredTheme(mode: ThemeMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* best effort */
  }
}

// Pure so the light/dark/system tri-state logic is unit-testable without touching the DOM.
export function resolveIsDark(mode: ThemeMode, prefersDark: boolean): boolean {
  return mode === "system" ? prefersDark : mode === "dark";
}

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)").matches
    : false;
}

export function useTheme(): { theme: ThemeMode; isDark: boolean; setTheme: (mode: ThemeMode) => void } {
  const [theme, setThemeState] = useState<ThemeMode>(() => readStoredTheme() ?? "system");
  const [prefersDark, setPrefersDark] = useState(systemPrefersDark);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setPrefersDark(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  const isDark = resolveIsDark(theme, prefersDark);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  const setTheme = useCallback((mode: ThemeMode) => {
    setThemeState(mode);
    writeStoredTheme(mode);
  }, []);

  return { theme, isDark, setTheme };
}
