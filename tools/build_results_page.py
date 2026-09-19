"""Inline poc/results/web_data.json into the results-page template."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
template = (root / "docs/web/page_template.html").read_text(encoding="utf-8")
data = json.loads((root / "poc/results/web_data.json").read_text(encoding="utf-8"))
# "</" inside a <script> would end it early; "<\/" is the same string in JSON
blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", r"<\/")
out = root / "docs/web/rad-smart-prototype.html"
out.write_text(template.replace("/*DATA*/", blob), encoding="utf-8")
print("wrote", out, f"{out.stat().st_size / 1024:.0f} KB")
