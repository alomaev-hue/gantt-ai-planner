import type {
  ApplyResponse,
  ChatMessage,
  ImportFailure,
  ImportSuccess,
  McpTokenResponse,
  MetaResponse,
  Operation,
  PlanResponse,
  TaskHistoryEntry,
} from "./types";
import { toISODate } from "@/lib/dates";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

// The backend names the file after this date (its own clock is UTC, a day off near midnight).
export const exportUrl = (now: Date = new Date()) => `/api/plan/export?today=${toISODate(now)}`;

export async function ensureSession(): Promise<void> {
  const res = await fetch("/api/session", { method: "POST" });
  if (!res.ok) throw await toError(res);
}

async function toError(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => null);
  const err = body?.error;
  return new ApiError(res.status, err?.code ?? "http_error", err?.message ?? `Ошибка ${res.status}`, err?.details);
}

export async function request<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const res = await fetch(path, init);
  if (res.status === 401 && !retried) {
    const err = await toError(res.clone());
    if (err.code === "no_session") {
      await ensureSession();
      return request<T>(path, init, true);
    }
  }
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export const api = {
  getPlan: () => request<PlanResponse>("/api/plan"),
  applyOps: (ops: Operation[]) => post<ApplyResponse>("/api/plan/operations", { ops }),
  undo: () => post<PlanResponse>("/api/plan/undo"),
  redo: () => post<PlanResponse>("/api/plan/redo"),
  reset: () => post<PlanResponse>("/api/plan/reset"),
  chatHistory: () => request<ChatMessage[]>("/api/chat/history"),
  taskHistory: (id: number) => request<TaskHistoryEntry[]>(`/api/plan/tasks/${id}/history`),
  meta: () => request<MetaResponse>("/api/meta"),
  deleteSession: () => request<void>("/api/session", { method: "DELETE" }),
  createMcpToken: () => post<McpTokenResponse>("/api/mcp-token"),
  revokeMcpToken: () => request<void>("/api/mcp-token", { method: "DELETE" }),
  async importPlan(file: File, projectStart: string): Promise<ImportSuccess | ImportFailure> {
    const form = new FormData();
    form.append("file", file);
    form.append("project_start", projectStart);
    const send = () => fetch("/api/plan/import", { method: "POST", body: form });
    let res = await send();
    if (res.status === 401) {
      await ensureSession();
      res = await send();
    }
    if (res.ok || res.status === 422) {
      const body = await res.clone().json().catch(() => null);
      if (body && "ok" in body) return body;
    }
    throw await toError(res);
  },
};
