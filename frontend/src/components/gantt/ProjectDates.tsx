import { formatRu } from "@/lib/dates";

// A centered caption right above the chart: where the schedule is counted from (the green line
// on the timeline) and where it ends. Lives in the chart pane, not the full-width toolbar, so it
// stays centered over the chart when the chart/chat divider is dragged.
export function ProjectDates({ start, end }: { start: string; end: string }) {
  return (
    <div
      title="Старт — дата, от которой считается план (зелёная линия на диаграмме); окончание — конец последней задачи"
      className="shrink-0 border-b border-border px-3 py-1.5 text-center text-sm font-semibold"
    >
      Старт {formatRu(start)} · Окончание {formatRu(end)}
    </div>
  );
}
