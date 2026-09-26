# Gantt AI Planner — frontend

React 19 + TypeScript + Vite single-page app: the Gantt chart (SVAR React Gantt), the chat panel
and the dialogs. It talks only to the backend's `/api/*` (in dev, `vite` proxies `/api` and
`/healthz` to `http://localhost:8000`).

Setup, architecture and the full stack live in the [root README](../README.md).

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server with the API proxy |
| `npm test` | Vitest unit/component tests |
| `npm run typecheck` / `npm run lint` | `tsc -b --noEmit` / oxlint |
| `npm run build` | Production build into `dist/` (served by the backend in the Docker image) |
| `npm run e2e` | Playwright against a running stack (`E2E_BASE_URL`, default `http://localhost:8000`) |
