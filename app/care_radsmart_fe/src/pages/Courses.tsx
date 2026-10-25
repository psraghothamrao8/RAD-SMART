import { useQuery } from "@tanstack/react-query";
import { ClipboardPlus, Search } from "lucide-react";
import { useState } from "react";
import { navigate, useQueryParams } from "raviger";

import Layout, { PageLink } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Badge, Card, Empty, Input, Notice, Select, Spinner, Table, type Tone } from "@/components/ui/primitives";
import { hm, shortDate } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { keys } from "@/lib/useConfig";
import { API, type Config, type Course } from "@/utils/api";

import SlotRequests from "./SlotRequests";

export const COURSE_TONE: Record<Course["status"], Tone> = {
  draft: "amber",
  approved: "green",
  completed: "gray",
  cancelled: "gray",
};

export function useCourseStatus() {
  const tr = useT();
  return (s: Course["status"]) =>
    ({
      draft: tr("cs_draft", "Waiting for approval"),
      approved: tr("cs_approved", "On treatment"),
      completed: tr("cs_completed", "Completed"),
      cancelled: tr("cs_cancelled", "Cancelled"),
    })[s];
}

export function standingTime(c: Course) {
  const last = c.slots[c.slots.length - 1];
  if (!last) return "—";
  return last.start2 ? `${hm(last.start)} + ${hm(last.start2)}` : hm(last.start);
}

export default function Courses({ facilityId }: { facilityId: string }) {
  const tr = useT();
  return (
    <Layout facilityId={facilityId} title={tr("courses_title", "Treatment courses")}>
      {(config) => <CourseList facilityId={facilityId} config={config} />}
    </Layout>
  );
}

function CourseList({ facilityId, config }: { facilityId: string; config: Config }) {
  const tr = useT();
  const [params] = useQueryParams<{ patient?: string }>();
  const patient = params.patient;
  const [q, setQ] = useState("");
  const [status, setStatus] = useState(patient ? "" : "draft,approved");
  const label = useCourseStatus();
  const courses = useQuery({
    queryKey: keys.courses(facilityId, { q, status, patient }),
    queryFn: () => API.courses(facilityId, { q, status, patient }),
  });
  const canApprove = !!config.permissions?.can_approve_radsmart_course;
  const newHref = `/facility/${facilityId}/radsmart/courses/new${patient ? `?patient=${patient}` : ""}`;

  return (
    <div className="flex flex-col gap-4">
      {config.permissions?.can_operate_radsmart && <SlotRequests facilityId={facilityId} />}
      <Card
        title={patient ? tr("patient_courses", "This patient's courses") : tr("all_courses", "Courses")}
        action={
          canApprove && (
            <Button size="sm" onClick={() => navigate(newHref)}>
              <ClipboardPlus />
              {tr("new_course", "New course")}
            </Button>
          )
        }
      >
        {!patient && (
          <div className="mb-3 flex flex-wrap gap-2">
            <div className="relative w-full max-w-xs">
              <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-gray-400" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={tr("search_course", "Name or hospital number")} className="pl-8" />
            </div>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-52">
              <option value="draft,approved">{tr("f_active", "Waiting or on treatment")}</option>
              <option value="draft">{label("draft")}</option>
              <option value="approved">{label("approved")}</option>
              <option value="completed">{label("completed")}</option>
              <option value="">{tr("f_every", "Every course")}</option>
            </Select>
          </div>
        )}
        {courses.isLoading ? (
          <Spinner label={tr("loading", "Loading…")} />
        ) : courses.error ? (
          <Notice kind="error">{String((courses.error as Error).message)}</Notice>
        ) : !courses.data?.length ? (
          <Empty>
            {patient
              ? tr("no_course_patient", "No radiotherapy course for this patient yet. Start one with New course.")
              : tr("no_courses", "No courses match")}
          </Empty>
        ) : (
          <Table
            stack
            head={[
              tr("h_patient", "Patient"),
              tr("h_diagnosis", "Diagnosis"),
              tr("h_treatment", "Treatment"),
              tr("h_progress", "Fractions"),
              tr("h_slot", "Standing slot"),
              tr("h_dates", "Dates"),
              tr("h_status", "Status"),
            ]}
          >
            {courses.data.map((c) => (
              // Below md each row is a card: patient | status, diagnosis, treatment | fractions, standing slot, dates.
              <tr
                key={c.id}
                className="hover:bg-gray-50 max-md:grid max-md:grid-cols-[minmax(0,1fr)_auto] max-md:gap-x-3 max-md:rounded-lg max-md:border max-md:border-gray-200 max-md:bg-white max-md:py-1 max-md:[&>td]:px-3 max-md:[&>td]:py-0.5"
              >
                <td className="px-3 py-2 max-md:pt-1.5">
                  <PageLink href={`/facility/${facilityId}/radsmart/courses/${c.id}`}>{c.patient_name}</PageLink>
                  <div className="text-xs text-gray-500">{c.hospital_number}</div>
                </td>
                <td className="px-3 py-2 max-md:col-span-2">
                  {c.diagnosis}
                  <div className="text-xs text-gray-500">
                    {c.total_dose_gy} Gy / {c.fractions}
                  </div>
                </td>
                <td className="px-3 py-2">{c.technique_label}</td>
                <td className="px-3 py-2 tabular-nums max-md:text-right">
                  <span className="text-xs text-gray-500 md:hidden">{tr("h_progress", "Fractions")} </span>
                  {c.sessions_done}/{c.fractions}
                </td>
                <td className="px-3 py-2 tabular-nums max-md:col-span-2">
                  <span className="text-xs text-gray-500 md:hidden">{tr("h_slot", "Standing slot")} </span>
                  {standingTime(c)}
                </td>
                <td className="px-3 py-2 text-xs text-gray-600 max-md:col-span-2 max-md:pb-1.5">
                  {c.dates.length ? `${shortDate(c.dates[0])} – ${shortDate(c.dates[c.dates.length - 1])}` : shortDate(c.start_date)}
                </td>
                <td className="px-3 py-2 max-md:col-start-2 max-md:row-start-1 max-md:pt-1.5 max-md:text-right">
                  <Badge tone={COURSE_TONE[c.status]}>{label(c.status)}</Badge>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
