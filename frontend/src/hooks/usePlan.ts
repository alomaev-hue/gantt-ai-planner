import { useQuery, type QueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import type { PlanResponse } from "@/api/types";

export const PLAN_KEY = ["plan"];

export function usePlan() {
  return useQuery({ queryKey: PLAN_KEY, queryFn: api.getPlan });
}

// The version the UI is currently showing — what a mutation sends as `expected_version`.
export function cachedPlanVersion(queryClient: QueryClient): number | undefined {
  return queryClient.getQueryData<PlanResponse>(PLAN_KEY)?.version;
}

// A 409 `version_conflict` means the plan moved on under this tab (another tab, the agent,
// MCP): refetch so the user is looking at the current state before they retry. Returns true
// when the error was a conflict so callers can skip their generic error path.
export function refetchOnConflict(queryClient: QueryClient, err: unknown): boolean {
  if (!(err instanceof ApiError) || err.code !== "version_conflict") return false;
  void queryClient.invalidateQueries({ queryKey: PLAN_KEY });
  return true;
}
