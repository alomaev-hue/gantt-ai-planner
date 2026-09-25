import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export const PLAN_KEY = ["plan"];

export function usePlan() {
  return useQuery({ queryKey: PLAN_KEY, queryFn: api.getPlan });
}
