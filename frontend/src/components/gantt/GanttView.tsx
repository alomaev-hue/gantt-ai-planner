import { useCallback, useEffect, useMemo, useRef } from "react";
import { Gantt, Willow, type IApi } from "@svar-ui/react-gantt";
import "@svar-ui/react-gantt/all.css";
import "./gantt.css";
import { ZOOM_PRESETS, toSvarLinks, toSvarTasks, type Zoom } from "./mapping";
import { RuLocale } from "./locale";
import type { ScheduledPlan } from "@/api/types";
import { formatRu, addDays } from "@/lib/dates";

const TASK_TYPES = [
  { id: "task", label: "Задача" },
  { id: "critical", label: "Критическая" },
  { id: "changed", label: "Изменена" },
];

export function GanttView(props: {
  plan: ScheduledPlan;
  zoom: Zoom;
  highlighted: ReadonlySet<number>;
  readOnly: boolean;
  onOpenTask(id: number): void;
}) {
  // Handlers passed into `init` are captured once (the Gantt is only initialized once);
  // routing through a ref keeps them current without re-running `init`.
  const handlers = useRef(props);
  useEffect(() => {
    handlers.current = props;
  }, [props]);

  const tasks = useMemo(() => toSvarTasks(props.plan, props.highlighted), [props.plan, props.highlighted]);
  const links = useMemo(() => toSvarLinks(props.plan), [props.plan]);

  const columns = useMemo(
    () => [
      { id: "id", header: "№", width: 44, align: "center" as const },
      { id: "text", header: "Задача", flexgrow: 1 },
      { id: "assignee", header: "Исполнитель", width: 130 },
      { id: "workDays", header: "Дн.", width: 48, align: "center" as const },
      { id: "start", header: "Начало", width: 88, template: (d: Date) => formatRu(d) },
      { id: "end", header: "Окончание", width: 88, template: (d: Date) => formatRu(addDays(d, -1)) },
    ],
    [],
  );

  const init = useCallback((api: IApi) => {
    api.intercept("show-editor", () => false);
    api.on("select-task", ({ id }) => {
      if (id != null) handlers.current.onOpenTask(Number(id));
    });
    // Phase 2 wires drag/resize/link editing here; Phase 1 is read-only end to end.
    api.intercept("update-task", () => false);
    api.intercept("add-link", () => false);
    api.intercept("drag-task", () => false);
  }, []);

  return (
    <RuLocale>
      <Willow>
        <Gantt
          init={init}
          tasks={tasks}
          links={links}
          columns={columns}
          taskTypes={TASK_TYPES}
          readonly={props.readOnly}
          {...ZOOM_PRESETS[props.zoom]}
          highlightTime={(d: Date, unit: string) =>
            unit === "day" && d.toDateString() === new Date().toDateString() ? "gantt-today" : ""
          }
        />
      </Willow>
    </RuLocale>
  );
}
