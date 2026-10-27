import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { PageLink } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Badge, Card } from "@/components/ui/primitives";
import { shortDate } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { keys } from "@/lib/useConfig";
import { API, type SlotRequest } from "@/utils/api";

import { SlotChoice, slotOptions } from "./SlotChoice";

/** Patients' requests for another standing time, waiting for a decision. */
export default function SlotRequests({ facilityId }: { facilityId: string }) {
  const tr = useT();
  const list = useQuery({
    queryKey: keys.slotRequests(facilityId),
    queryFn: () => API.slotRequests(facilityId, "proposed"),
  });
  if (!list.data?.length) return null;
  return (
    <Card title={tr("slot_requests", "Slot change requests ({{n}})", { n: list.data.length })}>
      <div className="flex flex-col divide-y divide-gray-100">
        {list.data.map((r) => (
          <RequestRow key={r.id} r={r} facilityId={facilityId} />
        ))}
      </div>
    </Card>
  );
}

export function RequestRow({ r, facilityId, onDone }: { r: SlotRequest; facilityId: string; onDone?: () => void }) {
  const tr = useT();
  const qc = useQueryClient();
  const options = slotOptions(r.proposal);
  const [time, setTime] = useState(options[0]?.time ?? "");
  const keep = time === r.current;
  const decide = useMutation({
    mutationFn: (d: "approve" | "reject") => API.decideSlot(facilityId, r.id, d, d === "approve" ? time : undefined),
    onSuccess: (_, d) => {
      toast.success(d === "approve" ? tr("slot_changed", "Standing slot changed to {{time}}", { time }) : tr("slot_kept", "The slot stays at {{time}}", { time: r.current ?? "" }));
      qc.invalidateQueries({ queryKey: ["care_radsmart"] });
      onDone?.();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <div className="flex flex-col gap-3 py-3 first:pt-0 last:pb-0 lg:flex-row lg:items-start">
      <div className="lg:w-64">
        <PageLink href={`/facility/${facilityId}/radsmart/courses/${r.course}`}>{r.patient_name}</PageLink>
        <p className="text-xs text-gray-500">{r.hospital_number}</p>
        <Badge tone={r.source === "radsmart" ? "violet" : "gray"} className="mt-1">
          {r.source === "radsmart" ? tr("src_radsmart", "RAD-SMART offer") : r.source === "staff" ? tr("src_staff", "Asked at the desk") : tr("src_patient", "Asked by the patient")}
        </Badge>
        <p className="mt-1 text-sm">
          {r.source === "radsmart"
            ? tr("offer_for", "Now {{current}}; a time inside the {{band}} is free from {{date}}. Ask the patient first.", { current: r.current ?? "—", band: r.band_label || r.band, date: shortDate(r.from_date) })
            : tr("asks_for", "Now {{current}}, asks for {{wanted}} from {{date}}", { current: r.current ?? "—", wanted: r.band_label || r.wanted || "—", date: shortDate(r.from_date) })}
        </p>
        {r.reason && <p className="text-xs text-gray-500">“{r.reason}”</p>}
      </div>
      <div className="flex-1">
        <SlotChoice proposal={r.proposal} value={time} onChange={setTime} current={r.current} />
      </div>
      <div className="flex gap-2">
        {keep ? (
          <Button size="sm" variant="outline" onClick={() => decide.mutate("reject")} disabled={decide.isPending}>
            {tr("keep_time", "Keep {{time}}", { time })}
          </Button>
        ) : (
          <>
            <Button size="sm" onClick={() => decide.mutate("approve")} disabled={!time || decide.isPending}>
              {r.source === "radsmart" ? tr("patient_agrees", "Patient agrees") : tr("approve_time", "Approve {{time}}", { time })}
            </Button>
            <Button size="sm" variant="outline" onClick={() => decide.mutate("reject")} disabled={decide.isPending}>
              {r.source === "radsmart" ? tr("patient_stays", "Prefers to stay") : tr("decline", "Decline")}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
