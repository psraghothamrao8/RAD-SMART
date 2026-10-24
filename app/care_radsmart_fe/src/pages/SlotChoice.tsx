import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n";
import type { Proposal } from "@/utils/api";

export function slotOptions(p: Proposal) {
  const out: { time: string; note: string; best: boolean }[] = [];
  if (p.standing) out.push({ time: p.standing.time, note: "", best: true });
  for (const a of p.alternatives ?? []) if (!out.some((o) => o.time === a.time)) out.push({ time: a.time, note: a.note ?? "", best: false });
  return out;
}

/** RAD-SMART's standing slot and its alternatives; the reasons explain the choice. */
export function SlotChoice({ proposal, value, onChange, current }: { proposal: Proposal; value: string; onChange: (t: string) => void; current?: string | null }) {
  const tr = useT();
  const options = slotOptions(proposal);
  if (!proposal.ok) return <p className="text-sm text-danger-700">{proposal.problem}</p>;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2" role="radiogroup">
        {options.map((o) => (
          <button
            type="button"
            key={o.time}
            role="radio"
            aria-checked={value === o.time}
            onClick={() => onChange(o.time)}
            className={cn(
              "rounded-md border px-3 py-1.5 text-left text-sm",
              value === o.time ? "border-primary-700 bg-primary-50 ring-1 ring-primary-700" : "border-gray-300 bg-white hover:bg-gray-50",
            )}
          >
            <span className="font-semibold tabular-nums">{o.time}</span>
            <span className="ml-2 text-xs text-gray-500">
              {o.time === current ? tr("current_slot", "current slot") : o.best ? tr("recommended", "recommended") : o.note || tr("alternative", "alternative")}
            </span>
          </button>
        ))}
      </div>
      <ul className="list-disc pl-5 text-xs text-gray-600">
        {proposal.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </div>
  );
}
