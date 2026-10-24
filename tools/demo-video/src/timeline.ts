// Turns the recorder's log (public/rec/rec.json) into the video's timeline: an intro card,
// a title card before each step, the recording itself, and an outro card. Waits for the
// server and page loads are compressed so the video keeps moving.
import rec from "../public/rec/rec.json";

export const FPS = 30;
export const REC_W = rec.width; // CSS pixels of the recorded viewport
export const REC_H = rec.height;

const SPEED = 1.15; // the recording plays slightly faster than real time
const FAST_TO = 1300; // a server wait is shown in this many ms
const IDLE_MAX = 6000; // a gap between actions longer than this is a page load...
const IDLE_TO = 1300; // ...shown in this many ms
const INTRO = 5;
const CARD = 2.6;
const OUTRO = 7;

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
  cx?: number;
  cy?: number;
  scale?: number;
};
export type Frame = { file: string; t: number };

export const events = rec.events as Ev[];
export const frames = rec.frames as Frame[];
export const chapters = events.filter((e) => e.type === "chapter");

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
  return out.sort((x, y) => x.a - y.a);
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
    const stop = i + 1 < chapters.length ? chapters[i + 1].t : end + 1200;
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

export function frameFileAt(t: number): string {
  let lo = 0, hi = frames.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (frames[mid].t <= t) lo = mid;
    else hi = mid - 1;
  }
  return frames[lo].file;
}
