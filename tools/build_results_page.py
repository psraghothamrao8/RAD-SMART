"""Inline poc/results/web_data.json into the results-page template.

Writes two copies:
- docs/web/rad-smart-prototype.html: page body only, for the Claude artifact
- docs/index.html: a complete HTML document, served by GitHub Pages from docs/
"""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
template = (root / "docs/web/page_template.html").read_text(encoding="utf-8")
data = json.loads((root / "poc/results/web_data.json").read_text(encoding="utf-8"))
# "</" inside a <script> would end it early; "<\/" is the same string in JSON
blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", r"<\/")
page = template.replace("/*DATA*/", blob)

standalone = (
    '<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    '<meta name="description" content="Interactive results from the RAD-SMART proof of concept on synthetic data: '
    'waits, an optimised treatment day, machine-fault recovery and two-machine new-start planning.">\n'
    + page + "\n</html>\n"
)

for out, text in [(root / "docs/web/rad-smart-prototype.html", page), (root / "docs/index.html", standalone)]:
    out.write_text(text, encoding="utf-8")
    print("wrote", out, f"{out.stat().st_size / 1024:.0f} KB")
# serve docs/ as plain files, without Jekyll processing
(root / "docs/.nojekyll").touch()
