"""Build the pitch deck for GitHub from its slide sources.

Sources: docs/deck/src/deck.json and docs/deck/src/slides/<id>.html, a copy of the
"RAD-SMART Pitch Deck" Claude artifact (1920x1080 slides in a small inline-CSS subset).

Writes:
- docs/deck/index.html: web version, served by GitHub Pages at /deck/
- docs/deck/RAD-SMART_Pitch_Deck.pdf: one 1920x1080 page per slide (needs Google Chrome)

Run: python tools/build_deck.py
"""
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
deck_dir = root / "docs/deck"
src = deck_dir / "src"
deck = json.loads((src / "deck.json").read_text(encoding="utf-8"))

# images uploaded to the artifact, and the report figures they came from
BLOBS = {
    "/_blob/1e5107b2dbca1be2330a5eb608ec5795": "../figures/fig1_wait_distribution.png",
    "/_blob/25c3c9ef31c5bb8ea625d623b8f4755f": "../figures/fig3_optimised_day.png",
    "/_blob/d9563dfa3becc271462d1e3f5316ec9d": "../figures/fig4c_fault_waiting_room.png",
    "/_blob/ddc7ca7e17059a694bd53325b4bac621": "../figures/fig5_capacity_forecast.png",
}

frames = []
for n, sid in enumerate(deck["order"], 1):
    s = (src / "slides" / f"{sid}.html").read_text(encoding="utf-8")
    for blob, path in BLOBS.items():
        s = s.replace(blob, path)
    missing = re.findall(r"/_blob/[0-9a-f]+", s)
    if missing:
        raise SystemExit(f"{sid}: no local file for {missing}")
    notes = re.search(r"<aside>(.*?)</aside>", s, re.S)
    note_html = (f'<details class="notes"><summary>Speaker notes</summary><p>{notes.group(1).strip()}</p></details>'
                 if notes else "")
    frames.append(f'<figure class="slide" id="s{n}" aria-label="Slide {n} of {len(deck["order"])}">'
                  f'<div class="frame"><div class="canvas">{s.strip()}</div></div>{note_html}</figure>')

fonts = "\n".join(f'<link rel="stylesheet" href="{html.escape(f["href"])}">' for f in deck["faces"].values())
title = html.escape(deck["title"])
page = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="RAD-SMART pitch deck, Health-a-thon 2026 (Cancer track): AI-assisted radiotherapy scheduling, machine allocation and resource tracking.">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
{fonts}
<style>
  :root {{ color-scheme: dark; --bg: #15191e; --ink: #e8ecf1; --muted: #a3adb9; --line: #2b323b; --link: #8dbbf2; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.5 'IBM Plex Sans', Arial, sans-serif; }}
  a {{ color: var(--link); }}
  header.top {{ max-width: 1280px; margin: 0 auto; padding: 28px 16px 8px; display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: baseline; justify-content: space-between; }}
  header.top h1 {{ margin: 0; font: 600 24px/1.2 'Source Serif 4', Georgia, serif; }}
  header.top nav {{ display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 15px; }}
  header.top p {{ margin: 0; width: 100%; color: var(--muted); font-size: 14px; }}
  .deck {{ max-width: 1280px; margin: 0 auto; padding: 16px 16px 48px; display: grid; gap: 28px; }}
  .slide {{ margin: 0; }}
  .frame {{ position: relative; width: 100%; aspect-ratio: 16 / 9; overflow: hidden; border-radius: 8px; box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35); background: #fff; }}
  .canvas {{ position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; transform-origin: 0 0; }}
  .notes {{ margin-top: 8px; color: var(--muted); font-size: 14px; }}
  .notes summary {{ cursor: pointer; width: max-content; }}
  .notes p {{ margin: 6px 0 0; max-width: 900px; }}
  footer {{ max-width: 1280px; margin: 0 auto; padding: 0 16px 40px; color: var(--muted); font-size: 14px; }}

  /* the slide canvas: 1920x1080, inline styles on top of these defaults */
  .canvas section {{ position: relative; width: 1920px; height: 1080px; display: flex; flex-direction: column; overflow: hidden; color: #000; }}
  .canvas section * {{ margin: 0; box-sizing: border-box; }}
  .canvas section div {{ display: flex; flex-direction: column; }}
  .canvas h1 {{ font-size: 96px; font-weight: 600; line-height: 1.1; }}
  .canvas h2 {{ font-size: 64px; font-weight: 600; line-height: 1.15; }}
  .canvas h3 {{ font-size: 44px; font-weight: 600; line-height: 1.2; }}
  .canvas p {{ line-height: 1.4; }}
  .canvas ul, .canvas ol {{ padding-left: 1.15em; }}
  .canvas li + li {{ margin-top: 0.3em; }}
  .canvas img {{ display: block; }}
  .canvas table {{ border-collapse: collapse; }}
  .canvas th, .canvas td {{ border: 1px solid #d9dfe6; padding: 0.35em 0.6em; text-align: left; vertical-align: top; }}
  .canvas th {{ font-weight: 600; }}
  .canvas aside {{ display: none; }}
  .canvas x-shape {{ display: block; }}
  .canvas x-shape[kind="arrow-right"] {{ clip-path: polygon(0 30%, 60% 30%, 60% 0, 100% 50%, 60% 100%, 60% 70%, 0 70%); }}

  @page {{ size: 1920px 1080px; margin: 0; }}
  @media print {{
    html, body {{ background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    header.top, .notes, footer {{ display: none; }}
    .deck {{ max-width: none; padding: 0; gap: 0; display: block; }}
    .frame {{ width: 1920px; height: 1080px; aspect-ratio: auto; border-radius: 0; box-shadow: none; break-after: page; }}
    .canvas {{ transform: none !important; }}
  }}
</style>
<header class="top">
  <h1>{title}</h1>
  <nav>
    <a href="RAD-SMART_Pitch_Deck.pdf">Download PDF</a>
    <a href="../">Interactive results</a>
    <a href="../RAD-SMART_Research_Report.pdf">Research report</a>
    <a href="https://github.com/psraghothamrao8/RAD-SMART">Source code</a>
  </nav>
  <p>{len(frames)} slides · use the arrow keys or Page Up / Page Down to move between slides · all data synthetic</p>
</header>
<main class="deck">
{chr(10).join(frames)}
</main>
<footer>RAD-SMART · Health-a-thon 2026 · Doctor partner: Dr Akshay Dinesan, Manipal · Assistive, not diagnostic</footer>
<script>
(function () {{
  var frames = Array.prototype.slice.call(document.querySelectorAll(".frame"));
  function fit() {{
    frames.forEach(function (f) {{ f.firstElementChild.style.transform = "scale(" + (f.clientWidth / 1920) + ")"; }});
  }}
  window.addEventListener("resize", fit);
  fit();
  var slides = Array.prototype.slice.call(document.querySelectorAll(".slide"));
  document.addEventListener("keydown", function (ev) {{
    var next = ev.key === "ArrowRight" || ev.key === "ArrowDown" || ev.key === "PageDown" || (ev.key === " " && !ev.shiftKey);
    var prev = ev.key === "ArrowLeft" || ev.key === "ArrowUp" || ev.key === "PageUp" || (ev.key === " " && ev.shiftKey);
    if (!next && !prev) return;
    var y = window.scrollY + 40, i = 0;
    slides.forEach(function (s, k) {{ if (s.offsetTop <= y) i = k; }});
    var t = slides[Math.max(0, Math.min(slides.length - 1, i + (next ? 1 : -1)))];
    ev.preventDefault();
    window.scrollTo({{ top: t.offsetTop - 16, behavior: "smooth" }});
  }});
}})();
</script>
</html>
"""
out = deck_dir / "index.html"
out.write_text(page, encoding="utf-8")
print("wrote", out, f"{out.stat().st_size / 1024:.0f} KB")

chrome = next((p for p in [shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium"),
                           r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"] if p and Path(p).exists()), None)
if not chrome:
    raise SystemExit("Google Chrome not found; the web version was built but the PDF was not")
pdf = deck_dir / "RAD-SMART_Pitch_Deck.pdf"
subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=15000",
                f"--print-to-pdf={pdf}", out.as_uri()], check=True, capture_output=True)
print("wrote", pdf, f"{pdf.stat().st_size / 1024:.0f} KB")
