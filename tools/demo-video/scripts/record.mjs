// Drives the RAD-SMART CARE plugin through the demonstration story in headless Chrome and
// records it: screencast frames plus a log of pointer moves, clicks, captions and chapters,
// which the Remotion project turns into the demo video. Synthetic demonstration data only.
//
// usage: CARE_PW=<fixture password> node record.mjs <outDir>
// env:   FACILITY, PATIENT, ENCOUNTER (CARE ids), TZ_DEMO (browser time zone, so the demo
//        clock reads a working afternoon), HOST (care_fe), API (care backend)
import { spawn } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const outDir = process.argv[2];
const HOST = process.env.HOST || "http://localhost:19101";
const API = process.env.API || "http://localhost:19100";
const F = process.env.FACILITY;
const P = process.env.PATIENT;
const E = process.env.ENCOUNTER;
const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const W = 1600, H = 900, DSF = 1.2;
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
const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=9334", `--user-data-dir=${profile}`, "--hide-scrollbars", `--window-size=${W},${H}`, "about:blank"], { stdio: "ignore" });
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
    if (cy > 90 && cy < H - 110) return r;
    const dy = Math.max(-240, Math.min(240, cy - H * 0.55));
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
const caption = (text) => log("caption", { text });
const chapter = (title, role) => log("chapter", { title, role });
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

// ---- set up ----
await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: DSF, mobile: false });
await send("Emulation.setTimezoneOverride", { timezoneId: process.env.TZ_DEMO || "America/Denver" });
await signIn("care-doctor");
// warm up care_fe and the plugin so the recording does not open on a loading screen
await send("Page.navigate", { url: `${HOST}/facility/${F}/radsmart` });
await waitFor(`document.querySelector(".care-radsmart-container h1")`, 90000);
await sleep(1500);

const visit = `/facility/${F}/patient/${P}/encounter/${E}/updates`;
const rsButton = `document.querySelector('button[title*="RAD-SMART"]')`;
const tab = (t) => `__byText(${JSON.stringify(t)}, "a,button", true)`;
const btn = (t, exact = false) => `__byText(${JSON.stringify(t)}, "button,a", ${exact})`;
const field = (l) => `__field(${JSON.stringify(l)})`;
const text = (t, sel = "h1,h2,h3,p,span,div,td,legend") => `__byText(${JSON.stringify(t)}, ${JSON.stringify(sel)})`;

await nav(visit, rsButton);
await send("Page.startScreencast", { format: "jpeg", quality: 82, maxWidth: Math.round(W * DSF), maxHeight: Math.round(H * DSF), everyNthFrame: 1 });
await sleep(800);

try {
  // ======== 1 · Doctor: a new course ========
  chapter("The doctor plans a new course", "Doctor");
  await sleep(2600);
  caption("The doctor opens the patient's visit in CARE. RAD-SMART adds one button: RADSMART.");
  const b = await hover(rsButton, 900);
  zoom(b, 1.8);
  await sleep(2600);
  zoom(null);
  await click(rsButton, { pause: 300 });
  await waitFor(`__byText("New course", "button", true)`);
  await sleep(800);
  caption("It lists this patient's radiotherapy courses. The doctor starts a new one.");
  await sleep(1800);
  await click(`__byText("New course", "button", true)`);
  await waitFor(`__byText("Darsh Mandal", "p", true)`);
  await sleep(900);

  caption("The doctor enters the prescription, as on the paper form.");
  await type(field("Hospital number"), "RT-2026-0412");
  await type(field("Diagnosis"), "Carcinoma cervix, stage IIB", { delay: 40 });
  await type(field("Total dose (Gy)"), "50");
  await type(field("Number of fractions"), "25");
  await setValue(field("Site"), "PELVIS");
  await sleep(600);

  caption("Then ticks what matters for this patient. Each tick becomes a rule RAD-SMART must keep.");
  await hover(text("Priority checklist", "h2,h3,p,div"), 600);
  await scroll(360);
  await click(`__byText("Travels by public transport", "label")`);
  await click(`__byText("Gap-sensitive radical course", "label")`);
  const older = await hover(`__byText("Older patient (70+)", "label")`, 700);
  caption("Some ticks are automatic: this patient is 79, so 'older patient' is already ticked.");
  zoom(older, 1.6);
  await sleep(2800);
  zoom(null);
  await sleep(500);

  caption("Saving asks RAD-SMART to propose a time.");
  await click(btn("Save and propose slots"), { pause: 200 });
  await fast("RAD-SMART is planning", () => waitFor(text("RAD-SMART's proposal", "h2,h3,p,div"), 60000));
  await sleep(1200);

  caption("RAD-SMART proposes a first day before 17:00 and one standing time for the whole course.");
  const prop = await hover(text("Standing slot, every later fraction", "p,span,div"), 900);
  zoom({ x: 140, y: prop.y - 20, w: 1300, h: 260 }, 1.35);
  await sleep(4200);
  zoom(null);
  await sleep(400);
  caption("It explains why, and offers alternatives. The doctor stays in charge.");
  await hover(`document.querySelector('[role=radiogroup]')`, 800);
  await sleep(3000);
  caption("The doctor approves. The patient keeps this time every day until the course ends.");
  await click(btn("Approve course and slots"), { pause: 200 });
  await fast("Saving", () => waitFor(text("Approved by", "dt,span,p,div"), 30000));
  await sleep(1500);
  await scroll(520);
  await sleep(2500);

  caption("Back on the visit page, the button now shows the patient's daily time.");
  await nav(visit, `${rsButton} && ${rsButton}.innerText.includes("·")`);
  const b2 = await hover(rsButton, 900);
  zoom(b2, 1.8);
  await sleep(3200);
  zoom(null);
  await sleep(600);

  // ======== 2 · Technologist: the day ========
  await signIn("care-staff");
  chapter("The technologist runs the day", "Technologist");
  await nav(`/facility/${F}/radsmart`, `__byText("hard rules hold", "p,span,div") && document.querySelector(".care-radsmart-container svg[viewBox]")`);
  await sleep(2500);
  caption("Today's board: the machine, a check that every rule holds, and the day on a timeline.");
  await hover(text("hard rules hold", "p,span,div"), 900);
  await sleep(2400);
  caption("Each block is one patient: green for a new start, blue for a standing slot. The red line is now.");
  const tlr = await reveal(`document.querySelector(".care-radsmart-container svg[role=img]")`);
  if (tlr) {
    zoom(tlr, 1.3);
    await moveTo(Math.round(tlr.x + tlr.w * 0.35), Math.round(tlr.y + tlr.h * 0.6), 1200);
    await moveTo(Math.round(tlr.x + tlr.w * 0.7), Math.round(tlr.y + tlr.h * 0.6), 1600);
    await sleep(1200);
    zoom(null);
  } else await sleep(3000);
  await sleep(500);

  caption("When a patient arrives, the technologist taps Arrived, then In room, then Out.");
  const firstArrive = `__byText("Arrived", "button", true)`;
  await reveal(firstArrive);
  const row = `${firstArrive}.closest("tr")`;
  await evaluate(`(${row}).setAttribute("data-demo-row", "1"), true`).catch(() => {});
  const inRow = (t) => `document.querySelector('[data-demo-row]') && __byText(${JSON.stringify(t)}, "button", true) && [...document.querySelector('[data-demo-row]').querySelectorAll("button")].find((b) => b.innerText.trim() === ${JSON.stringify(t)})`;
  const rr = await rectOf(`document.querySelector('[data-demo-row]')`);
  if (rr) zoom({ x: 140, y: rr.y - 40, w: 1300, h: rr.h + 80 }, 1.3);
  await click(firstArrive, { pause: 1400 });
  await waitFor(inRow("In room"), 15000);
  await click(inRow("In room"), { pause: 1400 });
  await waitFor(inRow("Out"), 15000);
  caption("These taps measure the real waiting time, so the department can see if waits are falling.");
  await click(inRow("Out"), { pause: 1800 });
  zoom(null);
  await sleep(800);

  // ======== 3 · A patient asks for another time ========
  chapter("A patient asks for another time", "Technologist");
  await click(tab("Courses"));
  await waitFor(`document.querySelector('input[placeholder="Name or hospital number"]')`);
  await sleep(800);
  caption("The patient asks to come earlier, because of the bus home. The technologist opens the course.");
  await type(`document.querySelector('input[placeholder="Name or hospital number"]')`, "Darsh", { delay: 90 });
  const active = `[...document.querySelectorAll("a")].filter(__vis).find((a) => a.innerText.trim() === "Darsh Mandal" && !(a.closest("tr")?.innerText || "").includes("Cancelled"))`;
  await waitFor(active);
  await sleep(700);
  await click(active);
  await waitFor(text("The patient asks for another time", "p"));
  await sleep(900);
  await hover(text("The patient asks for another time", "p"), 800);
  await sleep(600);
  await setValue(field("Asks for"), "16:00");
  await type(field("Reason"), "Bus timing", { delay: 70 });
  caption("RAD-SMART finds the nearest time that keeps every rule for every patient.");
  await click(btn("Find a time", true), { pause: 200 });
  await fast("RAD-SMART is checking the rules", () => waitFor(`document.querySelector('[role=radiogroup]')`, 60000));
  await sleep(900);
  const rg = await hover(`document.querySelector('[role=radiogroup]')`, 800);
  zoom({ x: 140, y: rg.y - 30, w: 1300, h: 200 }, 1.35);
  await sleep(2400);
  await click(`[...document.querySelectorAll('[role=radio]')].filter((b) => !b.innerText.includes("current slot")).sort((x, y) => y.innerText.includes("recommended") - x.innerText.includes("recommended"))[0]`, { pause: 1200 });
  zoom(null);
  caption("The time changes only when someone approves it.");
  await click(`[...document.querySelectorAll("button")].filter(__vis).find((b) => b.innerText.trim().startsWith("Approve"))`, { pause: 2200 });
  await sleep(1200);

  // ======== 4 · Breakdown ========
  chapter("The machine breaks down", "Technologist");
  await click(tab("Today"));
  await waitFor(btn("Report breakdown"));
  await sleep(900);
  caption("The machine fails. The technologist reports it and gives the engineer's estimate.");
  await click(btn("Report breakdown"));
  await waitFor(btn("Take offline and propose"));
  await sleep(900);
  await setValue(field("Expected downtime"), "120");
  await type(field("What happened"), "MLC fault, engineer called", { delay: 45 });
  await click(btn("Take offline and propose"), { pause: 200 });
  await fast("Re-planning the day", () => waitFor(btn("Approve and notify"), 90000));
  await sleep(1200);
  caption("In seconds, RAD-SMART proposes a new plan that follows the department's breakdown rules.");
  const tiles = await hover(text("Treated today", "p,span,div"), 900);
  zoom({ x: 140, y: tiles.y - 60, w: 1300, h: 260 }, 1.3);
  await sleep(4200);
  zoom(null);
  await sleep(500);
  caption("Who gets a new time, who comes back another day, and why. Patients still at home are asked to wait.");
  await scroll(420);
  await sleep(3800);
  caption("Nothing changes until a technologist or doctor approves. Messages are drafted in the patient's language.");
  await click(btn("Approve and notify"), { pause: 2400 });
  await sleep(800);
  await click(tab("Today"));
  await waitFor(btn("Back online"));
  await sleep(1200);
  caption("When the engineer fixes it, one tap brings the machine back online.");
  await click(btn("Back online"), { pause: 2200 });

  // ======== 5 · Insights ========
  chapter("Is it working?", "Doctor and technologist");
  await click(tab("Insights"));
  await waitFor(text("Wait at the 90th percentile", "h2,h3,p,div"), 30000);
  await sleep(1200);
  caption("Insights shows the measured waits against today's baseline (109 min) and the 25% lower target.");
  await hover(text("Wait, median", "p,span,div,dt"), 900);
  await sleep(2200);
  await scroll(300);
  await hover(text("Wait at the 90th percentile", "h2,h3,p,div"), 900);
  await sleep(4200);
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
  writeFileSync(join(outDir, "rec.json"), JSON.stringify({ width: W, height: H, scale: DSF, frames, events }, null, 1));
  console.log(`frames ${frames.length}, events ${events.length}, ${(now() / 1000).toFixed(1)} s`);
  ws.close();
  chrome.kill();
}
