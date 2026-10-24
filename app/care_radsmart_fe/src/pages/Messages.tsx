import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Languages, MessageCircle, Square, Volume2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import Layout, { PageLink } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Badge, Card, Empty, Input, Notice, Spinner, type Tone } from "@/components/ui/primitives";
import { clockTime, longDate } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { keys } from "@/lib/useConfig";
import { cn } from "@/lib/utils";
import { API, type Config, type Message } from "@/utils/api";

export default function Messages({ facilityId }: { facilityId: string }) {
  const tr = useT();
  return (
    <Layout facilityId={facilityId} title={tr("messages_title", "Messages to patients")}>
      {(config) => <MessageBoard facilityId={facilityId} config={config} />}
    </Layout>
  );
}

const KIND_TONE: Record<Message["kind"], Tone> = { course: "green", slot: "blue", breakdown: "amber" };

function MessageBoard({ facilityId, config }: { facilityId: string; config: Config }) {
  const tr = useT();
  const [date, setDate] = useState(config.today);
  const [filter, setFilter] = useState<"to_send" | "sent" | "all">("to_send");
  const params = { date, status: filter === "all" ? undefined : filter };
  const list = useQuery({
    queryKey: keys.messages(facilityId, params),
    queryFn: () => API.messages(facilityId, params),
    // Translations finish in the background a few seconds after approval.
    refetchInterval: (q) => (q.state.data?.some((m) => m.local_status === "pending") ? 3_000 : 30_000),
  });
  const canOperate = !!config.permissions?.can_operate_radsmart;

  return (
    <div className="flex flex-col gap-4">
      {config.sarvam ? (
        <Notice kind="info" title={tr("msg_how", "Each message is drafted after a person approves the change")}>
          {tr(
            "msg_how_text",
            "Sarvam AI translates it into the patient's language and reads it aloud. A translation that changes a time is not used: the patient gets the English text. Open WhatsApp, check the text, press send, then mark it sent here.",
          )}
        </Notice>
      ) : (
        <Notice kind="warn" title={tr("msg_no_sarvam", "Sarvam AI is not connected")}>
          {tr("msg_no_sarvam_text", "Messages go in English. Add SARVAM_API_KEY to the server to translate them and add voice notes.")}
        </Notice>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Input type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} className="w-44" />
        {date !== config.today && (
          <Button variant="ghost" size="sm" onClick={() => setDate(config.today)}>
            {tr("back_to_today", "Back to today")}
          </Button>
        )}
        <span className="text-sm font-medium text-gray-700">{longDate(date)}</span>
        <div className="ml-auto flex gap-1">
          {(
            [
              ["to_send", tr("mf_to_send", "To send")],
              ["sent", tr("mf_sent", "Sent")],
              ["all", tr("f_all", "All")],
            ] as const
          ).map(([k, label]) => (
            <Button key={k} size="xs" variant={filter === k ? "primary" : "ghost"} onClick={() => setFilter(k)}>
              {label}
            </Button>
          ))}
        </div>
      </div>
      {list.isLoading ? (
        <Spinner label={tr("loading", "Loading…")} />
      ) : list.error ? (
        <Notice kind="error">{String((list.error as Error).message)}</Notice>
      ) : !list.data?.length ? (
        <Empty>{filter === "to_send" ? tr("msg_none_to_send", "No messages waiting to be sent") : tr("msg_none", "No messages on this day")}</Empty>
      ) : (
        <div className="flex flex-col gap-3">
          {list.data.map((m) => (
            <MessageCard key={m.id} m={m} facilityId={facilityId} canOperate={canOperate} />
          ))}
        </div>
      )}
    </div>
  );
}

export function MessageCard({ m, facilityId, canOperate, compact }: { m: Message; facilityId: string; canOperate: boolean; compact?: boolean }) {
  const tr = useT();
  const qc = useQueryClient();
  const step = useMutation({
    mutationFn: (s: "sent" | "cancel" | "translate") => API.messageStep(m.id, s),
    onSuccess: (_, s) => {
      if (s === "sent") toast.success(tr("msg_marked", "Marked sent"));
      qc.invalidateQueries({ queryKey: ["care_radsmart", "messages"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const kindLabel = { course: tr("mk_course", "New course"), slot: tr("mk_slot", "New standing time"), breakdown: tr("mk_breakdown", "Breakdown") }[m.kind];
  const done = m.status !== "to_send";
  const full = [m.local_text, m.text, m.link].filter(Boolean).join("\n\n");
  return (
    <Card
      className={cn(done && "opacity-80")}
      title={
        <span className="flex flex-wrap items-center gap-2">
          {compact ? kindLabel : <PageLink href={`/facility/${facilityId}/radsmart/courses/${m.course}`}>{m.patient_name}</PageLink>}
          {!compact && <span className="text-xs font-normal text-gray-500">{m.hospital_number}</span>}
          {!compact && <Badge tone={KIND_TONE[m.kind]}>{kindLabel}</Badge>}
          <Badge tone="gray">{m.language}</Badge>
          {m.status === "sent" && (
            <Badge tone="green">{tr("msg_sent_by", "Sent by {{who}} at {{time}}", { who: m.sent_by ?? "—", time: clockTime(m.sent_at) })}</Badge>
          )}
          {m.status === "cancelled" && <Badge tone="gray">{tr("msg_cancelled", "Not sent")}</Badge>}
        </span>
      }
      action={<span className="text-xs text-gray-500">{clockTime(m.created_date)}</span>}
    >
      <div className="flex flex-col gap-2">
        {m.local_status === "pending" && (
          <p className="flex items-center gap-2 text-sm text-gray-500">
            <Languages className="size-4 animate-pulse" />
            {tr("msg_translating", "Translating into {{lang}}…", { lang: m.language })}
          </p>
        )}
        {m.local_text && (
          <p className="text-base leading-relaxed text-gray-900" lang={langCode(m.language)}>
            {m.local_text}
          </p>
        )}
        <p className={cn("text-gray-700", m.local_text ? "text-xs" : "text-sm")}>{m.text}</p>
        {m.local_note && (
          <p className={cn("text-xs", m.local_status === "failed" ? "text-danger-700" : "text-gray-500")}>{m.local_note}</p>
        )}
      </div>
      {canOperate && m.status !== "cancelled" && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3">
          {m.status === "to_send" && (
            <Button asChild size="sm">
              <a href={m.whatsapp} target="_blank" rel="noreferrer">
                <MessageCircle />
                {tr("open_whatsapp", "Open WhatsApp")}
              </a>
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigator.clipboard.writeText(full).then(() => toast.success(tr("copied", "Copied: paste it into SMS or any app")))}
          >
            <Copy />
            {tr("copy", "Copy")}
          </Button>
          {m.voice && <Listen id={m.id} />}
          {m.voice && m.local_text && <Listen id={m.id} english />}
          {m.local_status === "failed" && (
            <Button size="sm" variant="ghost" onClick={() => step.mutate("translate")} disabled={step.isPending}>
              <Languages />
              {tr("retry_translate", "Translate again")}
            </Button>
          )}
          {m.status === "to_send" && (
            <span className="ml-auto flex gap-2">
              <Button size="sm" variant="outline" onClick={() => step.mutate("sent")} disabled={step.isPending}>
                <Check />
                {tr("mark_sent", "Mark sent")}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => window.confirm(tr("confirm_msg_cancel", "Do not send this message?")) && step.mutate("cancel")}
                disabled={step.isPending}
                aria-label={tr("msg_cancel", "Do not send")}
                title={tr("msg_cancel", "Do not send")}
              >
                <X />
              </Button>
            </span>
          )}
        </div>
      )}
    </Card>
  );
}

/** Plays the Bulbul voice note; staff listen before sending it on. */
function Listen({ id, english }: { id: string; english?: boolean }) {
  const tr = useT();
  const audio = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");
  useEffect(
    () => () => {
      audio.current?.pause();
      if (audio.current?.src) URL.revokeObjectURL(audio.current.src);
    },
    [],
  );
  const play = async () => {
    if (state === "playing") {
      audio.current?.pause();
      setState("idle");
      return;
    }
    try {
      if (!audio.current) {
        setState("loading");
        audio.current = new Audio(await API.messageAudio(id, english));
        audio.current.onended = () => setState("idle");
      }
      await audio.current.play();
      setState("playing");
    } catch (e) {
      setState("idle");
      toast.error((e as Error).message);
    }
  };
  return (
    <Button size="sm" variant="ghost" onClick={play} disabled={state === "loading"}>
      {state === "playing" ? <Square /> : <Volume2 />}
      {english ? tr("listen_en", "English") : tr("listen", "Listen")}
    </Button>
  );
}

function langCode(language: string) {
  return ({ Kannada: "kn", Tulu: "kn", Malayalam: "ml", Hindi: "hi", Konkani: "kok" } as Record<string, string>)[language] ?? "en";
}
