import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

// Keyed by [task id, plan version] (spec §12): a new version means the task may have gained
// another history entry, and TanStack Query's cache would otherwise keep serving the stale list
// for this task id forever since nothing else here changes.
export function useTaskHistory(taskId: number, version: number) {
  return useQuery({
    queryKey: ["taskHistory", taskId, version],
    queryFn: () => api.taskHistory(taskId),
  });
}
