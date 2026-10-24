// Turns the recorder's log (public/rec/rec.json) into the video's timeline: an intro card,
// a title card before each step, the recording itself, and an outro card. Waits for the
// server and page loads are compressed so the video keeps moving, except while the
// narrator speaks or a voice note plays.
import narration from "../public/narration/index.json";
import rec from "../public/rec/rec.json";

export const FPS = 30;
export const REC_W = rec.width; // CSS pixels of the recorded viewport
export const REC_H = rec.height;

const SPEED = rec.speed ?? 1.15; // the recording plays slightly faster than real time
const FAST_TO = 1300; // a server wait is shown in this many ms
const IDLE_MAX = 6000; // a gap between actions longer than this is a page load...
const IDLE_TO = 1300; // ...shown in this many ms
const voice = narration as Record<string, { file: string | null; sec: number }>;
export const INTRO_VOICE = voice.intro;
export const OUTRO_VOICE = voice.outro;
const INTRO = Math.max(5, INTRO_VOICE.sec + 1.6);
const CARD = 2.6;
const OUTRO = Math.max(7, OUTRO_VOICE.sec + 2.5);

export type Ev = {
  t: number;
  type: string;
  x?: number;
  y?: number;
  fromX?: number;
  fromY?: number;
  dur?: number;
  text?: string;
  title?: string;
  role?: string;
  on?: boolean;
  label?: string;
  key?: string;
  file?: string | null;
  sec?: number;
  phone?: boolean;
  w?: number;
  h?: number;
  cx?: number;
  cy?: number;
  scale?: number;
};
export type Frame = { file: string; t: number };

export const events = rec.events as Ev[];
export const frames = rec.frames as Frame[];
export const chapters = events.filter((e) => e.type === "chapter");
export const PHONE = rec.phone as { w: number; h: number; dsf: number } | undefined;

export type Piece =
  | { kind: "intro"; from: number; dur: number }
  | { kind: "outro"; from: number; dur: number }
  | { kind: "card"; from: number; dur: number; index: number }
  | { kind: "rec"; from: number; dur: number; recFrom: number; recTo: number; chapter: number; skipped?: string };

const sec = (s: number) => Math.max(1, Math.round(s * FPS));

function compressed(): { a: number; b: number; label: string }[] {
  const out: { a: number; b: number; label: string }[] = [];
  let open: Ev | null = null;
  for (const e of events) {
    if (e.type === "fast" && e.on) open = e;
    if (e.type === "fast" && !e.on && open) {
      if (e.t - open.t > FAST_TO * SPEED) out.push({ a: open.t, b: e.t, label: open.label ?? "Working" });
      open = null;
    }
  }
  const acts = events.filter((e) => ["move", "click", "caption", "chapter", "zoom", "end"].includes(e.type));
  for (let i = 1; i < acts.length; i++) {
    const a = acts[i - 1].t + 1500, b = acts[i].t - 600;
    if (b - a > IDLE_MAX - 2100 && !out.some((o) => o.a < b && o.b > a)) out.push({ a, b, label: "Page loading" });
  }
  // Never compress while the narrator speaks or a voice note plays.
  const keep = events
    .filter((e) => (e.type === "caption" || e.type === "audio") && e.sec)
    .map((e) => ({ a: e.t, b: e.t + (e.sec ?? 0) * 1000 * SPEED + 200 }));
  const parts = out.flatMap((iv) =>
    keep.reduce<typeof out>(
      (acc, k) => acc.flatMap((p) => (k.b <= p.a || k.a >= p.b ? [p] : [...(k.a > p.a ? [{ ...p, b: k.a }] : []), ...(k.b < p.b ? [{ ...p, a: k.b }] : [])])),
      [iv],
    ),
  );
  return parts.filter((p) => p.b - p.a > FAST_TO * SPEED).sort((x, y) => x.a - y.a);
}

export function buildTimeline() {
  const pieces: Piece[] = [];
  let f = 0;
  const push = (p: Piece) => {
    pieces.push(p);
    f += p.dur;
  };
  push({ kind: "intro", from: f, dur: sec(INTRO) });
  const skips = compressed();
  const end = events.find((e) => e.type === "end")?.t ?? events[events.length - 1].t;
  chapters.forEach((ch, i) => {
    push({ kind: "card", from: f, dur: sec(CARD), index: i });
    const next = i + 1 < chapters.length ? chapters[i + 1].t : end + 1200;
    // set-up for the next step (a "cut" just before its chapter) is not shown
    const cut = events.find((e) => e.type === "cut" && e.t > ch.t && e.t < next);
    const stop = cut ? cut.t : next;
    let t = ch.t;
    for (const s of skips) {
      if (s.b <= t || s.a >= stop) continue;
      if (s.a > t) push({ kind: "rec", from: f, dur: sec((s.a - t) / 1000 / SPEED), recFrom: t, recTo: s.a, chapter: i });
      const b = Math.min(s.b, stop);
      push({ kind: "rec", from: f, dur: sec((s.label === "Page loading" ? IDLE_TO : FAST_TO) / 1000), recFrom: Math.max(s.a, t), recTo: b, chapter: i, skipped: s.label });
      t = b;
    }
    if (stop > t) push({ kind: "rec", from: f, dur: sec((stop - t) / 1000 / SPEED), recFrom: t, recTo: stop, chapter: i });
  });
  push({ kind: "outro", from: f, dur: sec(OUTRO) });
  return { pieces, total: f };
}

export const timeline = buildTimeline();

export function pieceAt(frame: number): Piece {
  const ps = timeline.pieces;
  let lo = 0, hi = ps.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (ps[mid].from <= frame) lo = mid;
    else hi = mid - 1;
  }
  return ps[lo];
}

/** The video frame at which a moment of the recording is shown. */
export function videoFrameOf(t: number): number {
  for (const p of timeline.pieces) {
    if (p.kind === "rec" && t >= p.recFrom && t < p.recTo) return Math.round(p.from + ((t - p.recFrom) / (p.recTo - p.recFrom)) * p.dur);
  }
  return 0;
}

/** Whether the recording shows the phone at this moment. */
export function phoneAt(t: number): boolean {
  let on = false;
  for (const e of events) if (e.type === "device" && e.t <= t) on = !!e.phone;
  return on;
}

export function frameFileAt(t: number): string {
  let lo = 0, hi = frames.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (frames[mid].t <= t) lo = mid;
    else hi = mid - 1;
  }
  return frames[lo].file;
}
