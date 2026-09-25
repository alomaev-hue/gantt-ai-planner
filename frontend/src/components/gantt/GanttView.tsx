import { useCallback, useEffect, useMemo, useRef } from "react";
import { Gantt, Willow, type IApi } from "@svar-ui/react-gantt";
import "@svar-ui/react-gantt/all.css";
import "./gantt.css";
import { ZOOM_PRESETS, closestTaskId, toSvarLinks, toSvarTasks, type Zoom } from "./mapping";
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
    // `select-task` also fires on keyboard grid navigation, so opening the task modal from it
    // would pop the modal while the user is just arrowing through rows. Instead, a real pointer
    // click is handled by the container's own onClick below (via `closestTaskId`); double-click
    // still routes through `show-editor`, which we intercept to open our modal instead of
    // SVAR's built-in editor.
    api.intercept("show-editor", ({ id }: { id: number | string | null }) => {
      if (id != null) handlers.current.onOpenTask(Number(id));
      return false;
    });
    // Phase 2 wires drag/resize/link editing here; Phase 1 is read-only end to end.
    api.intercept("update-task", () => false);
    api.intercept("add-link", () => false);
    api.intercept("drag-task", () => false);
  }, []);

  return (
    <div
      className="h-full min-h-0"
      onClick={(e) => {
        const id = closestTaskId(e.target);
        if (id != null) handlers.current.onOpenTask(id);
      }}
    >
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
    </div>
  );
}
