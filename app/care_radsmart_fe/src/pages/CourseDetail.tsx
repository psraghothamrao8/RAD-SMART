import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck2, Copy, ExternalLink, MessageCircle, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Badge, Card, Empty, Field, Input, Notice, Spinner, Table } from "@/components/ui/primitives";
import { addDays, clockTime, hm, longDate, shortDate, workingDay } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { keys } from "@/lib/useConfig";
import { API, type Config, type Course, type Explanation, type Proposal, type SlotRequest } from "@/utils/api";

import { COURSE_TONE, useCourseStatus } from "./Courses";
import { MessageCard } from "./Messages";
import { SlotChoice, slotOptions } from "./SlotChoice";
import { RequestRow } from "./SlotRequests";
import { STATUS_TONE, useStatusLabel } from "./Today";

export default function CourseDetail({ facilityId, courseId }: { facilityId: string; courseId: string }) {
  const tr = useT();
  return (
    <Layout facilityId={facilityId} title={tr("course_title", "Radiotherapy course")}>
      {(config) => <Detail facilityId={facilityId} courseId={courseId} config={config} />}
    </Layout>
  );
}

function Detail({ facilityId, courseId, config }: { facilityId: string; courseId: string; config: Config }) {
  const tr = useT();
  const qc = useQueryClient();
  const label = useCourseStatus();
  const course = useQuery({ queryKey: keys.course(facilityId, courseId), queryFn: () => API.course(facilityId, courseId) });
  const canApprove = !!config.permissions?.can_approve_radsmart_course;
  const cancel = useMutation({
    mutationFn: () => API.cancel(facilityId, courseId),
    onSuccess: () => {
      toast.success(tr("course_cancelled", "Course cancelled; its future sessions are released"));
      qc.invalidateQueries({ queryKey: ["care_radsmart"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (course.isLoading) return <Spinner label={tr("loading", "Loading…")} />;
  if (!course.data) return <Notice kind="error">{String((course.error as Error)?.message)}</Notice>;
  const c = course.data;
  const pattern = config.patterns.find((p) => p.code === c.pattern)?.label ?? c.pattern;
  const gap = config.gap_categories.find((g) => g.code === c.gap_category)?.label;

  return (
    <div className="flex flex-col gap-4">
      <Card
        title={
          <span className="flex flex-wrap items-center gap-2">
            {c.patient_name}
            <Badge tone={COURSE_TONE[c.status]}>{label(c.status)}</Badge>
            {c.demo && <Badge tone="violet">{tr("demo_short", "demo")}</Badge>}
          </span>
        }
        action={
          canApprove &&
          ["draft", "approved"].includes(c.status) && (
            <Button
              size="sm"
              variant="outline"
              disabled={cancel.isPending}
              onClick={() => window.confirm(tr("confirm_cancel", "Cancel this course? Its future sessions are released for other patients.")) && cancel.mutate()}
            >
              {tr("cancel_course", "Cancel course")}
            </Button>
          )
        }
      >
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <Item label={tr("f_hospital_number", "Hospital number")} value={c.hospital_number} />
          <Item label={tr("f_diagnosis", "Diagnosis")} value={c.diagnosis} />
          <Item label={tr("prescription", "Prescription")} value={`${c.total_dose_gy} Gy in ${c.fractions} fractions`} />
          <Item label={tr("f_pattern", "Treatment days")} value={pattern} />
          <Item label={tr("f_technique", "Technique")} value={c.technique_label} />
          <Item label={tr("f_machine", "Preferred machine")} value={c.machines.join(", ")} />
          <Item label={tr("f_gap", "Gap category (RCR)")} value={gap ?? String(c.gap_category)} />
          <Item label={tr("progress", "Treated")} value={`${c.sessions_done} of ${c.fractions}`} />
          {c.preferred_time && <Item label={tr("f_preferred", "Preferred time")} value={c.preferred_time} />}
          {(c.earliest_start || c.latest_end) && (
            <Item label={tr("window", "Time window")} value={`${c.earliest_start ?? "—"} – ${c.latest_end ?? "—"}`} />
          )}
          {c.approved_by && <Item label={tr("approved_by_label", "Approved by")} value={`${c.approved_by}, ${c.approved_at ? new Date(c.approved_at).toLocaleString("en-IN") : ""}`} />}
        </dl>
        {c.flags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {c.flags.map((f) => (
              <Badge key={f}>{f}</Badge>
            ))}
          </div>
        )}
        {c.note && <p className="mt-3 text-sm text-gray-600">{c.note}</p>}
      </Card>

      {c.status === "draft" && <ProposalPanel c={c} facilityId={facilityId} canApprove={canApprove} />}
      {c.status === "approved" && <Standing c={c} facilityId={facilityId} config={config} />}
      {c.status === "approved" && config.permissions?.can_operate_radsmart && <PatientLinkCard c={c} facilityId={facilityId} />}
      {c.status !== "draft" && <CourseMessages c={c} facilityId={facilityId} canOperate={!!config.permissions?.can_operate_radsmart} />}
      {c.status !== "draft" && <Sessions c={c} facilityId={facilityId} />}
    </div>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="font-medium text-gray-900">{value}</dd>
    </div>
  );
}

function ProposalPanel({ c, facilityId, canApprove }: { c: Course; facilityId: string; canApprove: boolean }) {
  const tr = useT();
  const qc = useQueryClient();
  const [proposal, setProposal] = useState<Proposal | null>(("ok" in c.proposal ? c.proposal : null) as Proposal | null);
  const [startDate, setStartDate] = useState(c.start_date);
  const [time, setTime] = useState("");
  const propose = useMutation({
    mutationFn: (d: string) => API.propose(facilityId, c.id, d, true),
    onSuccess: (p) => {
      setProposal(p);
      setTime(slotOptions(p)[0]?.time ?? "");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  // A new draft is planned once on opening. A query, not the mutation, so that React's double
  // mount in development does not plan it twice (each plan takes seconds of solver time).
  const first = useQuery({
    queryKey: ["radsmart-first-proposal", c.id],
    queryFn: () => API.propose(facilityId, c.id, c.start_date, true),
    enabled: !proposal && canApprove,
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
  });
  useEffect(() => {
    const p = proposal ?? first.data;
    if (p && !proposal) setProposal(p);
    if (p) setTime(slotOptions(p)[0]?.time ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [first.data]);
  useEffect(() => {
    if (first.error) toast.error((first.error as Error).message);
  }, [first.error]);
  const planning = propose.isPending || first.isFetching;
  const approve = useMutation({
    mutationFn: () => {
      const standing = proposal?.standing?.time;
      return API.approve(facilityId, c.id, proposal!, time && time !== standing ? time : undefined);
    },
    onSuccess: () => {
      toast.success(tr("course_approved", "Course approved: the patient keeps this slot until the course ends"));
      qc.invalidateQueries({ queryKey: ["care_radsmart"] });
    },
    onError: (e: Error) => {
      toast.error(e.message);
      propose.mutate(proposal?.start_date ?? startDate);
    },
  });

  return (
    <Card title={tr("proposal", "RAD-SMART's proposal")} action={planning ? <Spinner /> : null}>
      {!canApprove && <Notice kind="info">{tr("waiting_doctor", "Waiting for a doctor to approve the course and its slots.")}</Notice>}
      {proposal && !proposal.ok && (
        <Notice kind="warn" title={tr("no_room", "No slot fits from this date")}>
          {proposal.problem}
        </Notice>
      )}
      {proposal?.ok && (
        <div className="flex flex-col gap-4">
          <div className="grid gap-3 md:grid-cols-3">
            <SlotBox
              title={tr("first_day", "First day (new start)")}
              main={proposal.first ? `${shortDate(proposal.first.date!)} · ${proposal.first.time}` : "—"}
              sub={proposal.first ? tr("first_sub", "Report {{report}} · about {{min}} min with verification imaging", { report: proposal.first.report ?? "—", min: Math.round(proposal.first.minutes) }) : ""}
            />
            <SlotBox
              title={tr("standing", "Standing slot, every later fraction")}
              main={time || proposal.standing?.time || "—"}
              sub={proposal.standing ? tr("standing_sub", "{{machine}} · about {{min}} min · report {{report}}", { machine: proposal.standing.machine_name, min: Math.round(proposal.standing.minutes), report: proposal.standing.report ?? "—" }) : tr("single", "Single fraction")}
            />
            <SlotBox
              title={tr("course_dates", "Course")}
              main={`${shortDate(proposal.start_date)} – ${proposal.end_date ? shortDate(proposal.end_date) : "—"}`}
              sub={tr("treatment_days_n", "{{n}} treatment days", { n: proposal.treatment_days })}
            />
          </div>
          {proposal.standing2 && (
            <Notice kind="info">{tr("bid_second", "Second daily fraction at {{time}}", { time: proposal.standing2.time })}</Notice>
          )}
          <SlotChoice proposal={proposal} value={time} onChange={setTime} />
          <ExplainBox c={c} facilityId={facilityId} proposal={proposal} chosenTime={time && time !== proposal.standing?.time ? time : undefined} />
        </div>
      )}
      {canApprove && (
        <div className="mt-4 flex flex-wrap items-end justify-between gap-3 border-t border-gray-100 pt-4">
          <div className="flex items-end gap-2">
            <Field label={tr("try_date", "Try another start date")}>
              <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-44" />
            </Field>
            <Button variant="outline" onClick={() => propose.mutate(startDate)} disabled={planning}>
              <RefreshCw />
              {tr("repropose", "Propose again")}
            </Button>
          </div>
          <Button onClick={() => approve.mutate()} disabled={!proposal?.ok || approve.isPending || planning}>
            <CalendarCheck2 />
            {tr("approve_course", "Approve course and slots")}
          </Button>
        </div>
      )}
    </Card>
  );
}

function SlotBox({ title, main, sub }: { title: string; main: string; sub: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
      <p className="text-xs font-medium text-gray-500">{title}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-gray-900">{main}</p>
      <p className="text-xs text-gray-500">{sub}</p>
    </div>
  );
}

function Standing({ c, facilityId, config }: { c: Course; facilityId: string; config: Config }) {
  const tr = useT();
  const canOperate = !!config.permissions?.can_operate_radsmart;
  const [fromDate, setFromDate] = useState(workingDay(addDays(config.today, 1)));
  const [wanted, setWanted] = useState("");
  const [reason, setReason] = useState("");
  const [req, setReq] = useState<SlotRequest | null>(null);
  const ask = useMutation({
    mutationFn: () => API.slotRequest(facilityId, c.id, { from_date: fromDate, wanted, reason }),
    onSuccess: setReq,
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Card title={tr("slots", "Slots")}>
      <div className="grid gap-3 md:grid-cols-3">
        <SlotBox
          title={tr("first_day", "First day (new start)")}
          main={c.first?.date ? `${shortDate(c.first.date)} · ${c.first.time}` : "—"}
          sub={c.first?.report ? tr("report_at", "report {{time}}", { time: c.first.report }) : ""}
        />
        {c.slots.map((s, i) => (
          <SlotBox
            key={`${s.from}-${i}`}
            title={i === 0 ? tr("standing", "Standing slot, every later fraction") : tr("standing_from", "Standing slot from {{date}}", { date: shortDate(s.from) })}
            main={s.start2 ? `${hm(s.start)} + ${hm(s.start2)}` : hm(s.start)}
            sub={`${s.machine} · ${tr("slot_from", "from")} ${longDate(s.from)}`}
          />
        ))}
      </div>
      {"ok" in c.proposal && c.proposal.ok && (
        <div className="mt-4">
          <ExplainBox c={c} facilityId={facilityId} />
        </div>
      )}
      {canOperate && (
        <div className="mt-4 border-t border-gray-100 pt-4">
          <p className="text-sm font-semibold text-gray-900">{tr("change_title", "The patient asks for another time")}</p>
          <p className="text-xs text-gray-500">{tr("change_hint", "RAD-SMART proposes the nearest time that keeps every rule; the slot changes only when approved.")}</p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <Field label={tr("from_date", "From")}>
              <Input type="date" value={fromDate} min={config.today} onChange={(e) => setFromDate(e.target.value)} className="w-44" />
            </Field>
            <Field label={tr("wanted", "Asks for")}>
              <Input type="time" value={wanted} onChange={(e) => setWanted(e.target.value)} className="w-32" />
            </Field>
            <Field label={tr("reason", "Reason")} className="min-w-48 flex-1">
              <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={tr("reason_ph", "e.g. bus timing, work, chemotherapy")} />
            </Field>
            <Button onClick={() => ask.mutate()} disabled={!wanted || ask.isPending}>
              {ask.isPending ? tr("finding", "Finding a time…") : tr("find_time", "Find a time")}
            </Button>
          </div>
          {req && req.status === "proposed" && (
            <div className="mt-4 rounded-lg border border-gray-200 p-3">
              <RequestRow r={req} facilityId={facilityId} onDone={() => setReq(null)} />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

/** RAD-SMART's reasons in plain words (Sarvam-105B), in English and the patient's language. */
function ExplainBox({ c, facilityId, proposal, chosenTime }: { c: Course; facilityId: string; proposal?: Proposal; chosenTime?: string }) {
  const tr = useT();
  const [out, setOut] = useState<Explanation | null>(null);
  const explain = useMutation({
    mutationFn: () => API.explain(facilityId, c.id, { proposal, chosen_time: chosenTime, language: c.language }),
    onSuccess: setOut,
    onError: (e: Error) => toast.error(e.message),
  });
  useEffect(() => setOut(null), [proposal, chosenTime]);
  return (
    <div className="rounded-lg border border-gray-200 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-gray-900">{tr("why_title", "Why these times")}</p>
        <Button size="sm" variant="outline" onClick={() => explain.mutate()} disabled={explain.isPending}>
          <Sparkles />
          {explain.isPending ? tr("explaining", "Explaining…") : out ? tr("explain_again", "Explain again") : tr("explain", "Explain in plain words")}
        </Button>
      </div>
      {out && (
        <div className="mt-2 flex flex-col gap-2 text-sm">
          <p className="text-gray-800">{out.text}</p>
          {out.local_text && (
            <p className="rounded-md bg-gray-50 px-3 py-2 text-base text-gray-900">
              <span className="mr-2 text-xs font-semibold text-gray-500">{out.language}</span>
              {out.local_text}
            </p>
          )}
          <p className="text-xs text-gray-500">
            <Badge tone={out.source === "engine" ? "gray" : "blue"} className="mr-2">
              {out.source === "engine" ? tr("src_engine", "Engine's reasons") : tr("src_sarvam", "Sarvam AI")}
            </Badge>
            {out.source === "engine"
              ? out.note
              : tr("explain_check", "Written from the engine's reasons only; any time not in the plan would have been rejected.")}
            {out.local_note && ` ${out.local_note}`}
          </p>
        </div>
      )}
    </div>
  );
}

/** The patient's own page (live times, messages, replies) and the code reception scans. */
function PatientLinkCard({ c, facilityId }: { c: Course; facilityId: string }) {
  const tr = useT();
  const link = useQuery({ queryKey: keys.patientLink(facilityId, c.id), queryFn: () => API.patientLink(facilityId, c.id) });
  return (
    <Card title={tr("patient_page", "The patient's phone page")}>
      {link.isLoading ? (
        <Spinner />
      ) : !link.data ? (
        <Notice kind="error">{String((link.error as Error)?.message)}</Notice>
      ) : (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          {/* SVG drawn by the server (segno) from the six-letter code only. */}
          <div className="w-40 shrink-0 rounded-lg border border-gray-200 bg-white p-1 [&_svg]:h-auto [&_svg]:w-full" dangerouslySetInnerHTML={{ __html: link.data.qr }} />
          <div className="flex min-w-0 flex-col gap-2 text-sm">
            <p>
              <span className="text-xs text-gray-500">{tr("checkin_code", "Check-in code")} </span>
              <span className="font-mono text-xl font-semibold tracking-widest">{link.data.code}</span>
            </p>
            <p className="text-gray-600">
              {tr(
                "patient_page_text",
                "Send this link once. The patient sees today's time, any change and the messages with voice notes in {{lang}}, and can say they are on the way, late, cannot come, or want another time. No login; first name only.",
                { lang: c.language },
              )}
            </p>
            <p className="truncate font-mono text-xs text-gray-500">{link.data.url}</p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm">
                <a href={link.data.whatsapp} target="_blank" rel="noreferrer">
                  <MessageCircle />
                  {tr("send_whatsapp", "Send on WhatsApp")}
                </a>
              </Button>
              <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(link.data.url).then(() => toast.success(tr("copied_link", "Link copied")))}>
                <Copy />
                {tr("copy_link", "Copy link")}
              </Button>
              <Button asChild size="sm" variant="ghost">
                <a href={link.data.url} target="_blank" rel="noreferrer">
                  <ExternalLink />
                  {tr("open_page", "Open the page")}
                </a>
              </Button>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

function CourseMessages({ c, facilityId, canOperate }: { c: Course; facilityId: string; canOperate: boolean }) {
  const tr = useT();
  const list = useQuery({
    queryKey: keys.messages(facilityId, { course: c.id }),
    queryFn: () => API.messages(facilityId, { course: c.id }),
    refetchInterval: (q) => (q.state.data?.some((m) => m.local_status === "pending") ? 3_000 : false),
  });
  if (!list.data?.length) return null;
  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold text-gray-900">{tr("course_messages", "Messages to the patient")}</h2>
      {list.data.slice(0, 5).map((m) => (
        <MessageCard key={m.id} m={m} facilityId={facilityId} canOperate={canOperate} compact />
      ))}
    </div>
  );
}

function Sessions({ c, facilityId }: { c: Course; facilityId: string }) {
  const tr = useT();
  const statusLabel = useStatusLabel();
  const rows = useQuery({ queryKey: keys.sessions(facilityId, c.id), queryFn: () => API.courseSessions(facilityId, c.id) });
  return (
    <Card title={tr("sessions_course", "Sessions")}>
      {rows.isLoading ? (
        <Spinner />
      ) : !rows.data?.length ? (
        <Empty>{tr("no_sessions_course", "No sessions")}</Empty>
      ) : (
        <Table head={[tr("h_date", "Date"), tr("h_time", "Time"), tr("h_fraction", "Fraction"), tr("h_in_out", "In / out"), tr("h_status", "Status")]}>
          {rows.data.map((s) => (
            <tr key={s.id}>
              <td className="px-3 py-1.5">{s.date ? shortDate(s.date) : ""}</td>
              <td className="px-3 py-1.5 tabular-nums">
                {s.time}
                {s.moved_today && <span className="ml-1 text-xs text-warning-800">({tr("was", "was {{time}}", { time: s.planned_time })})</span>}
              </td>
              <td className="px-3 py-1.5 tabular-nums">
                {s.fraction}/{s.fractions}
                {s.kind === "new_start" && <Badge tone="green" className="ml-2">{tr("kind_new_start", "New start")}</Badge>}
                {s.kind === "added" && <Badge tone="violet" className="ml-2">{tr("kind_added", "Added fraction")}</Badge>}
              </td>
              <td className="px-3 py-1.5 text-xs tabular-nums text-gray-600">
                {s.in_room_at ? `${clockTime(s.in_room_at)} – ${clockTime(s.out_at)}` : "—"}
              </td>
              <td className="px-3 py-1.5">
                <Badge tone={STATUS_TONE[s.status]}>{statusLabel(s.status)}</Badge>
                {s.note && <span className="ml-2 text-xs text-gray-500">{s.note}</span>}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
