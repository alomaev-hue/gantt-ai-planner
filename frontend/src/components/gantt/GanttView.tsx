import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Gantt, Willow, type IApi } from "@svar-ui/react-gantt";
import "@svar-ui/react-gantt/all.css";
import "./gantt.css";
import { toast } from "sonner";
import { ZOOM_PRESETS, closestTaskId, toSvarLinks, toSvarTasks, type Zoom } from "./mapping";
import { interpretBarChange, linkToOperation } from "./interactions";
import { RuLocale } from "./locale";
import type { Operation, ScheduledPlan } from "@/api/types";
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
  onApply(ops: Operation[]): Promise<void>;
}) {
  // Handlers passed into `init` are captured once (the Gantt is only initialized once);
  // routing through a ref keeps them current without re-running `init`.
  const handlers = useRef(props);
  useEffect(() => {
    handlers.current = props;
  }, [props]);

  // SVAR applies a drag/resize/link optimistically to its own internal store the instant it
  // happens (before `onApply` below even starts its request) so the bar/arrow already looks
  // moved. When the backend rejects the change, `props.plan` is deliberately left untouched (no
  // refetch), so `tasks`/`links` would keep returning the very same array *references* on
  // re-render and SVAR would never re-sync from them. Bumping `revision` forces new references
  // out of the unchanged plan, which is what makes the Gantt re-init from last-known-good data
  // and the bar/link actually snap back.
  const [revision, setRevision] = useState(0);
  const snapBack = useCallback(() => setRevision((r) => r + 1), []);

  const tasks = useMemo(() => {
    void revision; // not read, but forces a fresh array after a rejected edit (see above)
    return toSvarTasks(props.plan, props.highlighted);
  }, [props.plan, props.highlighted, revision]);
  const links = useMemo(() => {
    void revision;
    return toSvarLinks(props.plan);
  }, [props.plan, revision]);

  // SVAR's own `gridWidth` default (`getDefaultGridWidth`, @svar-ui/gantt-store) sums the
  // *default* column set's widths, not ours — since we never pass `gridWidth` explicitly, a
  // flexgrow-only "text" column was left with only a few leftover pixels (observed ~42px,
  // truncating every task name to nothing useful). Giving it an explicit base `width` (still
  // with `flexgrow` so it grows into any extra space) and passing `gridWidth` computed from our
  // own columns fixes both the baseline and the total.
  const TEXT_COLUMN_WIDTH = 220;
  const columns = useMemo(
    () => [
      { id: "id", header: "№", width: 44, align: "center" as const },
      { id: "text", header: "Задача", width: TEXT_COLUMN_WIDTH, flexgrow: 1 },
      { id: "assignee", header: "Исполнитель", width: 130 },
      { id: "workDays", header: "Дн.", width: 48, align: "center" as const },
      { id: "start", header: "Начало", width: 88, template: (d: Date) => formatRu(d) },
      { id: "end", header: "Окончание", width: 88, template: (d: Date) => formatRu(addDays(d, -1)) },
    ],
    [],
  );
  const gridWidth = useMemo(() => columns.reduce((sum, c) => sum + c.width, 0), [columns]);

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

    // A bar drag or resize is committed as an `update-task` event carrying either `diff` (the
    // number of cells the bar moved/grew by, set by a move/resize commit) or `inProgress` (set
    // while a progress-marker drag is live) — see @svar-ui/gantt-store's DataStore.d.ts
    // (`IDataMethodsConfig["update-task"]`) and the bar-drag handlers in
    // @svar-ui/react-gantt's compiled source. Anything else (a plain field edit from our own
    // task modal, an agent-applied change, etc.) has neither and is left alone here — SVAR
    // already applied it to its own store by the time this fires. By the same point, `ev.task`
    // is the *resolved* task (real `start`/`end` Date objects, not raw pixel deltas), so we don't
    // need to reimplement SVAR's own cell-to-date math.
    api.on(
      "update-task",
      (ev: { id: number | string; task: { start?: Date; end?: Date }; diff?: number; inProgress?: boolean }) => {
        if (handlers.current.readOnly) return;
        if (ev.diff == null && ev.inProgress == null) return;
        const { start, end } = ev.task;
        if (!start || !end) return;
        const task = handlers.current.plan.tasks.find((t) => t.id === Number(ev.id));
        if (!task) return;
        const op = interpretBarChange(task, start, end);
        if (!op) return;
        void handlers.current.onApply([op]).catch(snapBack);
      },
    );

    // We intercept (never let SVAR create the link client-side) rather than `on`: the backend
    // is the only source of truth for dependencies, and only finish-to-start links are valid in
    // this domain (backend/app/domain/operations.py's AddDependencyOp has no `type`).
    api.intercept(
      "add-link",
      ({ link }: { link: { source?: number | string; target?: number | string; type?: string } }) => {
        if (handlers.current.readOnly) return false;
        if (link.type && link.type !== "e2s") {
          toast.error("Поддерживается только связь «окончание–начало»");
          return false;
        }
        if (link.source == null || link.target == null) return false;
        void handlers.current
          .onApply([linkToOperation(Number(link.source), Number(link.target))])
          .catch(snapBack);
        return false;
      },
    );
  }, [snapBack]);

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
            gridWidth={gridWidth}
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
