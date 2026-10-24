// Turns the narration in script.mjs into MP3s with Sarvam Bulbul v3 and writes
// public/narration/index.json ({key: {file, sec}}), which record.mjs and the video read.
// Each line is fetched once: a file named after the text is kept and reused, so changing
// one line re-voices only that line.
//
// usage: node narrate.mjs [--env-file <file with SARVAM_API_KEY>] [--dry]
//   --dry  calls nothing and estimates each line's length, for test recordings
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { INTRO, LINES, OUTRO } from "./script.mjs";

const OUT = join(import.meta.dirname, "..", "public", "narration");
const SPEAKER = process.env.SPEAKER || "shubh";
const PACE = 1.0;
const args = process.argv.slice(2);
const dry = args.includes("--dry");
const envFile = args.includes("--env-file") ? args[args.indexOf("--env-file") + 1] : null;
const key = process.env.SARVAM_API_KEY
  || (envFile && readFileSync(envFile, "utf8").split(/\r?\n/).find((l) => l.startsWith("SARVAM_API_KEY="))?.slice(15).trim());
if (!dry && !key) throw new Error("no SARVAM_API_KEY (pass --env-file or set it)");
mkdirSync(OUT, { recursive: true });

const all = { intro: { text: INTRO }, outro: { text: OUTRO }, ...LINES };
const index = {};
let chars = 0;
for (const [k, line] of Object.entries(all)) {
  const spoken = line.say || line.text;
  const file = `${createHash("sha1").update(`${SPEAKER}|${PACE}|${spoken}`).digest("hex").slice(0, 12)}.mp3`;
  const path = join(OUT, file);
  if (!existsSync(path) && !dry) {
    const r = await fetch("https://api.sarvam.ai/text-to-speech", {
      method: "POST",
      headers: { "Content-Type": "application/json", "api-subscription-key": key },
      body: JSON.stringify({ text: spoken, target_language_code: "en-IN", model: "bulbul:v3", speaker: SPEAKER, pace: PACE, output_audio_codec: "mp3" }),
    });
    if (!r.ok) throw new Error(`${k}: HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
    writeFileSync(path, Buffer.from((await r.json()).audios[0], "base64"));
    chars += spoken.length;
  }
  const sec = existsSync(path)
    ? Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).toString())
    : spoken.length / 14;   // a rough speaking rate, for dry runs
  index[k] = { file: existsSync(path) ? file : null, sec: Math.round(sec * 100) / 100 };
}
writeFileSync(join(OUT, "index.json"), JSON.stringify(index, null, 1));
const total = Object.values(index).reduce((s, x) => s + x.sec, 0);
console.log(`${Object.keys(index).length} lines, ${total.toFixed(0)} s of narration; voiced ${chars} new characters${dry ? " (dry run)" : ""}`);
