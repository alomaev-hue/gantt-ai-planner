import { ApiError, ensureSession } from "./client";
import type { ChatEvent } from "./types";

// Parses a chunk of an SSE stream. `\n\n` (or `\r\n\r\n`) separates events; `: ...` lines are
// comments (pings) and ignored; multi-line `data:` fields are joined with `\n`. Returns the
// complete events found so far plus the trailing partial block (`rest`), to be prepended to the
// next chunk.
export function parseSSE(buffer: string): { events: { event: string; data: string }[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: { event: string; data: string }[] = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (!line || line.startsWith(":")) continue;
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length) events.push({ event, data: data.join("\n") });
  }
  return { events, rest };
}

async function toApiError(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => null);
  const err = body?.error;
  return new ApiError(res.status, err?.code ?? "http_error", err?.message ?? `Ошибка ${res.status}`, err?.details);
}

// Streams a chat turn from POST /api/chat. On a 401 `no_session` it re-establishes the session
// and retries once; any other non-2xx response throws the `ApiError` parsed from the JSON body.
export async function* streamChat(message: string, signal?: AbortSignal): AsyncGenerator<ChatEvent> {
  const post = () =>
    fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message }),
      signal,
    });

  let res = await post();
  if (res.status === 401) {
    const err = await toApiError(res);
    if (err.code !== "no_session") throw err;
    await ensureSession();
    res = await post();
  }
  if (!res.ok) throw await toApiError(res);
  if (!res.body) return;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, rest } = parseSSE(buffer);
    buffer = rest;
    for (const e of events) yield JSON.parse(e.data) as ChatEvent;
  }
}
