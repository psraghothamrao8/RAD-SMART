import { loadFont as loadSans } from "@remotion/google-fonts/IBMPlexSans";
import { loadFont as loadSerif } from "@remotion/google-fonts/SourceSerif4";
import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame } from "remotion";

import { chapters, type Ev, events, frameFileAt, pieceAt, REC_H, REC_W, timeline } from "./timeline";

const { fontFamily: sans } = loadSans("normal", { weights: ["400", "500", "600"], subsets: ["latin"] });
const { fontFamily: serif } = loadSerif("normal", { weights: ["600"], subsets: ["latin"] });

const C = {
  bg: "#0E1A2B",
  bg2: "#13243A",
  ink: "#F3F6FA",
  ink2: "#B9C6D6",
  muted: "#8495AA",
  accent: "#3987E5",
  accentSoft: "rgba(57, 135, 229, 0.16)",
  warm: "#EB6834",
};

// The recording sits in a window 1440 px wide, with the caption band below it.
const WIN_W = 1440;
const K = WIN_W / REC_W;
const WIN_H = REC_H * K;
const WIN_X = (1920 - WIN_W) / 2;
const WIN_Y = 92;

const ROLE = ["Doctor", "Technologist", "Technologist", "Technologist", "Doctor and technologist"];
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.33, 0, 0.2, 1);

export const Demo: React.FC = () => {
  const frame = useCurrentFrame();
  const p = pieceAt(frame);
  const local = frame - p.from;
  const fade = interpolate(local, [0, 10, p.dur - 10, p.dur], [0, 1, 1, 0], clamp);

  if (p.kind === "intro") return <Intro opacity={fade} local={local} />;
  if (p.kind === "outro") return <Outro opacity={interpolate(local, [0, 12], [0, 1], clamp)} local={local} />;
  if (p.kind === "card") return <Card index={p.index} opacity={fade} local={local} />;

  const recT = p.recFrom + (local / p.dur) * (p.recTo - p.recFrom);
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: sans }}>
      <TopBar chapter={p.chapter} />
      <Window recT={recT} skipped={p.skipped} />
      <Caption recT={recT} chapter={p.chapter} />
    </AbsoluteFill>
  );
};

function TopBar({ chapter }: { chapter: number }) {
  return (
    <div style={{ position: "absolute", left: WIN_X, right: WIN_X, top: 26, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 18 }}>
        <span style={{ fontFamily: serif, fontSize: 34, fontWeight: 600, color: C.ink }}>RAD-SMART</span>
        <span style={{ fontSize: 24, color: C.muted }}>inside CARE · synthetic patients</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <span style={{ fontSize: 24, color: C.ink2 }}>
          Step {chapter + 1} of {chapters.length}
        </span>
        <span style={{ fontSize: 24, fontWeight: 600, color: C.ink, background: C.accentSoft, border: `1px solid ${C.accent}`, borderRadius: 999, padding: "6px 18px" }}>
          {ROLE[chapter]}
        </span>
      </div>
    </div>
  );
}

function Window({ recT, skipped }: { recT: number; skipped?: string }) {
  const z = zoomAt(recT);
  const tx = Math.min(0, Math.max(REC_W - z.s * REC_W, REC_W / 2 - z.s * z.cx));
  const ty = Math.min(0, Math.max(REC_H - z.s * REC_H, REC_H / 2 - z.s * z.cy));
  const pos = cursorAt(recT);
  const clicks = events.filter((e) => e.type === "click" && recT >= e.t && recT - e.t < 650);
  return (
    <div
      style={{
        position: "absolute",
        left: WIN_X,
        top: WIN_Y,
        width: WIN_W,
        height: WIN_H,
        borderRadius: 14,
        overflow: "hidden",
        background: "#fff",
        boxShadow: "0 24px 60px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.08)",
      }}
    >
      <div style={{ width: REC_W, height: REC_H, scale: String(K), transformOrigin: "0 0" }}>
        <div style={{ width: REC_W, height: REC_H, transformOrigin: "0 0", translate: `${tx}px ${ty}px`, scale: String(z.s) }}>
          <Img src={staticFile(`rec/frames/${frameFileAt(recT)}`)} style={{ width: REC_W, height: REC_H, display: "block" }} />
          {clicks.map((c) => {
            const k = (recT - c.t) / 650;
            return (
              <div
                key={c.t}
                style={{
                  position: "absolute",
                  left: (c.x ?? 0) - 6 - 30 * k,
                  top: (c.y ?? 0) - 6 - 30 * k,
                  width: 12 + 60 * k,
                  height: 12 + 60 * k,
                  borderRadius: "50%",
                  border: `3px solid ${C.accent}`,
                  background: "rgba(57,135,229,0.18)",
                  opacity: 1 - k,
                }}
              />
            );
          })}
          <Pointer x={pos.x} y={pos.y} />
        </div>
      </div>
      {skipped && (
        <div style={{ position: "absolute", right: 20, top: 18, fontFamily: sans, fontSize: 22, fontWeight: 600, color: "#fff", background: "rgba(14,26,43,0.85)", borderRadius: 999, padding: "8px 18px" }}>
          ⏩ {skipped === "Page loading" ? "Page loading, sped up" : `${skipped}, sped up`}
        </div>
      )}
    </div>
  );
}

function Pointer({ x, y }: { x: number; y: number }) {
  return (
    <svg width={26} height={34} viewBox="0 0 26 34" style={{ position: "absolute", left: x - 3, top: y - 2, filter: "drop-shadow(0 2px 3px rgba(0,0,0,0.35))" }}>
      <path d="M3 2 L3 27 L9.5 21 L13.5 31 L18 29 L14 19.5 L22.5 19.5 Z" fill="#111" stroke="#fff" strokeWidth={2} strokeLinejoin="round" />
    </svg>
  );
}

function Caption({ recT, chapter }: { recT: number; chapter: number }) {
  const start = chapters[chapter].t;
  const cap = [...events].reverse().find((e) => e.type === "caption" && e.t <= recT && e.t >= start);
  if (!cap) return null;
  const o = interpolate(recT - cap.t, [0, 350], [0, 1], clamp);
  return (
    <div style={{ position: "absolute", left: WIN_X, right: WIN_X, top: WIN_Y + WIN_H + 22, bottom: 20, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ margin: 0, fontSize: 38, lineHeight: 1.3, color: C.ink, textAlign: "center", opacity: o, translate: `0px ${(1 - o) * 10}px`, textWrap: "balance" }}>{cap.text}</p>
    </div>
  );
}

function Card({ index, opacity, local }: { index: number; opacity: number; local: number }) {
  const ch = chapters[index];
  return (
    <AbsoluteFill style={{ background: `radial-gradient(circle at 30% 30%, ${C.bg2}, ${C.bg})`, fontFamily: sans, justifyContent: "center", padding: "0 220px", opacity }}>
      <p style={{ margin: 0, fontSize: 34, fontWeight: 600, letterSpacing: 4, textTransform: "uppercase", color: C.accent }}>
        Step {index + 1} of {chapters.length}
      </p>
      <h1 style={{ margin: "18px 0 0", fontFamily: serif, fontSize: 96, fontWeight: 600, lineHeight: 1.05, color: C.ink, translate: `${interpolate(local, [0, 24], [24, 0], { ...clamp, easing: ease })}px 0px` }}>
        {ch.title}
      </h1>
      <p style={{ margin: "30px 0 0", fontSize: 44, color: C.ink2 }}>{ROLE[index]}</p>
    </AbsoluteFill>
  );
}

function Intro({ opacity, local }: { opacity: number; local: number }) {
  return (
    <AbsoluteFill style={{ background: `radial-gradient(circle at 30% 30%, ${C.bg2}, ${C.bg})`, fontFamily: sans, justifyContent: "center", padding: "0 220px", opacity }}>
      <p style={{ margin: 0, fontSize: 32, fontWeight: 600, letterSpacing: 4, textTransform: "uppercase", color: C.accent }}>App demo</p>
      <h1 style={{ margin: "14px 0 0", fontFamily: serif, fontSize: 150, fontWeight: 600, lineHeight: 1, color: C.ink, scale: String(interpolate(local, [0, 40], [0.96, 1], { ...clamp, easing: ease })), transformOrigin: "0 50%" }}>
        RAD-SMART
      </h1>
      <p style={{ margin: "30px 0 0", fontSize: 54, lineHeight: 1.25, color: C.ink, maxWidth: 1300 }}>How a radiotherapy department uses it, inside the CARE hospital system</p>
      <p style={{ margin: "34px 0 0", fontSize: 32, color: C.muted }}>A real recording of the app · every patient shown is synthetic</p>
    </AbsoluteFill>
  );
}

function Outro({ opacity, local }: { opacity: number; local: number }) {
  const steps = ["Predict", "Plan", "Test", "Tell"];
  return (
    <AbsoluteFill style={{ background: `radial-gradient(circle at 30% 30%, ${C.bg2}, ${C.bg})`, fontFamily: sans, justifyContent: "center", padding: "0 220px", opacity }}>
      <h1 style={{ margin: 0, fontFamily: serif, fontSize: 120, fontWeight: 600, color: C.ink }}>RAD-SMART</h1>
      <div style={{ display: "flex", gap: 18, marginTop: 34 }}>
        {steps.map((s, i) => (
          <span
            key={s}
            style={{ fontSize: 40, fontWeight: 600, color: C.ink, background: C.accentSoft, border: `1px solid ${C.accent}`, borderRadius: 14, padding: "12px 28px", opacity: interpolate(local, [10 + i * 6, 22 + i * 6], [0, 1], clamp) }}
          >
            {s}
          </span>
        ))}
        <span style={{ fontSize: 40, fontWeight: 600, color: C.ink, background: "rgba(235,104,52,0.16)", border: `1px solid ${C.warm}`, borderRadius: 14, padding: "12px 28px", opacity: interpolate(local, [40, 52], [0, 1], clamp) }}>
          A person decides
        </span>
      </div>
      <p style={{ margin: "56px 0 0", fontSize: 36, color: C.ink2 }}>psraghothamrao8.github.io/RAD-SMART</p>
      <p style={{ margin: "10px 0 0", fontSize: 30, color: C.muted }}>Code: github.com/psraghothamrao8/RAD-SMART</p>
    </AbsoluteFill>
  );
}

// ---- pointer and zoom state at a moment of the recording ----

function cursorAt(t: number) {
  let pos = { x: REC_W / 2, y: REC_H / 2 };
  for (const e of events) {
    if (e.type !== "move" || e.t > t) continue;
    const k = interpolate(t, [e.t, e.t + (e.dur ?? 600)], [0, 1], { ...clamp, easing: ease });
    pos = { x: (e.fromX ?? pos.x) + ((e.x ?? 0) - (e.fromX ?? pos.x)) * k, y: (e.fromY ?? pos.y) + ((e.y ?? 0) - (e.fromY ?? pos.y)) * k };
  }
  return pos;
}

type Z = { cx: number; cy: number; s: number };
const HOME: Z = { cx: REC_W / 2, cy: REC_H / 2, s: 1 };
const ZOOM_MS = 900;

function zoomAt(t: number): Z {
  let trans: { from: Z; to: Z; t0: number } | null = null;
  const at = (tr: NonNullable<typeof trans>, when: number): Z => {
    const k = interpolate(when, [tr.t0, tr.t0 + ZOOM_MS], [0, 1], { ...clamp, easing: ease });
    return { cx: tr.from.cx + (tr.to.cx - tr.from.cx) * k, cy: tr.from.cy + (tr.to.cy - tr.from.cy) * k, s: tr.from.s + (tr.to.s - tr.from.s) * k };
  };
  for (const e of events as Ev[]) {
    if (e.type !== "zoom" || e.t > t) continue;
    const from: Z = trans ? at(trans, e.t) : HOME;
    trans = { from, to: e.scale === 1 ? HOME : { cx: e.cx ?? HOME.cx, cy: e.cy ?? HOME.cy, s: e.scale ?? 1 }, t0: e.t };
  }
  return trans ? at(trans, t) : HOME;
}

export const DURATION = timeline.total;
