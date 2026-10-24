import { hm } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Config, SessionRow } from "@/utils/api";

const KIND_COLOUR: Record<string, string> = {
  new_start: "#046c4e",
  routine: "#0369a1",
  moved: "#d97706",
  added: "#7c3aed",
};

const W = 1100;
const LEFT = 64;
const ROW = 44;

/** The day on each machine: a bar per session, the 17:00 new-start line, blocks and now. */
export default function Timeline({
  sessions,
  machines,
  day,
  now,
}: {
  sessions: SessionRow[];
  machines: { code: string; name: string; status: string }[];
  day: Config["day"];
  now?: number;
}) {
  const tr = useT();
  const live = sessions.filter((s) => !["sent_home", "postponed", "missed", "cancelled"].includes(s.status));
  const lastEnd = Math.max(day.new_start_latest_end + 120, ...live.map((s) => s.start + s.minutes));
  const t0 = Math.floor((day.start - 30) / 60) * 60;
  const t1 = Math.ceil((lastEnd + 20) / 60) * 60;
  const x = (m: number) => LEFT + ((m - t0) / (t1 - t0)) * (W - LEFT - 8);
  const top = 36;
  const H = top + machines.length * ROW + 24;
  const hours: number[] = [];
  for (let h = t0; h <= t1; h += 60) hours.push(h);
  const legend = [
    { key: "new_start", label: tr("kind_new_start", "New start") },
    { key: "routine", label: tr("kind_routine", "Standing slot") },
    { key: "moved", label: tr("kind_moved", "Moved today") },
    { key: "added", label: tr("kind_added", "Added fraction") },
  ];
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-600">
        {legend.map((l) => (
          <span key={l.key} className="flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-sm" style={{ background: KIND_COLOUR[l.key] }} />
            {l.label}
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-sm bg-gray-300" />
          {tr("legend_done", "Lighter: treated")}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={tr("timeline_label", "Today's sessions on each machine")}>
        <defs>
          <pattern id="radsmart-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="#f3f4f6" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="#9ca3af" strokeWidth="2" />
          </pattern>
        </defs>
        {hours.map((h) => (
          <g key={h}>
            <line x1={x(h)} x2={x(h)} y1={top - 4} y2={H - 20} stroke="#e5e7eb" />
            <text x={x(h)} y={H - 6} textAnchor="middle" fontSize="11" fill="#6b7280">
              {hm(h)}
            </text>
          </g>
        ))}
        <line x1={x(day.new_start_latest_end)} x2={x(day.new_start_latest_end)} y1={10} y2={H - 20} stroke="#046c4e" strokeDasharray="4 3" />
        <text x={x(day.new_start_latest_end) + 4} y={13} fontSize="11" fill="#046c4e">
          {tr("timeline_17", "{{time}}: new starts finish before", { time: hm(day.new_start_latest_end) })}
        </text>
        {machines.map((m, i) => {
          const y = top + i * ROW;
          return (
            <g key={m.code}>
              <text x={LEFT - 8} y={y + ROW / 2 + 4} textAnchor="end" fontSize="12" fontWeight="600" fill={m.status === "offline" ? "#b91c1c" : "#111827"}>
                {m.code}
              </text>
              <rect x={LEFT} y={y + 4} width={W - LEFT - 8} height={ROW - 8} fill="#f9fafb" rx="4" />
              {day.blocks.map((b) => (
                <rect key={b.label + b.start} x={x(b.start)} y={y + 4} width={x(b.end) - x(b.start)} height={ROW - 8} fill="url(#radsmart-hatch)">
                  <title>{`${hm(b.start)}–${hm(b.end)} ${b.label}`}</title>
                </rect>
              ))}
              {live
                .filter((s) => s.machine === m.code)
                .map((s) => {
                  const done = s.status === "done";
                  const w = Math.max(2, x(s.start + s.minutes) - x(s.start) - 1);
                  return (
                    <rect
                      key={s.id}
                      x={x(s.start) + 0.5}
                      y={y + 8}
                      width={w}
                      height={ROW - 16}
                      rx="2"
                      fill={s.moved_today ? KIND_COLOUR.moved : (KIND_COLOUR[s.kind] ?? KIND_COLOUR.routine)}
                      opacity={done ? 0.35 : 1}
                    >
                      <title>
                        {`${s.time} ${s.patient_name} · ${tr("fraction_of", "fraction {{n}} of {{total}}", { n: s.fraction, total: s.fractions })} · ${Math.round(s.minutes)} min · ${s.status.replace("_", " ")}`}
                      </title>
                    </rect>
                  );
                })}
            </g>
          );
        })}
        {now !== undefined && now >= t0 && now <= t1 && (
          <g>
            <line x1={x(now)} x2={x(now)} y1={top - 4} y2={H - 20} stroke="#dc2626" strokeWidth="2" />
            <text x={x(now)} y={top - 6} textAnchor="middle" fontSize="11" fontWeight="600" fill="#dc2626">
              {tr("now", "now")}
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
