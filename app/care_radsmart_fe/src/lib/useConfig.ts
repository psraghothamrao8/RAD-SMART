import { useQuery } from "@tanstack/react-query";

import { API } from "@/utils/api";

export function useConfig(facilityId: string) {
  return useQuery({
    queryKey: ["care_radsmart", "config", facilityId],
    queryFn: () => API.config(facilityId),
    staleTime: 60_000,
  });
}

export const keys = {
  day: (f: string, date?: string) => ["care_radsmart", "day", f, date ?? "today"],
  courses: (f: string, params?: object) => ["care_radsmart", "courses", f, params ?? {}],
  course: (f: string, id: string) => ["care_radsmart", "course", f, id],
  sessions: (f: string, id: string) => ["care_radsmart", "course-sessions", f, id],
  triages: (f: string, date?: string) => ["care_radsmart", "triage", f, date ?? "today"],
  slotRequests: (f: string) => ["care_radsmart", "slot-requests", f],
  insights: (f: string, from?: string, to?: string) => ["care_radsmart", "insights", f, from ?? "", to ?? ""],
};
