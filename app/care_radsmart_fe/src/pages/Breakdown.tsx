import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Power, Wrench, XCircle } from "lucide-react";
import { useState } from "react";
import { useQueryParams } from "raviger";
import { toast } from "sonner";

import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Badge, Card, Empty, Field, Input, Notice, Select, Spinner, Stat, Table, type Tone } from "@/components/ui/primitives";
import { durationLabel, nowHM } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { keys } from "@/lib/useConfig";
import { cn } from "@/lib/utils";
import { API, type Config, type MachineInfo, type Triage, type TriageAction } from "@/utils/api";

const DURATIONS = [15, 30, 45, 60, 90, 120, 180, 240, 360, 480, 1440, 2880];

const ACTION_TONE: Record<string, Tone> = {
  treat: "green",
  treat_later: "blue",
  new_time: "amber",
  start_next_day: "violet",
  send_home: "red",
  do_not_travel: "red",
  doctor_decides: "violet",
};
const ACTION_ORDER = ["treat", "treat_later", "new_time", "do_not_travel", "send_home", "start_next_day", "doctor_decides"];

export default function Breakdown({ facilityId }: { facilityId: string }) {
  const tr = useT();
  return (
    <Layout facilityId={facilityId} title={tr("breakdown_title", "Machine breakdown")}>
      {(config) => <BreakdownBody facilityId={facilityId} config={config} />}
    </Layout>
  );
}

function BreakdownBody({ facilityId, config }: { facilityId: string; config: Config }) {
  const tr = useT();
  const qc = useQueryClient();
  const [params] = useQueryParams<{ machine?: string }>();
  const canOperate = !!config.permissions?.can_operate_radsmart;
  const day = useQuery({ queryKey: keys.day(facilityId, config.today), queryFn: () => API.day(facilityId, config.today) });
  const triages = useQuery({ queryKey: keys.triages(facilityId, config.today), queryFn: () => API.triages(facilityId, config.today) });
  const machines = day.data?.machines ?? config.machines;
  const [code, setCode] = useState(params.machine ?? machines[0]?.code ?? "");
  const machine = machines.find((m) => m.code === code) ?? machines[0];

  const online = useMutation({
    mutationFn: (m: MachineInfo) => API.machineStatus(m.id, { status: "online" }),
    onSuccess: () => {
      toast.success(tr("machine_online", "Machine is back online"));
      qc.invalidateQueries({ queryKey: ["care_radsmart"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (day.isLoading || triages.isLoading) return <Spinner label={tr("loading", "Loading…")} />;
  const list = (triages.data ?? []).filter((t) => !machine || t.machine === machine.code);
  const open = list.find((t) => t.status === "proposed");
  const latest = list[0];

  return (
    <div className="flex flex-col gap-4">
      <Notice kind="info" title={tr("rule_title", "How RAD-SMART responds")}>
        {tr(
          "rule_text",
          "Up to {{short}} min: nobody is sent home; everyone is treated today with up to {{short}} min of overtime. Longer: patients are sent back, as many as the expected downtime needs; patients who have not left home are asked to wait for a new time; new starts wait until the machine works. A technologist or doctor approves before anything changes.",
          { short: config.day.downtime_short_max_min },
        )}
      </Notice>

      {machines.length > 1 && (
        <Field label={tr("machine", "Machine")} className="max-w-xs">
          <Select value={code} onChange={(e) => setCode(e.target.value)}>
            {machines.map((m) => (
              <option key={m.code} value={m.code}>
                {m.name}
              </option>
            ))}
          </Select>
        </Field>
      )}

      {machine && (
        <Card
          title={
            <span className="flex items-center gap-2">
              {machine.name}
              <Badge tone={machine.status === "online" ? "green" : "red"}>{machine.status === "online" ? tr("online", "Online") : tr("offline", "Offline")}</Badge>
            </span>
          }
          action={
            canOperate && machine.status === "offline" ? (
              <Button size="sm" onClick={() => online.mutate(machine as MachineInfo)} disabled={online.isPending}>
                <Power />
                {tr("back_online", "Back online")}
              </Button>
            ) : null
          }
        >
          {canOperate ? (
            <FaultForm facilityId={facilityId} machine={machine as MachineInfo} offline={machine.status === "offline"} />
          ) : (
            <p className="text-sm text-gray-600">{tr("operate_only", "Technologists and doctors report breakdowns.")}</p>
          )}
        </Card>
      )}

      {open ? (
        <TriageView t={open} facilityId={facilityId} canOperate={canOperate} />
      ) : latest ? (
        <TriageView t={latest} facilityId={facilityId} canOperate={false} />
      ) : (
        <Empty>{tr("no_breakdowns", "No breakdown reported today")}</Empty>
      )}

      {list.length > 1 && (
        <Card title={tr("history", "Earlier proposals today")}>
          <Table head={[tr("h_reported", "Reported"), tr("h_expected", "Expected"), tr("h_outcome", "Outcome"), tr("h_status", "Status"), tr("h_by", "By")]}>
            {list.slice(open ? 0 : 1).filter((t) => t.id !== open?.id).map((t) => (
              <tr key={t.id}>
                <td className="px-3 py-1.5 tabular-nums">{t.proposal.fault_time}</td>
                <td className="px-3 py-1.5">{durationLabel(t.expected_minutes)}</td>
                <td className="px-3 py-1.5 text-xs text-gray-600">{summary(t, tr)}</td>
                <td className="px-3 py-1.5">
                  <Badge tone={t.status === "approved" ? "green" : "gray"}>{t.status}</Badge>
                </td>
                <td className="px-3 py-1.5 text-xs">{t.decided_by ?? "—"}</td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
    </div>
  );
}

function summary(t: Triage, tr: ReturnType<typeof useT>) {
  const c = t.proposal.counts;
  const back = (c.send_home ?? 0) + (c.do_not_travel ?? 0);
  return tr("summary", "{{back}} sent back, {{moved}} new times, {{next}} new starts moved", {
    back,
    moved: (c.new_time ?? 0) + (c.treat_later ?? 0),
    next: c.start_next_day ?? 0,
  });
}

function FaultForm({ facilityId, machine, offline }: { facilityId: string; machine: MachineInfo; offline: boolean }) {
  const tr = useT();
  const qc = useQueryClient();
  const [at, setAt] = useState(nowHM());
  const [minutes, setMinutes] = useState(45);
  const [note, setNote] = useState("");
  const report = useMutation({
    mutationFn: async (): Promise<{ triage: Triage | null }> =>
      offline
        ? { triage: await API.retriage(facilityId, machine.id, minutes) }
        : API.machineStatus(machine.id, { status: "offline", expected_minutes: minutes, note, time: at }),
    onSuccess: (r) => {
      toast[r.triage ? "warning" : "success"](
        r.triage ? tr("proposal_ready", "RAD-SMART's proposal is ready for approval") : tr("offline_none", "Machine offline; nobody was booked"),
      );
      qc.invalidateQueries({ queryKey: ["care_radsmart"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        report.mutate();
      }}
    >
      {!offline && (
        <Field label={tr("fault_at", "Fault started at")}>
          <Input type="time" value={at} onChange={(e) => setAt(e.target.value)} className="w-32" required />
        </Field>
      )}
      <Field label={offline ? tr("revised", "Revised: back in (from now)") : tr("expected", "Expected downtime")}>
        <Select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} className="w-40">
          {DURATIONS.map((d) => (
            <option key={d} value={d}>
              {durationLabel(d)}
            </option>
          ))}
        </Select>
      </Field>
      {!offline && (
        <Field label={tr("fault_note", "What happened")} className="min-w-56 flex-1">
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={tr("fault_ph", "e.g. MLC fault, engineer called")} />
        </Field>
      )}
      <Button type="submit" variant={offline ? "outline" : "destructive"} disabled={report.isPending}>
        <Wrench />
        {report.isPending ? tr("planning", "Re-planning the day…") : offline ? tr("re_estimate", "Re-plan with this estimate") : tr("take_offline", "Take offline and propose")}
      </Button>
    </form>
  );
}

function TriageView({ t, facilityId, canOperate }: { t: Triage; facilityId: string; canOperate: boolean }) {
  const tr = useT();
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("changed");
  const p = t.proposal;
  const decide = useMutation({
    mutationFn: (d: "approve" | "reject") => API.decideTriage(facilityId, t.id, d),
    onSuccess: (_, d) => {
      toast.success(d === "approve" ? tr("triage_applied", "Applied: today's board and the patients' courses are updated") : tr("triage_rejected", "Proposal rejected; nothing changed"));
      qc.invalidateQueries({ queryKey: ["care_radsmart"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const actions = [...p.actions].sort((a, b) => ACTION_ORDER.indexOf(a.action) - ACTION_ORDER.indexOf(b.action) || a.time.localeCompare(b.time));
  const shown = filter === "changed" ? actions.filter((a) => a.action !== "treat") : actions;
  const c = p.counts;
  const back = (c.send_home ?? 0) + (c.do_not_travel ?? 0);
  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-2">
          {tr("triage_for", "{{machine}} down at {{time}} for {{len}}", { machine: p.machine_name, time: p.fault_time, len: durationLabel(p.expected_minutes) })}
          <Badge tone={t.status === "proposed" ? "amber" : t.status === "approved" ? "green" : "gray"}>{t.status}</Badge>
        </span>
      }
      action={
        canOperate && t.status === "proposed" ? (
          <div className="flex gap-2">
            <Button size="sm" onClick={() => decide.mutate("approve")} disabled={decide.isPending}>
              <CheckCircle2 />
              {tr("approve_apply", "Approve and notify")}
            </Button>
            <Button size="sm" variant="outline" onClick={() => decide.mutate("reject")} disabled={decide.isPending}>
              <XCircle />
              {tr("reject", "Reject")}
            </Button>
          </div>
        ) : t.decided_by ? (
          <span className="text-xs text-gray-500">{tr("decided_by", "{{status}} by {{who}}", { status: t.status, who: t.decided_by })}</span>
        ) : null
      }
    >
      <p className="text-sm text-gray-700">{p.rule}</p>
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label={tr("t_restart", "Machine back")} value={p.restart ?? tr("not_today", "not today")} />
        <Stat label={tr("t_treated", "Treated today")} value={(c.treat ?? 0) + (c.treat_later ?? 0) + (c.new_time ?? 0)} sub={tr("t_treated_sub", "{{n}} at a new time", { n: (c.treat_later ?? 0) + (c.new_time ?? 0) })} />
        <Stat label={tr("t_told", "Told a new time")} value={c.new_time ?? 0} sub={tr("t_told_sub", "not yet travelling")} />
        <Stat label={tr("t_back", "Sent back")} value={back} sub={tr("t_back_sub", "fraction added at the end")} tone={back ? "bad" : undefined} />
        <Stat label={tr("t_new_starts", "New starts moved")} value={c.start_next_day ?? 0} sub={tr("t_ns_sub", "to the next working day")} />
        <Stat label={tr("t_overtime", "Overtime")} value={`${Math.round(p.overtime_min)} min`} sub={tr("t_ends", "day may run to {{t}}", { t: p.allowed_end })} />
      </div>
      {(c.doctor_decides ?? 0) > 0 && (
        <div className="mt-3">
          <Notice kind="warn">{tr("doctor_flag", "{{n}} gap-sensitive or hospice patients cannot fit: the oncologist decides (another machine, a longer day or compensation).", { n: c.doctor_decides })}</Notice>
        </div>
      )}
      {p.check && p.check.violations.length > 0 && (
        <div className="mt-3">
          <Notice kind="error" title={tr("triage_check_fail", "The re-plan breaks a hard rule")}>{p.check.violations.join("; ")}</Notice>
        </div>
      )}
      <div className="mt-4 flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-gray-900">{tr("patients_affected", "Patients")}</p>
        <div className="flex gap-1">
          <Button size="xs" variant={filter === "changed" ? "primary" : "ghost"} onClick={() => setFilter("changed")}>
            {tr("f_changed", "Affected")}
          </Button>
          <Button size="xs" variant={filter === "all" ? "primary" : "ghost"} onClick={() => setFilter("all")}>
            {tr("f_all", "All")}
          </Button>
        </div>
      </div>
      <Table
        className="mt-2"
        head={[tr("h_was", "Booked"), tr("h_patient", "Patient"), tr("h_action", "RAD-SMART proposes"), tr("h_new", "New time"), tr("h_why", "Why"), ""]}
      >
        {shown.map((a) => (
          <ActionRow key={a.id} a={a} open={open === a.id} onToggle={() => setOpen(open === a.id ? null : a.id)} />
        ))}
      </Table>
      <p className="mt-2 text-xs text-gray-500">{tr("solve_time", "Re-planned in {{s}} s. Messages are sent only after approval.", { s: p.solve_seconds })}</p>
    </Card>
  );
}

function ActionRow({ a, open, onToggle }: { a: TriageAction; open: boolean; onToggle: () => void }) {
  const tr = useT();
  return (
    <>
      <tr className={cn(["send_home", "do_not_travel"].includes(a.action) && "bg-danger-50/40")}>
        <td className="px-3 py-2 tabular-nums">{a.time}</td>
        <td className="px-3 py-2">
          <div className="font-medium">{a.patient_name}</div>
          <div className="text-xs text-gray-500">
            {a.hospital_number} · {a.fraction}/{a.fractions}
            {a.kind === "new_start" && ` · ${tr("kind_new_start", "New start")}`}
            {a.present && ` · ${tr("here", "here now")}`}
          </div>
        </td>
        <td className="px-3 py-2">
          <Badge tone={ACTION_TONE[a.action]}>{a.label}</Badge>
        </td>
        <td className="px-3 py-2 tabular-nums">
          {a.new_time ?? "—"}
          {a.new_report && a.action === "new_time" && <div className="text-xs text-gray-500">{tr("report_at", "report {{time}}", { time: a.new_report })}</div>}
        </td>
        <td className="max-w-80 px-3 py-2 text-xs text-gray-600">{a.why}</td>
        <td className="px-3 py-2 text-right">
          {a.message && (
            <Button size="xs" variant="ghost" onClick={onToggle}>
              {open ? tr("hide", "Hide") : tr("message", "Message")}
            </Button>
          )}
        </td>
      </tr>
      {open && a.message && (
        <tr>
          <td colSpan={6} className="bg-gray-50 px-3 py-2 text-sm text-gray-700">
            <span className="text-xs font-semibold text-gray-500">{tr("message_to", "Message ({{lang}})", { lang: a.language })}: </span>
            {a.message}
          </td>
        </tr>
      )}
    </>
  );
}
