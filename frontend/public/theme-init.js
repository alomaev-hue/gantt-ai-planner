// Runs before the app bundle (plain <script src>, not inline — production CSP is
// `default-src 'self'`, which blocks inline scripts) so the correct theme class is on <html>
// before first paint, avoiding a light->dark flash. Mirrors useTheme's own resolution logic
// (src/hooks/useTheme.ts): stored "light"/"dark" wins, "system" or nothing falls back to
// prefers-color-scheme. useTheme remains the source of truth once React mounts — it re-applies
// (or removes) the same class from its own effect regardless of what this script did.
(function () {
  try {
    var mode = null;
    try {
      mode = localStorage.getItem("theme");
    } catch {
      mode = null;
    }
    var isDark;
    if (mode === "dark") {
      isDark = true;
    } else if (mode === "light") {
      isDark = false;
    } else {
      var mql = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");
      isDark = !!(mql && mql.matches);
    }
    if (isDark) document.documentElement.classList.add("dark");
  } catch {
    // A theme guess is never worth blocking rendering over.
  }
})();
