import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Download, MoreVertical, Redo2, RotateCcw, Undo2, Upload } from "lucide-react";
import { api, ApiError, EXPORT_URL } from "@/api/client";
import type { PlanResponse } from "@/api/types";
import { PLAN_KEY } from "@/hooks/usePlan";
import { cn } from "@/lib/utils";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import type { Zoom } from "@/components/gantt/mapping";

const ZOOM_LABELS: Record<Zoom, string> = { day: "День", week: "Неделя", month: "Месяц" };
const ZOOM_ORDER: Zoom[] = ["day", "week", "month"];

export function Toolbar({
  plan,
  agentBusy,
  zoom,
  onZoom,
  onImport,
}: {
  plan: PlanResponse;
  agentBusy: boolean;
  zoom: Zoom;
  onZoom(zoom: Zoom): void;
  onImport(): void;
}) {
  const queryClient = useQueryClient();
  const [resetOpen, setResetOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [pending, setPending] = useState(false);

  const runPlanAction = async (action: () => Promise<PlanResponse>, errorMessage: string) => {
    setPending(true);
    try {
      const res = await action();
      queryClient.setQueryData(PLAN_KEY, res);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : errorMessage);
    } finally {
      setPending(false);
    }
  };

  const busy = agentBusy || pending;

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 rounded-md border border-input px-3 py-1.5 text-sm hover:bg-accent"
        onClick={onImport}
      >
        <Upload className="h-4 w-4" /> Загрузить Excel
      </button>

      <a
        href={EXPORT_URL}
        download
        className="inline-flex items-center gap-1.5 rounded-md border border-input px-3 py-1.5 text-sm hover:bg-accent"
      >
        <Download className="h-4 w-4" /> Экспорт
      </a>

      <div className="mx-1 h-5 w-px bg-border" />

      <button
        type="button"
        title="Отменить"
        aria-label="Отменить"
        disabled={!plan.can_undo || busy}
        className="rounded-md border border-input p-1.5 hover:bg-accent disabled:opacity-40"
        onClick={() => void runPlanAction(api.undo, "Не удалось отменить действие")}
      >
        <Undo2 className="h-4 w-4" />
      </button>
      <button
        type="button"
        title="Повторить"
        aria-label="Повторить"
        disabled={!plan.can_redo || busy}
        className="rounded-md border border-input p-1.5 hover:bg-accent disabled:opacity-40"
        onClick={() => void runPlanAction(api.redo, "Не удалось повторить действие")}
      >
        <Redo2 className="h-4 w-4" />
      </button>

      <div className="mx-1 h-5 w-px bg-border" />

      <div className="inline-flex rounded-md border border-input p-0.5">
        {ZOOM_ORDER.map((z) => (
          <button
            key={z}
            type="button"
            className={cn(
              "rounded-sm px-2.5 py-1 text-sm",
              zoom === z ? "bg-primary text-primary-foreground" : "hover:bg-accent",
            )}
            onClick={() => onZoom(z)}
          >
            {ZOOM_LABELS[z]}
          </button>
        ))}
      </div>

      <div className="ml-auto flex items-center gap-2">
        {agentBusy && (
          <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800">
            Агент редактирует план…
          </span>
        )}

        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-md border border-input px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-40"
          disabled={busy}
          onClick={() => setResetOpen(true)}
        >
          <RotateCcw className="h-4 w-4" /> Сбросить к демо
        </button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" aria-label="Ещё" className="rounded-md border border-input p-1.5 hover:bg-accent">
              <MoreVertical className="h-4 w-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onSelect={() => setDeleteOpen(true)}>Удалить мои данные</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <ConfirmDialog
        open={resetOpen}
        onOpenChange={setResetOpen}
        title="Сбросить план"
        description="Текущий план будет заменён демо-планом. Действие можно отменить."
        confirmLabel="Сбросить"
        onConfirm={() => void runPlanAction(api.reset, "Не удалось сбросить план")}
      />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Удалить мои данные"
        description="Все данные текущей сессии будут удалены без возможности восстановления."
        confirmLabel="Удалить"
        destructive
        onConfirm={() => {
          void api.deleteSession().finally(() => location.reload());
        }}
      />
    </div>
  );
}
