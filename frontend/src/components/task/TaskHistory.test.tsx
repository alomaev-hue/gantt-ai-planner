import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { api } from "@/api/client";
import { TaskHistory } from "./TaskHistory";

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, api: { taskHistory: vi.fn() } };
});

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

test("lists entries newest first with ru source labels and change lines", async () => {
  vi.mocked(api.taskHistory).mockResolvedValue([
    {
      version: 3,
      source: "agent",
      created_at: "2026-09-25T12:00:00Z",
      summary: "Изменено задач: 1",
      changes: [{ task_id: 1, task_name: "Дизайн", field: "name", before: "A", after: "B" }],
    },
    {
      version: 2,
      source: "user",
      created_at: "2026-09-24T12:00:00Z",
      summary: "Изменено задач: 1",
      changes: [{ task_id: 1, task_name: "Дизайн", field: "duration", before: 2, after: 3 }],
    },
  ]);

  renderWithQuery(<TaskHistory taskId={1} version={3} onFocusTask={vi.fn()} />);

  expect(await screen.findByText(/Версия 3 · агент/)).toBeInTheDocument();
  expect(screen.getByText(/Версия 2 · вы/)).toBeInTheDocument();
  expect(screen.getByText("название A → B")).toBeInTheDocument();
  expect(screen.getByText("длительность 2 → 3")).toBeInTheDocument();
  const versions = screen.getAllByText(/^Версия/).map((el) => el.textContent);
  expect(versions[0]).toMatch(/Версия 3/);
});

test("shows an empty state when the task has no history yet", async () => {
  vi.mocked(api.taskHistory).mockResolvedValue([]);
  renderWithQuery(<TaskHistory taskId={2} version={1} onFocusTask={vi.fn()} />);
  expect(await screen.findByText("Изменений пока не было")).toBeInTheDocument();
});

test("clicking a change line focuses that task", async () => {
  const onFocusTask = vi.fn();
  vi.mocked(api.taskHistory).mockResolvedValue([
    {
      version: 2,
      source: "mcp",
      created_at: "2026-09-24T12:00:00Z",
      summary: "Изменено задач: 1",
      changes: [{ task_id: 1, task_name: "Дизайн", field: "assignee", before: "Олег", after: "Аня" }],
    },
  ]);
  renderWithQuery(<TaskHistory taskId={1} version={2} onFocusTask={onFocusTask} />);
  const line = await screen.findByText("исполнитель Олег → Аня");
  line.click();
  expect(onFocusTask).toHaveBeenCalledWith(1);
});
