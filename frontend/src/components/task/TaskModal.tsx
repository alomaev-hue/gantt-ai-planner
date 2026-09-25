import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError } from "@/api/client";
import type { ScheduledPlan, ScheduledTask } from "@/api/types";
import { PLAN_KEY } from "@/hooks/usePlan";
import { formatRu } from "@/lib/dates";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { buildTaskOps, formFromTask, rebaseForm, validateTaskForm, type TaskForm } from "./taskOps";

const ASSIGNEE_DATALIST_ID = "task-modal-assignees";

function describeConstraint(task: ScheduledTask, plan: ScheduledPlan): string {
  if (task.constrained_by === "project_start") return "датой старта проекта";
  if (task.constrained_by === "constraint") return "ограничением «не раньше»";
  if (task.constrained_by.startsWith("predecessor:")) {
    const id = Number(task.constrained_by.slice("predecessor:".length));
    const predecessor = plan.tasks.find((t) => t.id === id);
    return `предшественником №${id} «${predecessor?.name ?? ""}»`;
  }
  return task.constrained_by;
}

export function TaskModal({
  task,
  plan,
  open,
  onOpenChange,
  onNavigate,
  disabled,
}: {
  task: ScheduledTask | null;
  plan: ScheduledPlan;
  open: boolean;
  onOpenChange(open: boolean): void;
  onNavigate(id: number): void;
  disabled: boolean;
}) {
  const queryClient = useQueryClient();
  // `baseline` is the form as last known from the server (i.e. `formFromTask` of the task the
  // form was seeded/rebased from); `form` is what's shown in the inputs. Diffing `form` against
  // `baseline` (not the live `task` directly) in `buildTaskOps` means a server-side change to a
  // field the user hasn't touched (agent edit, another tab) never gets read as a local edit that
  // Save would silently revert. All of this resets/rebases during render, not in an effect —
  // deriving state from a changed prop belongs in the render body per React's own guidance, and
  // an effect doing the same thing would cost an extra render pass for no benefit.
  const [state, setState] = useState<{ taskId: number; form: TaskForm; baseline: TaskForm; error: string | null } | null>(
    null,
  );
  const [saving, setSaving] = useState(false);

  if (task) {
    if (!state || state.taskId !== task.id) {
      const seeded = formFromTask(task);
      setState({ taskId: task.id, form: seeded, baseline: seeded, error: null });
    } else {
      const fresh = formFromTask(task);
      const staleBaseline = (Object.keys(fresh) as (keyof TaskForm)[]).some((key) => fresh[key] !== state.baseline[key]);
      if (staleBaseline) {
        const rebased = rebaseForm(state.form, state.baseline, fresh);
        setState({ taskId: task.id, form: rebased.form, baseline: rebased.baseline, error: state.error });
      }
    }
  } else if (state) {
    setState(null);
  }

  if (!task || !state) return null;

  const { form, baseline, error } = state;
  const setForm = (form: TaskForm) => setState({ ...state, form, error: null });
  const setError = (error: string | null) => setState({ ...state, error });

  const assigneeOptions = Array.from(
    new Set(plan.tasks.map((t) => t.assignee?.trim()).filter((a): a is string => Boolean(a))),
  ).sort((a, b) => a.localeCompare(b, "ru"));

  const predecessors = plan.dependencies
    .filter((d) => d.successor_id === task.id)
    .map((d) => plan.tasks.find((t) => t.id === d.predecessor_id))
    .filter((t): t is ScheduledTask => Boolean(t));
  const successors = plan.dependencies
    .filter((d) => d.predecessor_id === task.id)
    .map((d) => plan.tasks.find((t) => t.id === d.successor_id))
    .filter((t): t is ScheduledTask => Boolean(t));

  const ops = buildTaskOps(task, form, baseline);
  const canSave = !disabled && !saving && ops.length > 0;

  const handleSave = async () => {
    const validationError = validateTaskForm(form);
    if (validationError) {
      setError(validationError);
      return;
    }
    if (ops.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      const res = await api.applyOps(ops);
      queryClient.setQueryData(PLAN_KEY, res);
      toast.success(res.summary);
      res.warnings.forEach((warning) => toast.warning(warning));
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить изменения");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>
          №{task.id} «{task.name}»
        </DialogTitle>
        <DialogDescription className="sr-only">Редактирование задачи</DialogDescription>

        <div className="mt-2 flex flex-col gap-3">
          {task.is_critical && (
            <span className="inline-flex w-fit items-center rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive">
              Критическая задача
            </span>
          )}

          <label className="flex flex-col gap-1 text-sm">
            Название
            <input
              className="rounded-md border border-input bg-background px-2 py-1"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>

          <label className="flex flex-col gap-1 text-sm">
            Описание
            <textarea
              className="rounded-md border border-input bg-background px-2 py-1"
              rows={2}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </label>

          <div className="flex gap-3">
            <label className="flex flex-1 flex-col gap-1 text-sm">
              Исполнитель
              <input
                className="rounded-md border border-input bg-background px-2 py-1"
                value={form.assignee}
                list={ASSIGNEE_DATALIST_ID}
                onChange={(e) => setForm({ ...form, assignee: e.target.value })}
              />
              <datalist id={ASSIGNEE_DATALIST_ID}>
                {assigneeOptions.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
            </label>
            <label className="flex w-28 flex-col gap-1 text-sm">
              Длительность, дн.
              <input
                type="number"
                min={1}
                max={999}
                className="rounded-md border border-input bg-background px-2 py-1"
                value={form.duration}
                onChange={(e) => setForm({ ...form, duration: Number(e.target.value) })}
              />
            </label>
          </div>

          <label className="flex flex-col gap-1 text-sm">
            Не раньше
            <div className="flex items-center gap-2">
              <input
                type="date"
                className="rounded-md border border-input bg-background px-2 py-1"
                value={form.constraint ?? ""}
                onChange={(e) => setForm({ ...form, constraint: e.target.value || null })}
              />
              {form.constraint && (
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => setForm({ ...form, constraint: null })}
                >
                  Убрать
                </button>
              )}
            </div>
          </label>

          <div className="rounded-md bg-muted/50 p-2 text-sm text-muted-foreground">
            <p>Начало: {formatRu(task.start)}</p>
            <p>Окончание: {formatRu(task.end)}</p>
            <p>Резерв {task.slack} дн.</p>
            <p>Начало определяется: {describeConstraint(task, plan)}</p>
          </div>

          {(predecessors.length > 0 || successors.length > 0) && (
            <div className="flex flex-col gap-1.5 text-sm">
              {predecessors.length > 0 && (
                <div>
                  <span className="text-muted-foreground">Предшественники: </span>
                  {predecessors.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className="mr-2 underline hover:text-foreground"
                      onClick={() => onNavigate(p.id)}
                    >
                      №{p.id} «{p.name}»
                    </button>
                  ))}
                </div>
              )}
              {successors.length > 0 && (
                <div>
                  <span className="text-muted-foreground">Последователи: </span>
                  {successors.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      className="mr-2 underline hover:text-foreground"
                      onClick={() => onNavigate(s.id)}
                    >
                      №{s.id} «{s.name}»
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {task.overallocated_with.length > 0 && (
            <p className="text-sm text-amber-600">
              Пересекается по исполнителю с задачами: {task.overallocated_with.map((id) => `№${id}`).join(", ")}
            </p>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              className="rounded-md border border-input px-3 py-1.5 text-sm hover:bg-accent"
              onClick={() => onOpenChange(false)}
            >
              Отмена
            </button>
            <button
              type="button"
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
              disabled={!canSave}
              onClick={() => void handleSave()}
            >
              Сохранить
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
