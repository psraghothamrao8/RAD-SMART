import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera, CameraOff, ScanLine } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import Layout, { PageLink } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Badge, Card, Empty, Input, Notice } from "@/components/ui/primitives";
import { clockTime } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { API, type Config, type SessionRow } from "@/utils/api";

import { STATUS_TONE, useStatusLabel } from "./Today";

type Done = SessionRow & { already: boolean; at: string };

export default function CheckIn({ facilityId }: { facilityId: string }) {
  const tr = useT();
  return (
    <Layout facilityId={facilityId} title={tr("checkin_title", "Reception check-in")}>
      {(config) => <Desk facilityId={facilityId} config={config} />}
    </Layout>
  );
}

/**
 * The patient shows the QR code on their page (or reads out its six letters).
 * A USB scanner types the code into the box like a keyboard; a phone or
 * laptop camera works too. The session is marked arrived on Today's board.
 */
function Desk({ facilityId, config }: { facilityId: string; config: Config }) {
  const tr = useT();
  const qc = useQueryClient();
  const statusLabel = useStatusLabel();
  const [code, setCode] = useState("");
  const [camera, setCamera] = useState(false);
  const [done, setDone] = useState<Done[]>([]);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLInputElement>(null);
  const checkIn = useMutation({
    mutationFn: (c: string) => API.checkIn(facilityId, c),
    onSuccess: (s) => {
      setError(null);
      setDone((d) => [{ ...s, at: new Date().toISOString() }, ...d.filter((x) => x.id !== s.id)].slice(0, 20));
      setCode("");
      qc.invalidateQueries({ queryKey: ["care_radsmart"] });
    },
    onError: (e: Error) => setError(e.message),
    onSettled: () => box.current?.focus(),
  });
  const submit = (raw: string) => {
    const c = raw.trim().toUpperCase().replace(/^RADSMART:/, "");
    if (c.length === 6 && !checkIn.isPending) checkIn.mutate(c);
  };
  const last = done[0];

  if (!config.permissions?.can_operate_radsmart) {
    return <Notice kind="warn">{tr("operate_only_checkin", "Reception and technologists check patients in.")}</Notice>;
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title={tr("scan_title", "Scan the patient's code")}>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit(code);
          }}
        >
          <Input
            ref={box}
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder={tr("code_ph", "Six-letter code")}
            className="h-12 text-center font-mono text-2xl tracking-[0.3em] placeholder:font-sans placeholder:text-base placeholder:tracking-normal"
            maxLength={20}
            aria-label={tr("code", "Check-in code")}
          />
          <Button type="submit" className="h-12" disabled={checkIn.isPending}>
            <ScanLine />
            {tr("check_in", "Check in")}
          </Button>
        </form>
        <p className="mt-2 text-xs text-gray-500">
          {tr("scan_hint", "A barcode scanner types the code here. Or use the camera:")}
        </p>
        <div className="mt-2">
          <Button variant="outline" size="sm" onClick={() => setCamera((c) => !c)}>
            {camera ? <CameraOff /> : <Camera />}
            {camera ? tr("camera_off", "Stop camera") : tr("camera_on", "Scan with camera")}
          </Button>
        </div>
        {camera && <Scanner onCode={submit} onError={(m) => setError(m)} />}
        {error && (
          <div className="mt-3">
            <Notice kind="error">{error}</Notice>
          </div>
        )}
        {last && !error && (
          <div className="mt-3">
            <Notice kind={last.already ? "info" : "ok"} title={last.already ? tr("already_in", "{{name}} was already checked in", { name: last.patient_name }) : tr("checked_in", "{{name}} is checked in", { name: last.patient_name })}>
              {tr("checked_in_text", "Treatment at {{time}} on {{machine}} · fraction {{f}} of {{n}}", { time: last.time, machine: last.machine, f: last.fraction, n: last.fractions })}
            </Notice>
          </div>
        )}
      </Card>
      <Card title={tr("checked_in_list", "Checked in at this desk")}>
        {done.length === 0 ? (
          <Empty>{tr("none_checked_in", "Nobody yet")}</Empty>
        ) : (
          <ul className="divide-y divide-gray-100">
            {done.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                <span>
                  <PageLink href={`/facility/${facilityId}/radsmart/courses/${s.course}`}>{s.patient_name}</PageLink>
                  <span className="ml-2 text-xs text-gray-500">
                    {s.hospital_number} · {tr("treat_at", "treatment {{time}}", { time: s.time })}
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <span className="text-xs tabular-nums text-gray-500">{clockTime(s.at)}</span>
                  <Badge tone={STATUS_TONE[s.status]}>{statusLabel(s.status)}</Badge>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

/** Reads QR codes from the camera with jsQR (loaded only when the camera is on). */
function Scanner({ onCode, onError }: { onCode: (c: string) => void; onError: (m: string) => void }) {
  const tr = useT();
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    let stream: MediaStream | null = null;
    let frame = 0;
    let lastCode = "";
    let lastAt = 0;
    let stopped = false;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    (async () => {
      try {
        const { default: jsQR } = await import("jsqr");
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        if (stopped || !video.current) return;
        video.current.srcObject = stream;
        await video.current.play();
        const tick = () => {
          const v = video.current;
          if (stopped || !v || !ctx) return;
          if (v.readyState >= 2 && v.videoWidth) {
            canvas.width = v.videoWidth;
            canvas.height = v.videoHeight;
            ctx.drawImage(v, 0, 0);
            const hit = jsQR(ctx.getImageData(0, 0, canvas.width, canvas.height).data, canvas.width, canvas.height);
            // The same code stays in view for a while: read it once every 4 seconds.
            if (hit?.data.startsWith("RADSMART:") && (hit.data !== lastCode || Date.now() - lastAt > 4000)) {
              lastCode = hit.data;
              lastAt = Date.now();
              onCode(hit.data);
            }
          }
          frame = requestAnimationFrame(tick);
        };
        tick();
      } catch (e) {
        onError(tr("camera_failed", "The camera could not start: {{why}}", { why: (e as Error).message }));
      }
    })();
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((t) => t.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <video ref={video} muted playsInline className="mt-3 aspect-video w-full rounded-lg bg-gray-900 object-cover" />;
}
