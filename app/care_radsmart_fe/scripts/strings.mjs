// Collect every tr("key", "English") call into public/locale/en.json (keys get the radsmart__ prefix).
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const files = [];
const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.tsx?$/.test(name)) files.push(p);
  }
};
walk("src");

const out = { radsmart__page_title: "RAD-SMART" };
const call = /\btr\(\s*"([a-z0-9_]+)",\s*"((?:[^"\\]|\\.)*)"/g;
for (const f of files) {
  for (const [, key, text] of readFileSync(f, "utf8").matchAll(call)) {
    const k = `radsmart__${key}`;
    const v = JSON.parse(`"${text}"`);
    if (out[k] !== undefined && out[k] !== v) console.warn(`${k}: two texts ("${out[k]}" / "${v}")`);
    out[k] ??= v;
  }
}
const sorted = Object.fromEntries(Object.entries(out).sort(([a], [b]) => a.localeCompare(b)));
writeFileSync("public/locale/en.json", `${JSON.stringify(sorted, null, 2)}\n`);
console.log(`${Object.keys(sorted).length} strings`);
