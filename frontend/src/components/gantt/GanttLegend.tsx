import { formatRu } from "@/lib/dates";

// Colors reuse the CSS custom properties gantt.css already defines for bar styling (`:root` /
// `.dark`), so the legend swatches always match what's actually painted on the bars.
const ITEMS = [
  { color: "var(--gantt-critical)", label: "Критический путь" },
  { color: "var(--gantt-conflict)", label: "Перегрузка" },
  { color: "var(--gantt-changed)", label: "Изменено" },
];

// The project's dates are spelled out here because nothing else on screen states where the
// schedule is counted from; the green swatch matches the start line drawn on the timeline.
export function GanttLegend({ projectStart, projectEnd }: { projectStart: string; projectEnd: string }) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-t border-border px-3 py-1.5 text-xs text-muted-foreground">
      {ITEMS.map((item) => (
        <span key={item.label} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: item.color }} aria-hidden="true" />
          {item.label}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5">
        <span className="h-3 w-0.5" style={{ background: "var(--gantt-start)" }} aria-hidden="true" />
        Старт проекта
      </span>
      <span className="ml-auto whitespace-nowrap">
        Старт {formatRu(projectStart)} · Окончание {formatRu(projectEnd)}
      </span>
    </div>
  );
}
