import { ApiError, api, retryUnlessClientError } from "./client";

afterEach(() => vi.restoreAllMocks());

test("401 no_session triggers session creation and one retry", async () => {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(`${init?.method ?? "GET"} ${url}`);
    if (url === "/api/session") return new Response(JSON.stringify({ ok: true }), { status: 200 });
    if (calls.filter((c) => c === "GET /api/plan").length === 1)
      return new Response(JSON.stringify({ error: { code: "no_session", message: "x" } }), { status: 401 });
    return new Response(JSON.stringify({ version: 1 }), { status: 200 });
  }));
  const plan = await api.getPlan();
  expect(plan.version).toBe(1);
  expect(calls).toEqual(["GET /api/plan", "POST /api/session", "GET /api/plan"]);
});

test("errors carry code and message", async () => {
  vi.stubGlobal("fetch", vi.fn(async () =>
    new Response(JSON.stringify({ error: { code: "agent_busy", message: "Агент занят" } }), { status: 409 })));
  await expect(api.undo()).rejects.toMatchObject({ status: 409, code: "agent_busy", message: "Агент занят" });
});

test("export URL carries the user's local calendar date", async () => {
  const { exportUrl } = await import("./client");
  expect(exportUrl(new Date(2026, 11, 31, 23, 30))).toBe("/api/plan/export?today=2026-12-31");
});

test("concurrent ensureSession calls share one POST /api/session", async () => {
  const { ensureSession } = await import("./client");
  let posts = 0;
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  vi.stubGlobal("fetch", vi.fn(async () => {
    posts += 1;
    await gate;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }));
  const first = ensureSession();
  const second = ensureSession();
  const third = ensureSession();
  release();
  await Promise.all([first, second, third]);
  expect(posts).toBe(1);
  // Once settled, a later call starts a fresh request.
  await ensureSession();
  expect(posts).toBe(2);
});

test("mutations send the plan version they were made against", async () => {
  const bodies: unknown[] = [];
  vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
    bodies.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ version: 3 }), { status: 200 });
  }));
  await api.applyOps([{ op: "clear_constraint", id: 1 }], 2);
  await api.undo(3);
  await api.redo();
  expect(bodies).toEqual([
    { ops: [{ op: "clear_constraint", id: 1 }], expected_version: 2 },
    { expected_version: 3 },
    { expected_version: null },
  ]);
});

test("queries don't retry client errors (a 429 rate limit must surface, not spin)", () => {
  const limited = new ApiError(429, "rate_limited", "Слишком много новых сессий");
  expect(retryUnlessClientError(0, limited)).toBe(false);
  expect(retryUnlessClientError(0, new ApiError(404, "not_found", "x"))).toBe(false);
  // Server errors and network failures still get the usual three retries.
  expect(retryUnlessClientError(0, new ApiError(502, "http_error", "x"))).toBe(true);
  expect(retryUnlessClientError(2, new TypeError("Failed to fetch"))).toBe(true);
  expect(retryUnlessClientError(3, new TypeError("Failed to fetch"))).toBe(false);
});
