import { api } from "./client";

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
