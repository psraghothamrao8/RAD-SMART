// Screenshots of the live demonstration for the slides, the brief and the website
// (docs/figures/app*.png), in headless Chrome. Synthetic demonstration data only.
// It puts one waiting patient first (Emergency) so the board shows the override, and
// takes it back at the end.
//
// usage: node scripts/screens.mjs [outDir]       default ../../docs/figures
// env:   HOST   the demonstration (default: the Azure server)
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const outDir = process.argv[2] || join(import.meta.dirname, "..", "..", "..", "docs", "figures");
const HOST = process.env.HOST || "https://radsmart.braveglacier-5f9807f7.uaenorth.azurecontainerapps.io";
const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
mkdirSync(outDir, { recursive: true });

const profile = join(process.env.TEMP || "/tmp", `radsmart-shots-${Date.now()}`);
const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=9335", `--user-data-dir=${profile}`, "--hide-scrollbars", "--window-size=1600,900", "about:blank"], { stdio: "ignore" });
let targets = [];
for (let i = 0; i < 60 && !targets.some((t) => t.type === "page"); i++) {
  try {
    targets = await fetch("http://127.0.0.1:9335/json").then((r) => r.json());
  } catch {}
  await sleep(200);
}
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) (pending.get(m.id)(m), pending.delete(m.id));
});
const send = (method, params = {}) => new Promise((r) => (pending.set(++id, r), ws.send(JSON.stringify({ id, method, params }))));
const js = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) throw new Error(`${expression.slice(0, 80)}: ${r.result.exceptionDetails.exception?.description}`);
  return r.result?.result?.value;
};
const size = (width, height, scale, mobile = false) => send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: scale, mobile });
async function waitFor(cond, ms = 60000) {
  for (const end = Date.now() + ms; Date.now() < end; await sleep(300)) {
    try {
      if (await js(`!!(${cond}) && !document.querySelector('.animate-spin')`)) return sleep(800);
    } catch {}
  }
  throw new Error(`timed out waiting for ${cond}`);
}
const go = async (path, ready) => (await send("Page.navigate", { url: HOST + path }), await sleep(1500), waitFor(ready));
const text = (s) => `document.body.innerText.includes(${JSON.stringify(s)})`;
// The element's box, grown by pad px, in page coordinates (the page is scrolled to it first).
const box = (sel, pad = 0) => js(`(() => { const e = ${sel}; e.scrollIntoView({block: "center"}); const r = e.getBoundingClientRect();
  return { x: r.left + scrollX - ${pad}, y: r.top + scrollY - ${pad}, width: r.width + ${2 * pad}, height: r.height + ${2 * pad}, scale: 1 }; })()`);
async function shot(name, clip) {
  await sleep(500);
  const r = await send("Page.captureScreenshot", { format: "png", ...(clip ? { clip, captureBeyondViewport: true } : {}) });
  writeFileSync(join(outDir, name), Buffer.from(r.result.data, "base64"));
  console.log(name);
}
const click = (sel) => js(`(${sel}).click(), true`);
const button = (label, within = "document") => `[...${within}.querySelectorAll("button")].find((b) => b.innerText.trim() === ${JSON.stringify(label)})`;
const rowOf = (name) => `[...document.querySelectorAll("tr")].find((t) => t.innerText.includes(${JSON.stringify(name)}))`;
const card = `[...document.querySelectorAll("section,div")].filter((d) => d.innerText.startsWith("Versa HD") && d.innerText.includes("Call next")).pop()`;

await size(1600, 900, 2);

// ---- the technologist's board, with one waiting patient put first ----
await go("/api/care_radsmart/try/technologist/", text("Call next"));
const pick = await js(`(() => {
  const rows = [...document.querySelectorAll("tr")].filter((t) => /\\bWaiting\\b/.test(t.innerText) && !/Call next/.test(t.innerText));
  const r = rows.pop(); return r && r.querySelector("a").innerText.trim(); })()`);
let name = pick;
if (!name) {   // nobody waiting but the next: take one still to come, and record the arrival
  name = await js(`(() => { const r = [...document.querySelectorAll("tr")].filter((t) => /To come/.test(t.innerText))[3]; return r.querySelector("a").innerText.trim(); })()`);
  await click(button("Arrived", rowOf(name)));
  await sleep(2500);
}
await click(button("First", rowOf(name)));
await sleep(400);
await click(button("Emergency", rowOf(name)));
await waitFor(`${rowOf(name)}.innerText.includes("Priority")`);
await js("scrollTo(0, 0)");
await shot("app1_today.png");
await shot("app13_queue.png", await box(card, 12));
await click(button("Here now"));
await sleep(1200);
await shot("app14_here_now.png", await box(`[...document.querySelectorAll("table")].pop().parentElement`, 8));
await click(button("All"));
await sleep(1200);
const offer = await js(`!!${rowOf("Ask the patient")}`);
if (offer) await shot("app15_offer.png", await box(rowOf("Ask the patient"), 6));
await click(button("Not first", rowOf(name)));   // back to plan order: the demonstration is shared
await sleep(1500);

// ---- the doctor's New course, with Emergency start ticked ----
await go("/api/care_radsmart/try/doctor/", text("Priority checklist"));
await js(`[...document.querySelectorAll("label")].find((l) => l.innerText.startsWith("Emergency start today")).querySelector("input").click()`);
await sleep(600);
await shot("app16_emergency.png", await box(`[...document.querySelectorAll("fieldset")][0]`, 10));

// ---- a patient's own page, at phone size ----
await size(390, 844, 3, true);
await go("/api/care_radsmart/try/patient/", "document.querySelector('.voice, .play, h1')");
await shot("app10_patient_phone.png");

ws.close();
chrome.kill();
