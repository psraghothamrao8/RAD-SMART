import { ArrowRight, Check, ChevronDown, ChevronUp, Compass } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { useQueryParams } from "raviger";

import { cn } from "@/lib/utils";

/**
 * The public demonstration's guided tour, inside the app (config.tour: RADSMART_OPEN_DEMO).
 * The tour's front door (/api/care_radsmart/try/) lists seven steps; each opens a page here,
 * signed in as the right person. This guide stays on that page: what to press, in order, and
 * the button to the next step. In English, like the front door: the tour is for reviewers.
 *
 * The step follows from the page. Steps a visitor has seen are kept in this browser
 * (localStorage radsmart_tour_seen), so the front door can tick them and offer the next one.
 */

const TRY = "/api/care_radsmart/try/";
const SEEN = "radsmart_tour_seen";
const SMALL = "radsmart_tour_small";

export const TOUR_STEPS = [
  "Plan a course",
  "See it on the patient's phone",
  "Check the patient in",
  "Run the day",
  "The machine breaks down",
  "Tell the patients",
  "See the waits",
] as const;

interface Guide {
  step: number; // 1 to 7
  who: string;
  todo: ReactNode[];
  tip?: ReactNode;
  next: { label: string; href: string };
}

/** Button names as they appear on the page. */
const B = ({ children }: { children: ReactNode }) => <strong className="font-semibold text-gray-900">{children}</strong>;

function guideFor(path: string, base: string, code?: string): Guide | null {
  const rest = path.startsWith(base) ? path.slice(base.length).replace(/\/$/, "") : null;
  if (rest === null) return null;
  const toPatient = { label: "Next: the patient's phone", href: `${TRY}patient/` };
  if (rest === "/courses/new")
    return {
      step: 1,
      who: "You are the doctor.",
      todo: [
        <>Pick a patient from the list.</>,
        <>
          Press <B>Fill in an example</B> above the prescription, or type your own.
        </>,
        <>
          Press <B>Save and propose slots</B> at the bottom of the page.
        </>,
      ],
      tip: (
        <>
          For an emergency, tick <B>Emergency start today</B> in the checklist before saving: RAD-SMART fits the patient in today.
        </>
      ),
      next: toPatient,
    };
  if (rest.startsWith("/courses/"))
    return {
      step: 1,
      who: "You are the doctor.",
      todo: [
        <>Read RAD-SMART's proposal: a first day, and one daily time for the whole course, that keep every rule of the department.</>,
        <>
          Press <B>Explain in plain words</B> to read why.
        </>,
        <>
          Press <B>Approve course and slots</B>. Only a doctor can.
        </>,
      ],
      next: toPatient,
    };
  if (rest === "/courses")
    return {
      step: 1,
      who: "You are the doctor.",
      todo: [
        <>Open any course to see its first day and its standing slot.</>,
        <>
          Or open the <B>New course</B> tab to plan one.
        </>,
      ],
      next: toPatient,
    };
  if (rest === "/checkin")
    return {
      step: 3,
      who: "You are at the reception desk.",
      todo: [
        code ? (
          <>
            The patient's code <B>{code}</B> is filled in for you.
          </>
        ) : (
          <>
            Type the six letters under the QR code on the patient's page, or press <B>Scan with camera</B>.
          </>
        ),
        <>
          Press <B>Check in</B>.
        </>,
        <>
          The patient now shows as <B>Waiting</B> on the Today board, the next step.
        </>,
      ],
      next: { label: "Next: run the day", href: `${TRY}technologist/?to=today` },
    };
  if (rest === "")
    return {
      step: 4,
      who: "You are the technologist at the machine.",
      todo: [
        <>
          Under each machine, <B>Call next</B> names who is next: press <B>Take in</B>. When the treatment ends, press <B>Out</B> in the
          patient's row.
        </>,
        <>
          Press <B>First</B> on any patient in the list, and give a reason: an emergency goes to the top of the queue.
        </>,
        <>
          Under <B>Slot change requests</B>, a better time may be offered to a patient: press <B>Patient agrees</B>.
        </>,
      ],
      tip: <>Nothing here is ever blocked: RAD-SMART warns, and people decide.</>,
      next: { label: "Next: the machine breaks down", href: `${TRY}technologist/?to=breakdown` },
    };
  if (rest === "/breakdown")
    return {
      step: 5,
      who: "You are the technologist.",
      todo: [
        <>
          Set <B>Expected downtime</B> to 1 h 30 min, then press <B>Take offline and propose</B>.
        </>,
        <>Read what RAD-SMART proposes for each patient, and why. It re-planned the rest of the day in seconds.</>,
        <>
          Press <B>Approve and notify</B>. Nothing changed until now.
        </>,
      ],
      tip: <>Up to an hour down, everyone is still treated today with a little overtime. Longer, some patients are sent back.</>,
      next: { label: "Next: tell the patients", href: `${TRY}technologist/?to=messages` },
    };
  if (rest === "/messages")
    return {
      step: 6,
      who: "You are the technologist.",
      todo: [
        <>
          Find a message under <B>To send</B>: each is drafted in the patient's own language.
        </>,
        <>
          Press <B>Listen</B> to hear it as a voice note.
        </>,
        <>
          Press <B>Open WhatsApp</B> to send it with the text filled in (or <B>Send on Telegram</B>, to your own Telegram), then{" "}
          <B>Mark sent</B>.
        </>,
      ],
      next: { label: "Next: see the waits", href: `${TRY}doctor/?to=insights` },
    };
  if (rest === "/insights")
    return {
      step: 7,
      who: "You are the doctor.",
      todo: [
        <>Read how long patients waited, worked out from the times the Today board recorded.</>,
        <>Compare the 90th-percentile wait with the department's baseline of 109 minutes.</>,
        <>
          Change <B>From</B> and <B>To</B> to see other days.
        </>,
      ],
      tip: <>That is the whole pipeline, from the prescription to the patient's phone.</>,
      next: { label: "Finish the tour", href: TRY },
    };
  return null;
}

function load<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : (JSON.parse(v) as T);
  } catch {
    return fallback;
  }
}
function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode: the guide still works, it just forgets */
  }
}

export default function TourGuide({ path, base }: { path: string; base: string }) {
  const [{ code }] = useQueryParams<{ code?: string }>();
  const guide = guideFor(path, base, code && /^[A-Z0-9]{6}$/.test(code) ? code : undefined);
  const [small, setSmall] = useState(() => load(SMALL, false));
  const [seen, setSeen] = useState<number[]>(() => load(SEEN, []));
  const step = guide?.step;
  useEffect(() => {
    if (!step) return;
    setSeen((s) => {
      if (s.includes(step)) return s;
      const out = [...s, step];
      save(SEEN, out);
      return out;
    });
  }, [step]);
  if (!guide) return null;
  const toggle = () => {
    save(SMALL, !small);
    setSmall(!small);
  };
  const title = TOUR_STEPS[guide.step - 1];
  const next = (
    <a
      href={guide.next.href}
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md bg-primary-700 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-800"
    >
      {guide.next.label}
      <ArrowRight className="size-4" />
    </a>
  );
  return (
    <aside aria-label="Guided tour" className="rounded-lg border-2 border-primary-600 bg-primary-50 p-3 text-sm text-gray-800 md:p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {/* On a phone the heading has its own line; the step dots and Hide go below it */}
        <p className="flex min-w-0 flex-1 basis-full items-start gap-2 sm:basis-0">
          <Compass className="mt-px size-5 shrink-0 text-primary-700" aria-hidden />
          <span>
            <span className="text-primary-800">
              Guided tour, step {guide.step} of {TOUR_STEPS.length}:
            </span>{" "}
            <span className="font-semibold text-gray-900">{title}</span>
          </span>
        </p>
        <ol className="flex items-center gap-1 max-sm:mr-auto" aria-label="Steps">
          {TOUR_STEPS.map((t, i) => (
            <li
              key={t}
              title={`${i + 1}. ${t}`}
              aria-current={i + 1 === guide.step ? "step" : undefined}
              className={cn(
                "grid size-5 place-items-center rounded-full text-[10px] font-bold",
                i + 1 === guide.step
                  ? "bg-primary-700 text-white"
                  : seen.includes(i + 1)
                    ? "bg-primary-200 text-primary-800"
                    : "bg-white text-gray-400 ring-1 ring-gray-300",
              )}
            >
              {seen.includes(i + 1) && i + 1 !== guide.step ? <Check className="size-3" /> : i + 1}
            </li>
          ))}
        </ol>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!small}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-primary-800 hover:bg-primary-100"
        >
          {small ? <ChevronDown className="size-4" /> : <ChevronUp className="size-4" />}
          {small ? "Show what to do" : "Hide"}
        </button>
        {small && next}
      </div>
      {!small && (
        <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0">
            <p className="text-gray-600">{guide.who} Do this, in order:</p>
            <ol className="mt-1.5 flex flex-col gap-1.5">
              {guide.todo.map((t, i) => (
                <li key={i} className="flex gap-2">
                  <span className="grid size-5 shrink-0 place-items-center rounded-full bg-white text-xs font-bold text-primary-800 ring-1 ring-primary-300">
                    {i + 1}
                  </span>
                  <span>{t}</span>
                </li>
              ))}
            </ol>
            {guide.tip && <p className="mt-2 text-gray-600">{guide.tip}</p>}
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-3">
            <a href={TRY} className="text-sm font-medium text-primary-800 hover:underline">
              All steps
            </a>
            {next}
          </div>
        </div>
      )}
    </aside>
  );
}
