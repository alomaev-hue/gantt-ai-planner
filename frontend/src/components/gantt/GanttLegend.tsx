// Colors reuse the CSS custom properties gantt.css already defines for bar styling (`:root` /
// `.dark`), so the legend swatches always match what's actually painted on the bars.
const ITEMS = [
  { color: "var(--gantt-critical)", label: "Критический путь" },
  { color: "var(--gantt-conflict)", label: "Перегрузка" },
  { color: "var(--gantt-changed)", label: "Изменено" },
];

export function GanttLegend() {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-t border-border px-3 py-1.5 text-xs text-muted-foreground">
      {ITEMS.map((item) => (
        <span key={item.label} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: item.color }} aria-hidden="true" />
          {item.label}
        </span>
      ))}
    </div>
  );
}
