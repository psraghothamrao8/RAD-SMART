import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import Layout from "@/components/Layout";
import { Card, Field, Input, Notice, Spinner, Stat } from "@/components/ui/primitives";
import { addDays, shortDate } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { keys } from "@/lib/useConfig";
import { API, type Config, type Insights as InsightsData } from "@/utils/api";

export default function Insights({ facilityId }: { facilityId: string }) {
  const tr = useT();
  return (
    <Layout facilityId={facilityId} title={tr("insights_title", "How long patients wait")}>
      {(config) => <Body facilityId={facilityId} config={config} />}
    </Layout>
  );
}

function Body({ facilityId, config }: { facilityId: string; config: Config }) {
  const tr = useT();
  const [from, setFrom] = useState(addDays(config.today, -28));
  const [to, setTo] = useState(config.today);
  const q = useQuery({ queryKey: keys.insights(facilityId, from, to), queryFn: () => API.insights(facilityId, from, to) });
  if (q.isLoading) return <Spinner label={tr("loading", "Loading…")} />;
  if (!q.data) return <Notice kind="error">{String((q.error as Error)?.message)}</Notice>;
  const d = q.data;
  const p90 = d.wait_p90;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label={tr("from", "From")}>
          <Input type="date" value={from} max={to} onChange={(e) => e.target.value && setFrom(e.target.value)} className="w-44" />
        </Field>
        <Field label={tr("to", "To")}>
          <Input type="date" value={to} min={from} onChange={(e) => e.target.value && setTo(e.target.value)} className="w-44" />
        </Field>
        <p className="pb-2 text-sm text-gray-600">{tr("timed", "{{n}} treatments with arrival and room-in times recorded", { n: d.sessions_timed })}</p>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label={tr("kpi_p90", "Wait, 90th percentile")}
          value={p90 === null ? "—" : `${Math.round(p90)} min`}
          sub={tr("kpi_p90_sub", "Baseline {{b}} min, target {{t}} min", { b: d.kpi.baseline_min, t: d.kpi.target_min })}
          tone={p90 === null ? undefined : p90 <= d.kpi.target_min ? "good" : "bad"}
        />
        <Stat label={tr("kpi_median", "Wait, median")} value={d.wait_median === null ? "—" : `${Math.round(d.wait_median)} min`} sub={tr("arrival_room", "arrival to treatment room")} />
        <Stat label={tr("kpi_15", "In within ±15 min of the slot")} value={d.within_15_pct === null ? "—" : `${Math.round(d.within_15_pct)}%`} />
        <Stat label={tr("kpi_late", "More than 60 min late")} value={d.late_60_pct === null ? "—" : `${Math.round(d.late_60_pct)}%`} />
        <Stat label={tr("kpi_session", "Session length, median")} value={d.session_minutes_median === null ? "—" : `${d.session_minutes_median} min`} sub={tr("room_in_out", "room in to room out")} />
        <Stat label={tr("kpi_sent", "Sent back")} value={d.sent_home} sub={tr("kpi_sent_sub", "breakdowns or not today")} />
        <Stat label={tr("kpi_postponed", "New starts postponed")} value={d.postponed} />
        <Stat label={tr("kpi_added", "Fractions added at the end")} value={d.added} />
      </div>
      <Card title={tr("chart_title", "Wait at the 90th percentile, by day")}>
        <DayChart data={d} />
        <p className="mt-2 text-xs text-gray-500">
          {tr("chart_note", "The baseline is from {{src}}. Each bar is one treatment day; hover for the numbers.", { src: d.kpi.baseline_source })}
        </p>
      </Card>
    </div>
  );
}

function DayChart({ data }: { data: InsightsData }) {
  const tr = useT();
  const days = data.by_day;
  if (!days.length) return <p className="text-sm text-gray-500">{tr("no_days", "No timed treatments in this range")}</p>;
  const W = 900;
  const H = 260;
  const L = 44;
  const B = 28;
  const T = 12;
  const max = Math.ceil(Math.max(data.kpi.baseline_min, ...days.map((d) => d.wait_p90)) / 30) * 30 + 10;
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const step = (W - L - 8) / days.length;
  const bw = Math.max(4, Math.min(28, step - 4));
  const ticks = [];
  for (let v = 0; v <= max; v += 30) ticks.push(v);
  const labelEvery = Math.ceil(days.length / 10);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={tr("chart_title", "Wait at the 90th percentile, by day")}>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={L} x2={W - 8} y1={y(v)} y2={y(v)} stroke="#f3f4f6" />
          <text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#6b7280">
            {v}
          </text>
        </g>
      ))}
      <text x={4} y={T + 4} fontSize="11" fill="#6b7280">
        min
      </text>
      {days.map((d, i) => {
        const x = L + i * step + (step - bw) / 2;
        return (
          <g key={d.date}>
            <rect x={x} y={y(d.wait_p90)} width={bw} height={Math.max(0, y(0) - y(d.wait_p90))} rx="3" fill="#0369a1">
              <title>{`${shortDate(d.date)}: P90 ${Math.round(d.wait_p90)} min, median ${Math.round(d.wait_median)} min, ${d.n} treatments`}</title>
            </rect>
            {i % labelEvery === 0 && (
              <text x={x + bw / 2} y={H - 10} textAnchor="middle" fontSize="10" fill="#6b7280">
                {shortDate(d.date).split(" ").slice(1).join(" ")}
              </text>
            )}
          </g>
        );
      })}
      <line x1={L} x2={W - 8} y1={y(data.kpi.baseline_min)} y2={y(data.kpi.baseline_min)} stroke="#b91c1c" strokeDasharray="5 4" strokeWidth="1.5" />
      <text x={W - 10} y={y(data.kpi.baseline_min) - 5} textAnchor="end" fontSize="11" fill="#b91c1c">
        {tr("baseline_line", "baseline {{v}} min", { v: data.kpi.baseline_min })}
      </text>
      <line x1={L} x2={W - 8} y1={y(data.kpi.target_min)} y2={y(data.kpi.target_min)} stroke="#046c4e" strokeDasharray="5 4" strokeWidth="1.5" />
      <text x={W - 10} y={y(data.kpi.target_min) - 5} textAnchor="end" fontSize="11" fill="#046c4e">
        {tr("target_line", "target {{v}} min (25% lower)", { v: data.kpi.target_min })}
      </text>
    </svg>
  );
}
