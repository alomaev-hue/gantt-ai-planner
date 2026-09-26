import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export const META_KEY = ["meta"];

// GET /api/meta needs no session and barely ever changes for a running deployment, so it's
// fetched once and kept forever (`staleTime: Infinity`) rather than refetched like the plan. The
// endpoint is owned by a parallel backend change and may not exist yet in every environment —
// `retry: false` means a missing/404 route just leaves `data` undefined instead of retrying
// pointlessly, and callers treat "no data" as "say nothing" (see Toolbar's demo-mode badge).
export function useMeta() {
  return useQuery({
    queryKey: META_KEY,
    queryFn: api.meta,
    staleTime: Infinity,
    retry: false,
  });
}
