// Drives the RAD-SMART CARE plugin through the demonstration story in headless Chrome and
// records it: screencast frames plus a log of pointer moves, clicks, captions and chapters,
// which the Remotion project turns into the demo video. Synthetic demonstration data only.
// Each caption waits for its narration (public/narration/index.json, from narrate.mjs) to
// finish before the next one, and the voice notes the app plays are saved beside the frames.
//
// usage: CARE_PW=<fixture password> node record.mjs <outDir>
// env:   FACILITY, PATIENT, ENCOUNTER (CARE ids), TZ_DEMO (browser time zone, so the demo
//        clock reads a working afternoon), HOST (care_fe), API (care backend)
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { LINES } from "./script.mjs";

const outDir = process.argv[2];
const HOST = process.env.HOST || "http://localhost:19101";
const API = process.env.API || "http://localhost:19100";
const F = process.env.FACILITY;
const P = process.env.PATIENT;
const E = process.env.ENCOUNTER;
const NAME = process.env.PATIENT_NAME || "Darsh Mandal"; // the recording patient; scripts/ids.py prints it
const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const W = 1600, H = 900, DSF = 1.2;
const PHONE = { w: 390, h: 844, dsf: 2 };
const SPEED = 1.15;   // the video plays the recording this much faster (src/timeline.ts)
const NARRATION = JSON.parse(readFileSync(join(import.meta.dirname, "..", "public", "narration", "index.json"), "utf8"));
let VH = H;           // the viewport height now: the phone chapter is recorded at phone size
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

rmSync(join(outDir, "frames"), { recursive: true, force: true });
mkdirSync(join(outDir, "frames"), { recursive: true });

async function token(user) {
  const r = await fetch(`${API}/api/v1/auth/login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: user, password: process.env.CARE_PW }),
  }).then((x) => x.json());
  if (!r.access) throw new Error(`login failed for ${user}`);
  return r;
}

// ---- Chrome and the DevTools protocol ----
const profile = join(process.env.TEMP || "/tmp", `radsmart-rec-${Date.now()}`);
const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=9334", `--user-data-dir=${profile}`, "--hide-scrollbars", "--autoplay-policy=no-user-gesture-required", `--window-size=${W},${H}`, "about:blank"], { stdio: "ignore" });
let targets;
for (let i = 0; i < 60; i++) {
  try {
    targets = await fetch("http://127.0.0.1:9334/json").then((r) => r.json());
    if (targets.some((t) => t.type === "page")) break;
  } catch {}
  await sleep(200);
}
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let msgId = 0;
const pending = new Map();
const handlers = {};
ws.addEventListener("message", (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m);
    pending.delete(m.id);
  } else if (m.method && handlers[m.method]) handlers[m.method](m.params);
});
const send = (method, params = {}) =>
  new Promise((resolve) => {
    const n = ++msgId;
    pending.set(n, resolve);
    ws.send(JSON.stringify({ id: n, method, params }));
  });
const evaluate = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) throw new Error(`${expression.slice(0, 80)}: ${r.result.exceptionDetails.exception?.description}`);
  return r.result?.result?.value;
};

// ---- the log ----
const t0 = Date.now();
const now = () => Date.now() - t0;
const frames = [];
const events = [];
const log = (type, data = {}) => events.push({ t: now(), type, ...data });
let cursor = { x: W / 2, y: H / 2 };

handlers["Page.screencastFrame"] = ({ data, metadata, sessionId }) => {
  const file = `f_${String(frames.length).padStart(5, "0")}.jpg`;
  writeFileSync(join(outDir, "frames", file), Buffer.from(data, "base64"));
  frames.push({ file, t: Math.round(metadata.timestamp * 1000 - t0) });
  send("Page.screencastFrameAck", { sessionId });
};

// ---- page helpers (run in the page) ----
const HELPERS = `
window.__vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
window.__byText = (text, sel, exact) => [...document.querySelectorAll(sel || "button,a,[role=tab],[role=radio],label")]
  .filter(__vis).filter((e) => { const t = (e.innerText || "").trim(); return exact ? t === text : t.includes(text); })
  .sort((x, y) => x.innerText.length - y.innerText.length)[0];
window.__field = (label) => { const l = [...document.querySelectorAll("label")].filter(__vis)
  .find((x) => (x.querySelector("span")?.innerText || "").trim() === label); return l && l.querySelector("input,select,textarea"); };
window.__rect = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; };
window.__set = (e, v) => { const proto = e.tagName === "SELECT" ? HTMLSelectElement.prototype : e.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(e, v); e.dispatchEvent(new Event(e.tagName === "SELECT" ? "change" : "input", { bubbles: true })); };
true;`;
const helpers = () => evaluate(HELPERS);

async function rectOf(js) {
  await helpers();
  return evaluate(`__rect(${js})`);
}
async function waitFor(js, ms = 30000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      await helpers();
      if (await evaluate(`!!(${js}) && !document.querySelector('.animate-spin')`)) return;
    } catch {}
    await sleep(250);
  }
  throw new Error(`timed out waiting for ${js}`);
}

// ---- actions ----
async function nav(path, ready) {
  await send("Page.navigate", { url: `${HOST}${path}` });
  await sleep(600);
  await waitFor(ready, 60000);
  await sleep(1200);
}
async function moveTo(x, y, dur = 700) {
  log("move", { x, y, dur, fromX: cursor.x, fromY: cursor.y });
  cursor = { x, y };
  await sleep(dur);
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
}
async function reveal(js) {
  // Bring the element into view with the mouse wheel, as a person would.
  for (let i = 0; i < 40; i++) {
    const r = await rectOf(js);
    if (!r) throw new Error(`not found: ${js}`);
    const cy = r.y + r.h / 2;
    if (cy > 90 && cy < VH - 110) return r;
    const dy = Math.max(-240, Math.min(240, cy - VH * 0.55));
    await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: cursor.x, y: cursor.y, deltaX: 0, deltaY: dy });
    await sleep(260);   // wheel scrolling is animated: let it settle before measuring again
    const after = await rectOf(js);
    if (after && Math.abs(after.y - r.y) < 1) return after;   // already at the top or bottom of the page
  }
  return rectOf(js);
}
async function scroll(total, step = 120) {
  const n = Math.ceil(Math.abs(total) / step);
  for (let i = 0; i < n; i++) {
    await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: cursor.x, y: cursor.y, deltaX: 0, deltaY: Math.sign(total) * step });
    await sleep(45);
  }
  await sleep(400);
}
async function hover(js, dur = 700) {
  const r = await reveal(js);
  await moveTo(Math.round(r.x + r.w / 2), Math.round(r.y + r.h / 2), dur);
  return r;
}
async function click(js, { dur = 700, pause = 500 } = {}) {
  const r = await reveal(js);
  const at = (q) => [Math.round(q.x + Math.min(q.w / 2, 60)), Math.round(q.y + q.h / 2)];
  let [x, y] = at(r);
  await moveTo(x, y, dur);
  const r2 = await rectOf(js);   // the page may have moved while the pointer travelled
  if (r2) {
    const [x2, y2] = at(r2);
    if (Math.abs(x2 - x) > 2 || Math.abs(y2 - y) > 2) {
      [x, y] = [x2, y2];
      await moveTo(x, y, 200);
    }
  }
  await sleep(120);
  log("click", { x, y });
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await sleep(70);
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
  await sleep(pause);
}
async function type(js, text, { delay = 55 } = {}) {
  await click(js, { pause: 200 });
  for (const ch of text) {
    await evaluate(`(() => { const e = ${js}; __set(e, e.value + ${JSON.stringify(ch)}); return true; })()`);
    await sleep(delay);
  }
  await sleep(300);
}
async function setValue(js, value) {
  // Selects, dates and times: point at the control, then set it (native pop-ups are not in the screencast).
  await click(js, { pause: 250 });
  await evaluate(`__set(${js}, ${JSON.stringify(value)})`);
  await sleep(600);
}
// The narration: a caption appears with its voice, and the next caption (or step) waits
// until the voice has finished. Actions carry on while it speaks.
let voiceEnd = 0;
async function voiceDone() {
  while (now() < voiceEnd) await sleep(50);
}
async function say(key) {
  const line = LINES[key], n = NARRATION[key];
  if (!line || !n) throw new Error(`no narration for ${key}: run narrate.mjs`);
  await voiceDone();
  log("caption", { text: line.text, key, file: n.file, sec: n.sec });
  voiceEnd = now() + n.sec * 1000 * SPEED + 350;
}
// `prep` (switching device, opening the first page) runs off camera: the video cuts
// from the end of the last step to the title card, and starts this step after it.
async function chapter(title, role, prep) {
  await voiceDone();
  if (prep) {
    log("cut");
    await prep();
  }
  log("chapter", { title, role });
}
// A voice note the app plays: saved for the video, which plays its first `sec` seconds.
let audioN = 0;
async function playAudio(url, headers, sec) {
  const r = await fetch(url, { headers });
  if (!r.ok) return console.warn(`voice note ${r.status}: ${url}`);
  const file = `audio_${++audioN}.mp3`;
  writeFileSync(join(outDir, file), Buffer.from(await r.arrayBuffer()));
  log("audio", { file, sec });
  voiceEnd = Math.max(voiceEnd, now() + sec * 1000 * SPEED + 300);
}
const zoom = (r, scale) => log("zoom", r ? { cx: r.x + r.w / 2, cy: r.y + r.h / 2, scale } : { scale: 1 });
async function fast(label, fn) {
  log("fast", { on: true, label });
  try { return await fn(); } finally { log("fast", { on: false }); }
}

let scriptId;
async function signIn(user) {
  const t = await token(user);
  if (scriptId) await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: scriptId });
  const r = await send("Page.addScriptToEvaluateOnNewDocument", {
    source: `localStorage.setItem("care_access_token", ${JSON.stringify(t.access)}); localStorage.setItem("care_refresh_token", ${JSON.stringify(t.refresh)});`,
  });
  scriptId = r.result.identifier;
}


// ---- the demonstration's patients, chosen through the API ----
const RS = `${API}/api/care_radsmart`;
const staffToken = (await token("care-staff")).access;
async function api(path) {
  const r = await fetch(`${RS}${path}${path.includes("?") ? "&" : "?"}facility=${F}`, { headers: { Authorization: `Bearer ${staffToken}` } });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json();
}
const TZ = process.env.TZ_DEMO || "America/Denver";
const hm = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date());
const nowMin = Number(hm.slice(0, 2)) * 60 + Number(hm.slice(3, 5));
const toMin = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
const soon = (await api("/day/")).sessions
  .filter((s) => s.demo && s.status === "scheduled" && toMin(s.report) > nowMin + 10)
  .sort((a, b) => a.start - b.start);
// One patient comes in today (their phone, then reception); another has said they will be late.
const arriving = soon.find((s) => s.language === "Kannada") || soon[0];
const late = soon.find((s) => arriving && s.course !== arriving.course);
if (!arriving || !late) throw new Error("no demonstration patients still to come today: reseed");
const arrivingLink = await api(`/courses/${arriving.course}/patient-link/`);
const lateLink = await api(`/courses/${late.course}/patient-link/`);
await fetch(lateLink.url, { method: "POST", body: new URLSearchParams({ kind: "late", minutes: "30" }), redirect: "manual" });
console.log(`arriving: ${arriving.patient_name} (${arriving.report}), late: ${late.patient_name}`);

// ---- set up ----
await send("Page.enable");
await send("Runtime.enable");
await send("Network.enable");
let audioUrl = null;   // the voice note the Messages page fetched last
handlers["Network.requestWillBeSent"] = ({ request }) => {
  if (/\/messages\/[^/]+\/audio\//.test(request.url)) audioUrl = request.url;
};
await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: DSF, mobile: false });
await send("Emulation.setTimezoneOverride", { timezoneId: TZ });
await signIn("care-doctor");
// warm up care_fe and the plugin so the recording does not open on a loading screen
await send("Page.navigate", { url: `${HOST}/facility/${F}/radsmart` });
await waitFor(`document.querySelector(".care-radsmart-container h1")`, 90000);
await sleep(1500);

const screencast = (w, h, dsf) => send("Page.startScreencast", { format: "jpeg", quality: 82, maxWidth: Math.round(w * dsf), maxHeight: Math.round(h * dsf), everyNthFrame: 1 });
// The patient's chapter is recorded at phone size; the video shows it in a phone.
async function phone(on) {
  await send("Page.stopScreencast");
  const [w, h, dsf] = on ? [PHONE.w, PHONE.h, PHONE.dsf] : [W, H, DSF];
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: dsf, mobile: on });
  VH = h;
  cursor = { x: w / 2, y: h / 2 };
  log("device", { phone: on, w, h });
  await screencast(w, h, dsf);
}
async function open(url, ready) {
  await send("Page.navigate", { url });
  await sleep(600);
  await waitFor(ready, 60000);
  await sleep(900);
}

const visit = `/facility/${F}/patient/${P}/encounter/${E}/updates`;
const rsButton = `document.querySelector('button[title*="RAD-SMART"]')`;
const tab = (t) => `__byText(${JSON.stringify(t)}, "a,button", true)`;
const btn = (t, exact = false) => `__byText(${JSON.stringify(t)}, "button,a", ${exact})`;
const field = (l) => `__field(${JSON.stringify(l)})`;
const text = (t, sel = "h1,h2,h3,p,span,div,td,legend") => `__byText(${JSON.stringify(t)}, ${JSON.stringify(sel)})`;
const rowOf = (name) => `[...document.querySelectorAll("tr")].filter(__vis).find((r) => r.innerText.includes(${JSON.stringify(name)}))`;
const inRow = (name, b) => `(${rowOf(name)}) && [...(${rowOf(name)}).querySelectorAll("button")].find((x) => x.innerText.trim() === ${JSON.stringify(b)})`;
const fit = (r, max = 1.4) => Math.max(1, Math.min(max, 1300 / r.w, 640 / r.h));

await nav(visit, rsButton);
await screencast(W, H, DSF);
await sleep(800);

try {
  // ======== 1 · Doctor: a new course ========
  await chapter("The doctor plans a new course", "Doctor");
  await sleep(1200);
  await say("visit");
  const b = await hover(rsButton, 900);
  zoom(b, 1.8);
  await sleep(2600);
  zoom(null);
  await click(rsButton, { pause: 300 });
  await waitFor(`__byText("New course", "button", true)`);
  await sleep(500);
  await say("newCourse");
  await click(`__byText("New course", "button", true)`);
  await waitFor(`__byText(${JSON.stringify(NAME)}, "p", true)`);
  await sleep(600);

  await say("prescription");
  await type(field("Hospital number"), "RT-2026-0412");
  await type(field("Diagnosis"), "Carcinoma cervix, stage IIB", { delay: 40 });
  await type(field("Total dose (Gy)"), "50");
  await type(field("Number of fractions"), "25");
  await setValue(field("Site"), "PELVIS");

  await say("ticks");
  await hover(text("Priority checklist", "h2,h3,p,div"), 600);
  await scroll(360);
  await click(`__byText("Travels by public transport", "label")`);
  await click(`__byText("Gap-sensitive radical course", "label")`);
  const older = await hover(`__byText("Older patient (70+)", "label")`, 700);
  await say("older");
  zoom(older, 1.6);
  await sleep(2800);
  zoom(null);

  await say("save");
  await click(btn("Save and propose slots"), { pause: 200 });
  await fast("RAD-SMART is planning", () => waitFor(text("Standing slot, every later fraction", "p,span,div"), 180000));
  await sleep(800);

  await say("proposal");
  const prop = await hover(text("Standing slot, every later fraction", "p,span,div"), 900);
  zoom({ x: 140, y: prop.y - 20, w: 1300, h: 260 }, 1.35);
  await sleep(3800);
  zoom(null);

  await say("explain");
  await click(btn("Explain in plain words"), { pause: 200 });
  await fast("Sarvam AI is writing", () => waitFor(btn("Explain again"), 60000));
  await sleep(500);
  const whyBox = `__byText("Why these times", "p", true).closest(".rounded-lg")`;
  const why = await reveal(whyBox);
  zoom(why, fit(why, 1.5));
  await moveTo(Math.round(why.x + why.w * 0.6), Math.round(why.y + why.h * 0.55), 900);
  await say("guard");
  await sleep(2500);
  zoom(null);

  await say("approve");
  await click(btn("Approve course and slots"), { pause: 200 });
  await fast("Saving", () => waitFor(text("Approved by", "dt,span,p,div"), 30000));
  await sleep(1200);
  const courseId = await evaluate(`location.pathname.split("/").filter(Boolean).pop()`);

  await say("link");
  const cardSel = `__byText("The patient's phone page", "h2", true).closest("section")`;
  const card = await reveal(cardSel);
  zoom(card, fit(card));
  await hover(btn("Send on WhatsApp"), 900);
  await sleep(2500);
  zoom(null);

  // ======== 2 · The patient's phone ========
  const own = await api(`/courses/${courseId}/patient-link/`);
  await chapter("The patient's phone", "Patient", async () => {
    await phone(true);
    await open(own.url, `document.querySelector("h1")`);
  });
  await say("phone");
  await hover(`document.querySelector("ul.next") || document.querySelector("h1")`, 900);
  await sleep(1500);
  const note = await evaluate(`document.querySelector(".voice audio")?.src || ""`);
  if (note) {
    await say("voice");
    // a real tap, so the page's Listen button turns to Pause and fills while the voice note plays
    await click(`document.querySelector(".play .ic")`, { pause: 0 });
    await playAudio(note, {}, 6);
  }
  await say("treatDay");
  await open(arrivingLink.url, `document.querySelector(".code")`);
  await hover(`document.querySelector(".code")`, 900);
  await sleep(1200);
  await say("tap");
  await click(`document.querySelector("button.primary")`, { pause: 300 });
  await waitFor(`document.querySelector(".note.ok")`);
  await sleep(600);
  await hover(`document.querySelector(".note.ok")`, 600);
  await sleep(1500);

  // ======== 3 · Reception ========
  const codeBox = `document.querySelector('.care-radsmart-container input[placeholder^="Six"]')`;
  await chapter("Reception checks the patient in", "Reception", async () => {
    await phone(false);
    await signIn("care-staff");
    await nav(`/facility/${F}/radsmart/checkin`, codeBox);
  });
  await say("scan");
  await hover(codeBox, 700);
  for (const ch of arrivingLink.code) {   // a barcode scanner types fast
    await evaluate(`(() => { const e = ${codeBox}; __set(e, e.value + ${JSON.stringify(ch)}); return true; })()`);
    await sleep(35);
  }
  await sleep(300);
  await click(btn("Check in", true), { pause: 300 });
  const listed = `__byText(${JSON.stringify(arriving.patient_name)}, "p,span,div,li,td")`;
  await waitFor(listed, 15000);
  await say("checkedIn");
  await hover(listed, 800);
  await sleep(1500);

  // ======== 4 · Technologist: the day ========
  await chapter("The technologist runs the day", "Technologist");
  await click(tab("Today"));
  await waitFor(`__byText("hard rules hold", "p,span,div") && document.querySelector(".care-radsmart-container svg[viewBox]")`);
  await sleep(800);
  await say("board");
  await hover(text("hard rules hold", "p,span,div"), 900);
  await sleep(1500);
  await say("blocks");
  const tlr = await reveal(`document.querySelector(".care-radsmart-container svg[role=img]")`);
  if (tlr) {
    zoom(tlr, 1.3);
    await moveTo(Math.round(tlr.x + tlr.w * 0.35), Math.round(tlr.y + tlr.h * 0.6), 1200);
    await moveTo(Math.round(tlr.x + tlr.w * 0.7), Math.round(tlr.y + tlr.h * 0.6), 1600);
    await voiceDone();
    zoom(null);
  }
  await say("replies");
  const repSel = `__byText("From patients' phones", "h2").closest("section")`;
  const rep = await reveal(repSel);
  zoom(rep, fit(rep));
  await hover(repSel, 800);
  await voiceDone();
  zoom(null);

  await say("taps");
  await reveal(inRow(arriving.patient_name, "In room"));
  const rr = await rectOf(rowOf(arriving.patient_name));
  if (rr) zoom({ x: 140, y: rr.y - 40, w: 1300, h: rr.h + 80 }, 1.3);
  await click(inRow(arriving.patient_name, "In room"), { pause: 1400 });
  await waitFor(inRow(arriving.patient_name, "Out"), 15000);
  await click(inRow(arriving.patient_name, "Out"), { pause: 1600 });
  zoom(null);

  // ======== 5 · Breakdown ========
  await chapter("The machine breaks down", "Technologist");
  await say("fault");
  await click(btn("Report breakdown"));
  await waitFor(btn("Take offline and propose"));
  await sleep(600);
  await setValue(field("Expected downtime"), "120");
  await type(field("What happened"), "MLC fault, engineer called", { delay: 45 });
  await click(btn("Take offline and propose"), { pause: 200 });
  await fast("Re-planning the day", () => waitFor(btn("Approve and notify"), 90000));
  await sleep(800);
  await say("replan");
  const tiles = await hover(text("Treated today", "p,span,div"), 900);
  zoom({ x: 140, y: tiles.y - 60, w: 1300, h: 260 }, 1.3);
  await voiceDone();
  zoom(null);
  await say("who");
  await scroll(420);
  await voiceDone();
  await say("approveFault");
  await click(btn("Approve and notify"), { pause: 600 });
  await waitFor(btn("Open messages"), 30000);
  await sleep(800);
  await click(btn("Open messages"), { pause: 300 });
  await fast("Sarvam AI is translating", () => waitFor(`${btn("Open WhatsApp")} && !${text("Translating into", "p,span,div")}`, 180000));
  await sleep(600);
  await say("messages");
  const msgSel = `${btn("Open WhatsApp")}.closest("section")`;
  const msg = await reveal(msgSel);
  zoom(msg, fit(msg));
  await hover(msgSel, 900);
  await voiceDone();
  if (await evaluate(`!!__byText("Listen", "button", true)`)) {
    await say("listen");
    audioUrl = null;
    await click(`__byText("Listen", "button", true)`, { pause: 200 });
    const until = Date.now() + 30000;
    while (!audioUrl && Date.now() < until) await sleep(100);
    if (audioUrl) await playAudio(audioUrl, { Authorization: `Bearer ${staffToken}` }, 5);
  }
  await say("whatsapp");
  await hover(btn("Open WhatsApp"), 800);
  await sleep(1400);
  await click(btn("Mark sent", true), { pause: 1200 });
  zoom(null);
  await click(tab("Today"));
  await waitFor(btn("Back online"));
  await sleep(800);
  await say("online");
  await click(btn("Back online"), { pause: 1500 });

  // ======== 6 · Insights ========
  await chapter("Is it working?", "Doctor and technologist");
  await click(tab("Insights"));
  await waitFor(text("Wait at the 90th percentile", "h2,h3,p,div"), 30000);
  await sleep(800);
  await say("insights");
  await hover(text("Wait, median", "p,span,div,dt"), 900);
  await sleep(1800);
  await scroll(300);
  await hover(text("Wait at the 90th percentile", "h2,h3,p,div"), 900);
  await voiceDone();
  await sleep(1200);
  log("end");
  await sleep(600);
} catch (e) {
  console.error("FAILED:", e.message);
  log("error", { message: e.message });
  const shot = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(outDir, "error.png"), Buffer.from(shot.result.data, "base64"));
} finally {
  await send("Page.stopScreencast");
  await sleep(300);
  writeFileSync(join(outDir, "rec.json"), JSON.stringify({ width: W, height: H, scale: DSF, phone: PHONE, speed: SPEED, frames, events }, null, 1));
  console.log(`frames ${frames.length}, events ${events.length}, ${(now() / 1000).toFixed(1)} s`);
  ws.close();
  chrome.kill();
}
