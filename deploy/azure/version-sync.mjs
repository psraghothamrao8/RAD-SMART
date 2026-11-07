// Run in the image's frontend stage, after CARE's build: no "A new version of CARE is
// available" prompt when a page loads.
//
// CARE's build gives itself a new random version (build-meta.json) every time, so after
// each redeploy anyone who had visited before was asked to update, though the page they
// had just loaded was already the newest: nginx never caches index.html. This puts a
// small script at the top of index.html that records the loaded build's version before
// CARE checks it, and clears the old build's offline copies as CARE's own update does.
// A tab left open across a redeploy still asks (CARE checks once a day): a silent reload
// there could lose a half-filled form.
import { readFileSync, writeFileSync } from "node:fs";

const { version } = JSON.parse(readFileSync("build/build-meta.json", "utf8"));
if (!/^[\w-]+$/.test(version)) throw new Error(`unexpected build version: ${version}`);

const script =
  "<script>try{var v=" + JSON.stringify(version) + ";" +
  "if(localStorage.getItem('app-version')!==v){" +
  "localStorage.setItem('app-version',v);" +
  "localStorage.setItem('app-last-updated',new Date().toISOString());" +
  "if('caches' in window)caches.keys().then(function(k){k.forEach(function(n){caches.delete(n)})});" +
  "}}catch(e){}</script>";

const page = readFileSync("build/index.html", "utf8");
if (!page.includes("<head>")) throw new Error("index.html has no <head>");
writeFileSync("build/index.html", page.replace("<head>", "<head>\n    " + script));
console.log(`index.html records build ${version} on load`);
