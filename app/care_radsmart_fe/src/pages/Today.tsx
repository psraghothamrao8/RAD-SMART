import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightCircle, Check, ChevronLeft, ChevronRight, Power, RotateCcw, Smartphone, Sparkles, Wrench } from "lucide-react";
import { useState } from "react";
import { navigate } from "raviger";
import { toast } from "sonner";

import Layout, { PageLink } from "@/components/Layout";
import Timeline from "@/components/Timeline";
import { Button } from "@/components/ui/button";
import { Badge, Card, Empty, Input, Notice, Spinner, Table, type Tone } from "@/components/ui/primitives";
import { addDays, clockTime, longDate, nowMinutes, shortDate, workingDay } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { keys } from "@/lib/useConfig";
import { cn } from "@/lib/utils";
import { API, type Band, type Config, type MachineInfo, type PatientReply, type SessionRow } from "@/utils/api";

type Step = "arrive" | "room" | "done" | "undo" | "send-home";

export const STATUS_TONE: Record<string, Tone> = {
  scheduled: "gray",
  arrived: "blue",
  in_room: "amber",
  done: "green",
  sent_home: "red",
  postponed: "violet",
  missed: "red",
  cancelled: "gray",
};

export function useStatusLabel() {
  const tr = useT();
  return (s: string) =>
    ({
      scheduled: tr("st_scheduled", "To come"),
      arrived: tr("st_arrived", "Waiting"),
      in_room: tr("st_in_room", "In room"),
      done: tr("st_done", "Treated"),
      sent_home: tr("st_sent_home", "Sent back"),
      postponed: tr("st_postponed", "Postponed"),
      missed: tr("st_missed", "Missed"),
      cancelled: tr("st_cancelled", "Cancelled"),
    })[s] ?? s;
}

export default function Today({ facilityId }: { facilityId: string }) {
  const tr = useT();
  return (
    <Layout facilityId={facilityId} title={tr("today_title", "Today's treatment day")}>
      {(config) => <Board facilityId={facilityId} config={config} />}
    </Layout>
  );
}

function Board({ facilityId, config }: { facilityId: string; config: Config }) {
  const tr = useT();
  const qc = useQueryClient();
  const [date, setDate] = useState(config.today);
  const [filter, setFilter] = useState<"all" | "waiting" | "to_come" | "done">("all");
  const isToday = date === config.today;
  const canOperate = !!config.permissions?.can_operate_radsmart;
  const statusLabel = useStatusLabel();

  const day = useQuery({
    queryKey: keys.day(facilityId, date),
    queryFn: () => API.day(facilityId, date),
    refetchInterval: isToday ? 30_000 : false,
  });
  const triages = useQuery({
    queryKey: keys.triages(facilityId, date),
    queryFn: () => API.triages(facilityId, date),
    enabled: isToday,
  });
  const replies = useQuery({
    queryKey: keys.replies(facilityId, date),
    queryFn: () => API.replies(facilityId, date),
    enabled: isToday,
    refetchInterval: 30_000,
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["care_radsmart"] });
  };

  const step = useMutation({
    mutationFn: ({ id, action, reason }: { id: string; action: Step; reason?: string }) => API.session(id, action, reason ? { reason } : {}),
    onSuccess: refresh,
    onError: (e: Error) => toast.error(e.message),
  });
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approve" | "reject" }) => API.decideSlot(facilityId, id, decision),
    onSuccess: (_, v) => {
      toast.success(v.decision === "approve" ? tr("offer_taken", "New standing time saved; a message to the patient is ready") : tr("offer_kept", "The patient keeps their time"));
      refresh();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const approve = useMutation({
    mutationFn: () => API.approveDay(facilityId, date),
    onSuccess: () => {
      toast.success(tr("day_approved", "Today's plan is approved"));
      refresh();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const online = useMutation({
    mutationFn: (m: MachineInfo) => API.machineStatus(m.id, { status: "online" }),
    onSuccess: () => {
      toast.success(tr("machine_online", "Machine is back online"));
      refresh();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (day.isLoading) return <Spinner label={tr("loading", "Loading…")} />;
  if (day.error || !day.data) return <Notice kind="error">{String((day.error as Error)?.message)}</Notice>;
  const d = day.data;
  const pending = (triages.data ?? []).filter((t) => t.status === "proposed");
  const rows = d.sessions.filter((s) =>
    filter === "all"
      ? true
      : filter === "waiting"
        ? ["arrived", "in_room"].includes(s.status)
        : filter === "to_come"
          ? s.status === "scheduled"
          : ["done", "sent_home", "postponed", "missed"].includes(s.status),
  );
  const openReplies = (replies.data ?? []).filter((r) => r.status === "open");
  // Newest open reply per course, shown beside the patient on the board.
  const replyFor = new Map<string, PatientReply>();
  for (const r of openReplies) if (!replyFor.has(r.course)) replyFor.set(r.course, r);
  const toTreat = d.sessions.filter((s) => ["scheduled", "arrived", "in_room"].includes(s.status)).length;
  const byId = new Map(d.sessions.map((s) => [s.id, s]));
  const nextIds = new Set(d.machines.map((m) => m.queue?.next).filter(Boolean));
  // Patients earlier in the plan on the same machine who are still to come or waiting.
  const aheadOf = (s: SessionRow) =>
    d.sessions.filter((x) => x.machine === s.machine && x.id !== s.id && ["scheduled", "arrived"].includes(x.status) && x.start < s.start);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" aria-label={tr("prev_day", "Previous working day")} onClick={() => setDate(workingDay(addDays(date, -1), -1))}>
          <ChevronLeft />
        </Button>
        <Input type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} className="w-44" />
        <Button variant="outline" size="icon" aria-label={tr("next_day", "Next working day")} onClick={() => setDate(workingDay(addDays(date, 1)))}>
          <ChevronRight />
        </Button>
        {!isToday && (
          <Button variant="ghost" size="sm" onClick={() => setDate(config.today)}>
            {tr("back_to_today", "Back to today")}
          </Button>
        )}
        <span className="text-sm font-medium text-gray-700">{longDate(date)}</span>
      </div>

      {pending.map((t) => (
        <Notice
          key={t.id}
          kind="warn"
          title={tr("triage_pending", "{{machine}} breakdown: a proposal is waiting for approval", { machine: t.proposal.machine_name })}
          action={
            <Button size="sm" variant="warning" onClick={() => navigate(`/facility/${facilityId}/radsmart/breakdown`)}>
              {tr("review", "Review")}
            </Button>
          }
        >
          {t.proposal.rule}
        </Notice>
      ))}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {d.machines.map((m) => (
          <Card
            key={m.id}
            title={
              <span className="flex items-center gap-2">
                {m.name}
                <Badge tone={m.status === "online" ? "green" : "red"}>
                  {m.status === "online" ? tr("online", "Online") : tr("offline", "Offline")}
                </Badge>
              </span>
            }
            action={
              canOperate && isToday ? (
                m.status === "online" ? (
                  <Button size="sm" variant="outline" onClick={() => navigate(`/facility/${facilityId}/radsmart/breakdown?machine=${m.code}`)}>
                    <Wrench />
                    {tr("report_breakdown", "Report breakdown")}
                  </Button>
                ) : (
                  <Button size="sm" onClick={() => online.mutate(m)} disabled={online.isPending}>
                    <Power />
                    {tr("back_online", "Back online")}
                  </Button>
                )
              ) : null
            }
          >
            <dl className="grid grid-cols-3 gap-2 text-sm">
              <Metric label={tr("m_sessions", "Sessions")} value={m.sessions ?? 0} />
              <Metric label={tr("m_new_starts", "New starts")} value={m.new_starts ?? 0} />
              <Metric label={tr("m_after_17", "After 17:00")} value={m.after_17 ?? 0} />
              <Metric label={tr("m_last_end", "Last finishes")} value={m.last_end ?? "—"} />
              <Metric label={tr("m_booked", "Booked")} value={`${Math.round((m.booked_min ?? 0) / 60)} h`} />
              <Metric
                label={tr("m_room", "Free for new starts")}
                value={`${m.new_start_room_min ?? 0} min`}
                hint={tr("m_room_hint", "Gaps of at least 30 min before 17:00")}
              />
            </dl>
            {m.status === "offline" && m.expected_back && (
              <p className="mt-3 text-xs text-danger-700">{tr("expected_back", "Expected back {{time}}", { time: clockTime(m.expected_back) })}</p>
            )}
            {isToday && m.status === "online" && m.queue && (
              <Queue
                q={m.queue}
                byId={byId}
                canOperate={canOperate}
                busy={step.isPending}
                onTakeIn={(id) => step.mutate({ id, action: "room", reason: tr("reason_queue", "Next in the queue") })}
              />
            )}
          </Card>
        ))}
      </div>

      {d.check.violations.length === 0 ? (
        <Notice
          kind="ok"
          title={
            d.check.sessions_checked
              ? tr("check_ok", "All {{rules}} hard rules hold for the {{n}} patients still to be treated", { rules: d.check.rules_checked, n: d.check.sessions_checked })
              : tr("check_none", "Nothing left to treat on this day")
          }
          action={
            canOperate && toTreat > 0 && d.approval?.status !== "approved" ? (
              <Button size="sm" onClick={() => approve.mutate()} disabled={approve.isPending}>
                {tr("approve_day", "Approve the plan")}
              </Button>
            ) : d.approval?.status === "approved" ? (
              <Badge tone="green">{tr("approved_by", "Approved by {{who}}", { who: d.approval.by ?? "—" })}</Badge>
            ) : null
          }
        >
          {tr("check_list", "Standing slots, new starts before 17:00, the doctor's time windows, one patient per machine, accessories, blood irradiation time and the hospice window.")}
        </Notice>
      ) : (
        <Notice kind="error" title={tr("check_failed", "The plan breaks a hard rule; fix it before approving")}>
          <ul className="list-disc pl-4">
            {d.check.violations.map((v) => (
              <li key={v}>{v.split(":")[0]}</li>
            ))}
          </ul>
        </Notice>
      )}

      {openReplies.length > 0 && <Replies replies={openReplies} facilityId={facilityId} canOperate={canOperate} />}

      <Card title={tr("timeline", "The day on each machine")}>
        <Timeline sessions={d.sessions} machines={d.machines} day={config.day} now={isToday ? nowMinutes() : undefined} />
      </Card>

      <Card
        title={tr("sessions_title", "Patients ({{n}})", { n: d.sessions.length })}
        action={
          <div className="flex flex-wrap gap-1">
            {(
              [
                ["all", tr("f_all", "All")],
                ["to_come", tr("f_to_come", "To come")],
                ["waiting", tr("f_waiting", "Here now")],
                ["done", tr("f_done", "Finished")],
              ] as const
            ).map(([k, label]) => (
              <Button key={k} size="xs" variant={filter === k ? "primary" : "ghost"} onClick={() => setFilter(k)}>
                {label}
              </Button>
            ))}
          </div>
        }
      >
        {rows.length === 0 ? (
          <Empty>{tr("no_sessions", "No patients in this list")}</Empty>
        ) : (
          <Table
            stack
            head={[
              tr("h_time", "Time"),
              tr("h_patient", "Patient"),
              tr("h_fraction", "Fraction"),
              tr("h_treatment", "Treatment"),
              tr("h_needs", "Needs"),
              tr("h_in_out", "In / out"),
              tr("h_status", "Status"),
              "",
            ]}
          >
            {rows.map((s) => (
              <SessionLine
                key={s.id}
                s={s}
                facilityId={facilityId}
                statusLabel={statusLabel}
                reply={replyFor.get(s.course)}
                canOperate={canOperate && isToday}
                isNext={nextIds.has(s.id)}
                ahead={["scheduled", "arrived"].includes(s.status) ? aheadOf(s) : []}
                busy={(step.isPending && step.variables?.id === s.id) || (decide.isPending && decide.variables?.id === s.offer?.id)}
                onStep={(action, reason) => step.mutate({ id: s.id, action, reason })}
                onDecide={(decision) => s.offer && decide.mutate({ id: s.offer.id, decision })}
              />
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

export function useBandName() {
  const tr = useT();
  return (b: Band | "") =>
    ({ morning: tr("band_morning", "morning"), afternoon: tr("band_afternoon", "afternoon"), evening: tr("band_evening", "evening") })[b as Band] ?? tr("band_any", "any time");
}

/** Who to call next on a machine, who is in the room, and how far it runs behind. */
function Queue({ q, byId, canOperate, busy, onTakeIn }: {
  q: NonNullable<MachineInfo["queue"]>;
  byId: Map<string, SessionRow>;
  canOperate: boolean;
  busy: boolean;
  onTakeIn: (id: string) => void;
}) {
  const tr = useT();
  const next = q.next ? byId.get(q.next) : undefined;
  const room = q.in_room ? byId.get(q.in_room) : undefined;
  const behind = q.behind_min;
  return (
    <div className="mt-3 flex flex-col gap-1.5 rounded-md border border-gray-200 bg-gray-50 p-2 text-sm">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-xs text-gray-500">{tr("q_in_room", "In the room")}</span>
        <span className="font-medium">{room ? room.patient_name : tr("q_free", "free")}</span>
        {behind != null && (
          <Badge tone={behind >= 5 ? "amber" : "green"} className="ml-auto" title={tr("q_behind_hint", "The longest anyone here has waited past their time")}>
            {behind >= 5 ? tr("q_behind", "{{n}} min behind", { n: behind }) : tr("q_on_time", "on time")}
          </Badge>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-xs text-gray-500">{tr("q_next", "Call next")}</span>
        {next ? (
          <>
            <span className="font-medium">{next.patient_name}</span>
            <span className="text-xs tabular-nums text-gray-500">{next.time}</span>
            {canOperate && !room && (
              <Button size="xs" className="ml-auto" onClick={() => onTakeIn(next.id)} disabled={busy}>
                <ArrowRightCircle />
                {tr("q_take_in", "Take in")}
              </Button>
            )}
          </>
        ) : (
          <span className="text-xs text-gray-500">{q.waiting ? tr("q_none_ready", "nobody ready yet") : tr("q_nobody", "nobody waiting")}</span>
        )}
      </div>
      <p className="text-xs text-gray-500">
        {tr("q_counts", "{{waiting}} waiting · {{away}} past their time, not here yet", { waiting: q.waiting, away: q.not_here })}
      </p>
    </div>
  );
}

export function useReplyText() {
  const tr = useT();
  const bandName = useBandName();
  return (r: PatientReply) =>
    ({
      on_way: tr("r_on_way", "On the way"),
      late: r.minutes ? tr("r_late_n", "Late, about {{n}} min", { n: r.minutes }) : tr("r_late", "Running late"),
      not_today: tr("r_not_today", "Cannot come today"),
      other_time: r.band
        ? tr("r_other_band", "Asks for the {{band}}", { band: bandName(r.band) })
        : r.wanted
          ? tr("r_other_n", "Asks for {{time}}", { time: r.wanted })
          : tr("r_other", "Asks for another time"),
    })[r.kind];
}

const REPLY_TONE: Record<PatientReply["kind"], Tone> = { on_way: "blue", late: "amber", not_today: "red", other_time: "violet" };

/** What patients said on their own page today; staff act and mark each one done. */
function Replies({ replies, facilityId, canOperate }: { replies: PatientReply[]; facilityId: string; canOperate: boolean }) {
  const tr = useT();
  const qc = useQueryClient();
  const text = useReplyText();
  const done = useMutation({
    mutationFn: (id: string) => API.replyDone(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["care_radsmart", "replies"] }),
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Smartphone className="size-4" />
          {tr("replies_title", "From patients' phones ({{n}})", { n: replies.length })}
        </span>
      }
    >
      <ul className="divide-y divide-gray-100">
        {replies.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm first:pt-0 last:pb-0">
            <Badge tone={REPLY_TONE[r.kind]}>{text(r)}</Badge>
            <PageLink href={`/facility/${facilityId}/radsmart/courses/${r.course}`}>{r.patient_name}</PageLink>
            <span className="text-xs text-gray-500">
              {r.hospital_number}
              {r.time && ` · ${tr("treat_at", "treatment {{time}}", { time: r.time })}`} · {clockTime(r.created_date)}
            </span>
            {r.reason && <span className="text-xs text-gray-600">“{r.reason}”</span>}
            {r.channel === "telegram" && <Badge tone="gray">{tr("via_telegram", "Telegram")}</Badge>}
            <span className="ml-auto flex items-center gap-2">
              {r.kind === "other_time" && r.slot_request_status === "proposed" && (
                <PageLink href={`/facility/${facilityId}/radsmart/courses`} className="text-xs">
                  {tr("decide_request", "Decide the request")}
                </PageLink>
              )}
              {canOperate && (
                <Button size="xs" variant="ghost" onClick={() => done.mutate(r.id)} disabled={done.isPending}>
                  <Check />
                  {tr("reply_done", "Done")}
                </Button>
              )}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** An open request for another standing time, beside the patient: RAD-SMART's
 * offer of a time inside their preferred part of the day (staff ask the patient),
 * or the patient's own request. */
function OfferBox({ offer, bandName, canOperate, busy, onDecide }: {
  offer: NonNullable<SessionRow["offer"]>;
  bandName: (b: Band | "") => string;
  canOperate: boolean;
  busy: boolean;
  onDecide: (d: "approve" | "reject") => void;
}) {
  const tr = useT();
  const mine = offer.source === "radsmart";
  const when = shortDate(offer.from_date);
  return (
    <div className="mt-2 max-w-52 rounded-md border border-alert-200 bg-alert-50 p-2 text-xs text-alert-900 max-md:max-w-none">
      <p className="flex items-start gap-1">
        <Sparkles className="mt-0.5 size-3 shrink-0" />
        <span>
          {mine
            ? tr("offer_text", "A {{band}} slot is free: {{time}} every day from {{date}}. Ask the patient.", { band: bandName(offer.band), time: offer.time ?? "—", date: when })
            : offer.time
              ? tr("request_text", "Asked for {{wanted}}: {{time}} from {{date}}", { wanted: offer.band ? bandName(offer.band) : offer.time, time: offer.time, date: when })
              : offer.problem ?? tr("request_open", "Asked for another time")}
        </span>
      </p>
      {!mine && offer.band && offer.in_band === false && (
        <p className="mt-1 text-alert-800">{tr("not_in_band_yet", "Nothing inside the {{band}} is free yet: RAD-SMART offers one when it frees up.", { band: bandName(offer.band) })}</p>
      )}
      {canOperate && offer.time && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          <Button size="xs" onClick={() => onDecide("approve")} disabled={busy}>
            {mine ? tr("patient_agrees", "Patient agrees") : tr("approve_time", "Approve {{time}}", { time: offer.time })}
          </Button>
          <Button size="xs" variant="outline" onClick={() => onDecide("reject")} disabled={busy}>
            {mine ? tr("patient_stays", "Prefers to stay") : tr("decline", "Decline")}
          </Button>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div title={hint}>
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="font-semibold tabular-nums text-gray-900">{value}</dd>
    </div>
  );
}

function SessionLine({
  s,
  facilityId,
  statusLabel,
  reply,
  canOperate,
  isNext,
  ahead,
  busy,
  onStep,
  onDecide,
}: {
  s: SessionRow;
  facilityId: string;
  statusLabel: (s: string) => string;
  reply?: PatientReply;
  canOperate: boolean;
  isNext: boolean;
  ahead: SessionRow[];
  busy: boolean;
  onStep: (a: Step, reason?: string) => void;
  onDecide: (d: "approve" | "reject") => void;
}) {
  const tr = useT();
  const replyText = useReplyText();
  const bandName = useBandName();
  const [asking, setAsking] = useState(false);
  const gone = ["sent_home", "postponed", "missed", "cancelled"].includes(s.status);
  const cautions = s.cautions ?? [];
  // Taking someone in ahead of the plan, or with something to check: ask why (optional), never block.
  const takeIn = () => (ahead.length || cautions.length ? setAsking(true) : onStep("room"));
  const waiting = ahead.filter((x) => x.status === "arrived").length;
  const reasons = [
    tr("reason_early", "Came early"),
    tr("reason_not_here", "Next patient not here"),
    tr("reason_clinical", "Clinical reason"),
    tr("reason_other", "Other"),
  ];
  return (
    // Below md each row is a card: time | patient, fraction | treatment, needs, in/out, status | actions.
    <tr
      className={cn(
        "max-md:grid max-md:grid-cols-[6rem_1fr] max-md:rounded-lg max-md:border max-md:border-gray-200 max-md:bg-white max-md:py-1 max-md:[&>td]:px-2 max-md:[&>td]:py-1",
        gone && "bg-gray-50 text-gray-500 max-md:bg-gray-50",
      )}
    >
      <td className="px-3 py-2 align-top">
        <div className="font-semibold tabular-nums">{s.time}</div>
        {s.moved_today ? (
          <div className="text-xs text-warning-800">{tr("was", "was {{time}}", { time: s.planned_time })}</div>
        ) : (
          <div className="text-xs text-gray-500">{tr("report_at", "report {{time}}", { time: s.report })}</div>
        )}
      </td>
      <td className="max-w-60 px-3 py-2 align-top max-md:max-w-none">
        <PageLink href={`/facility/${facilityId}/radsmart/courses/${s.course}`}>{s.patient_name}</PageLink>
        <div className="text-xs text-gray-500">
          {s.hospital_number} · {s.age} {tr("years", "y")} · {s.language}
        </div>
        {reply && (
          <Badge tone={REPLY_TONE[reply.kind]} className="mt-1" title={reply.reason || undefined}>
            <Smartphone className="size-3" />
            {replyText(reply)}
          </Badge>
        )}
        <div className="mt-1 flex flex-wrap gap-1">
          {isNext && <Badge tone="blue">{tr("q_next", "Call next")}</Badge>}
          {s.late_by != null && s.late_by > 0 && <Badge tone="amber">{tr("not_here_yet", "Not here yet · {{n}} min past", { n: s.late_by })}</Badge>}
          {s.often_late && <Badge tone="gray" title={tr("often_late_hint", "Arrived after their treatment time in 3 of their last 5 visits")}>{tr("often_late", "Often late")}</Badge>}
          {s.out_of_turn && <Badge tone="violet" title={s.turn_note}>{tr("out_of_turn", "Out of turn")}</Badge>}
        </div>
        {s.offer && <OfferBox offer={s.offer} bandName={bandName} canOperate={canOperate} busy={busy} onDecide={onDecide} />}
      </td>
      <td className="px-3 py-2 align-top tabular-nums">
        {s.fraction}/{s.fractions}
        {s.kind === "new_start" && (
          <div>
            <Badge tone="green">{tr("kind_new_start", "New start")}</Badge>
          </div>
        )}
        {s.kind === "added" && (
          <div>
            <Badge tone="violet">{tr("kind_added", "Added fraction")}</Badge>
          </div>
        )}
      </td>
      <td className="max-w-44 px-3 py-2 align-top max-md:max-w-none">
        <div>{s.technique}</div>
        <div className="text-xs text-gray-500">
          {s.diagnosis} · {Math.round(s.minutes)} min
        </div>
      </td>
      <td className={cn("max-w-44 px-3 py-2 align-top max-md:col-span-2 max-md:max-w-none", s.flags.length === 0 && "max-md:hidden")}>
        <div className="flex flex-wrap gap-1">
          {s.flags.slice(0, 3).map((f) => (
            <Badge key={f}>{f}</Badge>
          ))}
          {s.flags.length > 3 && <Badge title={s.flags.slice(3).join(", ")}>+{s.flags.length - 3}</Badge>}
        </div>
      </td>
      <td className={cn("px-3 py-2 align-top text-xs tabular-nums text-gray-600 max-md:col-span-2 max-md:flex max-md:gap-3", !s.arrived_at && "max-md:hidden")}>
        <div>
          {tr("arr", "arr")} {clockTime(s.arrived_at)}
        </div>
        <div>
          {clockTime(s.in_room_at)} – {clockTime(s.out_at)}
        </div>
      </td>
      <td className="px-3 py-2 align-top">
        <Badge tone={STATUS_TONE[s.status]}>{statusLabel(s.status)}</Badge>
        {s.note && <div className="mt-1 max-w-32 text-xs text-gray-500">{s.note}</div>}
        {s.out_of_turn && s.turn_note && <div className="mt-1 max-w-32 text-xs text-alert-700">{s.turn_note}</div>}
        {cautions.map((c) => (
          <div key={c} className="mt-1 max-w-32 text-xs text-warning-800">
            {c}
          </div>
        ))}
      </td>
      <td className={cn("px-3 py-2 align-top md:sticky md:right-0 md:shadow-[-6px_0_6px_-6px_rgb(0_0_0/0.15)]", gone ? "bg-gray-50" : "bg-white")}>
        {canOperate && (
          <div className="flex flex-wrap justify-end gap-1">
            {s.status === "scheduled" && (
              <>
                <Button size="xs" onClick={() => onStep("arrive")} disabled={busy}>
                  {tr("a_arrived", "Arrived")}
                </Button>
                <Button
                  size="xs"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => window.confirm(tr("confirm_send_home", "Send {{name}} back today? The fraction is added at the end of the course.", { name: s.patient_name })) && onStep("send-home")}
                >
                  {tr("a_send_home", "Not today")}
                </Button>
              </>
            )}
            {s.status === "arrived" && !asking && (
              <Button size="xs" variant={isNext || !ahead.length ? "primary" : "outline"} onClick={takeIn} disabled={busy}>
                {tr("a_in_room", "In room")}
              </Button>
            )}
            {asking && (
              <div className="flex w-full max-w-48 flex-col items-end gap-1 rounded-md border border-alert-200 bg-alert-50 p-2 text-left">
                <p className="w-full text-xs text-alert-900">
                  {ahead.length
                    ? tr("ahead_of", "Due {{time}}, ahead of {{n}} due before them ({{waiting}} here). Why?", { time: s.time, n: ahead.length, waiting })
                    : tr("check_first", "Check first:")}
                </p>
                {cautions.map((c) => (
                  <p key={c} className="w-full text-xs text-warning-800">
                    {c}
                  </p>
                ))}
                <div className="flex flex-wrap justify-end gap-1">
                  {ahead.length > 0 &&
                    reasons.map((r) => (
                      <Button key={r} size="xs" variant="outline" disabled={busy} onClick={() => (setAsking(false), onStep("room", r))}>
                        {r}
                      </Button>
                    ))}
                  <Button size="xs" disabled={busy} onClick={() => (setAsking(false), onStep("room"))}>
                    {ahead.length ? tr("skip_reason", "Take in") : tr("take_in_anyway", "Take in")}
                  </Button>
                  <Button size="xs" variant="ghost" onClick={() => setAsking(false)}>
                    {tr("cancel", "Cancel")}
                  </Button>
                </div>
              </div>
            )}
            {s.status === "in_room" && (
              <Button size="xs" onClick={() => onStep("done")} disabled={busy}>
                {tr("a_out", "Out")}
              </Button>
            )}
            {["arrived", "in_room", "done"].includes(s.status) && (
              <Button size="xs" variant="ghost" onClick={() => onStep("undo")} disabled={busy} aria-label={tr("undo", "Undo")} title={tr("undo", "Undo")}>
                <RotateCcw />
              </Button>
            )}
          </div>
        )}
      </td>
    </tr>
  );
}

