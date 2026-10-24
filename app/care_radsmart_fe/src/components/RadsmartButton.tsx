import { useQuery } from "@tanstack/react-query";
import { Radiation } from "lucide-react";
import { navigate } from "raviger";

import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { API } from "@/utils/api";

import { standingTime } from "@/pages/Courses";

import Page from "./Page";

/**
 * The RADSMART button. On the visit and patient pages it opens the patient's
 * radiotherapy course (or starts one); on the facility page it opens today's board.
 */
export default function RadsmartButton({ facilityId, patientId, className }: { facilityId?: string; patientId?: string; className?: string }) {
  const tr = useT();
  const courses = useQuery({
    queryKey: ["care_radsmart", "patient-course", facilityId, patientId],
    queryFn: () => API.courses(facilityId!, { patient: patientId, status: "draft,approved" }),
    enabled: !!facilityId && !!patientId,
    retry: false,
  });
  if (!facilityId) return null;
  if (patientId && courses.isError) return null;          // no RAD-SMART access in this facility
  const active = courses.data?.[0];
  const href = !patientId
    ? `/facility/${facilityId}/radsmart`
    : active
      ? `/facility/${facilityId}/radsmart/courses/${active.id}`
      : `/facility/${facilityId}/radsmart/courses?patient=${patientId}`;
  const label = active
    ? active.status === "approved"
      ? tr("btn_slot", "RADSMART · {{time}}", { time: standingTime(active) })
      : tr("btn_draft", "RADSMART · to approve")
    : "RADSMART";
  return (
    <Page>
      <button
        type="button"
        onClick={() => navigate(href)}
        className={cn(
          "inline-flex h-9 items-center justify-center gap-2 rounded-md bg-primary-700 px-4 text-sm font-semibold whitespace-nowrap text-white shadow-sm hover:bg-primary-800",
          className,
        )}
        title={tr("btn_title", "Radiotherapy scheduling (RAD-SMART)")}
      >
        <Radiation className="size-4" />
        {label}
      </button>
    </Page>
  );
}

export function EncounterRadsmart({ encounter, className }: { encounter: { facility: { id: string }; patient: { id: string } }; className?: string }) {
  return <RadsmartButton facilityId={encounter.facility?.id} patientId={encounter.patient?.id} className={className} />;
}

export function PatientRadsmart({ patient, facilityId, className }: { patient: { id: string }; facilityId?: string; className?: string }) {
  return <RadsmartButton facilityId={facilityId} patientId={patient?.id} className={className} />;
}

export function FacilityRadsmart({ facility, className }: { facility: { id: string }; className?: string }) {
  return <RadsmartButton facilityId={facility?.id} className={className} />;
}
