import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, Power, RotateCcw, Smartphone, Wrench } from "lucide-react";
import { useState } from "react";
import { navigate } from "raviger";
import { toast } from "sonner";

import Layout, { PageLink } from "@/components/Layout";
import Timeline from "@/components/Timeline";
import { Button } from "@/components/ui/button";
import { Badge, Card, Empty, Input, Notice, Spinner, Table, type Tone } from "@/components/ui/primitives";
import { addDays, clockTime, longDate, nowMinutes, workingDay } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { keys } from "@/lib/useConfig";
import { cn } from "@/lib/utils";
import { API, type Config, type MachineInfo, type PatientReply, type SessionRow } from "@/utils/api";

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
    mutationFn: ({ id, action }: { id: string; action: "arrive" | "room" | "done" | "undo" | "send-home" }) => API.session(id, action),
    onSuccess: refresh,
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
                busy={step.isPending && step.variables?.id === s.id}
                onStep={(action) => step.mutate({ id: s.id, action })}
              />
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

export function useReplyText() {
  const tr = useT();
  return (r: PatientReply) =>
    ({
      on_way: tr("r_on_way", "On the way"),
      late: r.minutes ? tr("r_late_n", "Late, about {{n}} min", { n: r.minutes }) : tr("r_late", "Running late"),
      not_today: tr("r_not_today", "Cannot come today"),
      other_time: r.wanted ? tr("r_other_n", "Asks for {{time}}", { time: r.wanted }) : tr("r_other", "Asks for another time"),
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
  busy,
  onStep,
}: {
  s: SessionRow;
  facilityId: string;
  statusLabel: (s: string) => string;
  reply?: PatientReply;
  canOperate: boolean;
  busy: boolean;
  onStep: (a: "arrive" | "room" | "done" | "undo" | "send-home") => void;
}) {
  const tr = useT();
  const replyText = useReplyText();
  const gone = ["sent_home", "postponed", "missed", "cancelled"].includes(s.status);
  return (
    <tr className={cn(gone && "bg-gray-50 text-gray-500")}>
      <td className="px-3 py-2 align-top">
        <div className="font-semibold tabular-nums">{s.time}</div>
        {s.moved_today ? (
          <div className="text-xs text-warning-800">{tr("was", "was {{time}}", { time: s.planned_time })}</div>
        ) : (
          <div className="text-xs text-gray-500">{tr("report_at", "report {{time}}", { time: s.report })}</div>
        )}
      </td>
      <td className="px-3 py-2 align-top">
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
      <td className="px-3 py-2 align-top">
        <div>{s.technique}</div>
        <div className="text-xs text-gray-500">
          {s.diagnosis} · {Math.round(s.minutes)} min
        </div>
      </td>
      <td className="max-w-56 px-3 py-2 align-top">
        <div className="flex flex-wrap gap-1">
          {s.flags.slice(0, 3).map((f) => (
            <Badge key={f}>{f}</Badge>
          ))}
        </div>
      </td>
      <td className="px-3 py-2 align-top text-xs tabular-nums text-gray-600">
        <div>
          {tr("arr", "arr")} {clockTime(s.arrived_at)}
        </div>
        <div>
          {clockTime(s.in_room_at)} – {clockTime(s.out_at)}
        </div>
      </td>
      <td className="px-3 py-2 align-top">
        <Badge tone={STATUS_TONE[s.status]}>{statusLabel(s.status)}</Badge>
        {s.note && <div className="mt-1 max-w-48 text-xs text-gray-500">{s.note}</div>}
      </td>
      <td className="px-3 py-2 align-top">
        {canOperate && (
          <div className="flex justify-end gap-1">
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
            {s.status === "arrived" && (
              <Button size="xs" onClick={() => onStep("room")} disabled={busy}>
                {tr("a_in_room", "In room")}
              </Button>
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

