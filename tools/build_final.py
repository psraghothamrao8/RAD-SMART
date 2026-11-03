"""The final-round deliverables, filled into the organisers' Health-a-thon 2026 templates.

Reads the two templates the organisers sent (new_mail/, not committed) and writes
  docs/RAD-SMART_Final_Presentation.pptx   the final presentation (12 template slides,
                                           with the two second slides it allows)
  docs/RAD-SMART_Solution_Brief.pptx       the two-page overview
The templates' logo, titles, footers and fonts are kept; their instructions are replaced.
One message per slide, set large, with screenshots of the live demonstration
(docs/figures/app*.png, from tools/demo-video/scripts/screens.mjs) and the department's
own figures. Every number comes from docs/Phase2_Submission.md and the evaluation.

Run: python tools/build_final.py   (needs python-pptx and Pillow)
"""
import copy
import io
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

root = Path(__file__).resolve().parent.parent
docs, fig = root / "docs", root / "docs" / "figures"
DECK_TEMPLATE = root / "new_mail" / "PPT_Final_Teamplate_Health-a-thon 2026.pptx"
BRIEF_TEMPLATE = root / "new_mail" / "Two-page Solution Brief Template.pptx"
DECK, BRIEF = docs / "RAD-SMART_Final_Presentation.pptx", docs / "RAD-SMART_Solution_Brief.pptx"

TEAM, CODE_ = "RAD-SMART", "YU8PAK"
CONTACT = "akshay.dinesan@manipal.edu"
SITE = "https://psraghothamrao8.github.io/RAD-SMART/"
VIDEO = SITE + "#demo"
REPO = "https://github.com/psraghothamrao8/RAD-SMART"
MVP = "https://radsmart.braveglacier-5f9807f7.uaenorth.azurecontainerapps.io"   # redirects to the tour
LIVE = MVP + "/api/care_radsmart/try/"

# the template's own colours; a hairline and one quiet tint
BLUE, GREEN, DARK, GRAY, LINE, TINT, PALE = "1F3DA9", "0D8743", "232F3E", "5D6A79", "D5DBE3", "F1F4FA", "B9C0CA"
HEAD, BODY = "Arial", "Calibri"
L, R, TOP, BOTTOM = 0.45, 12.88, 1.5, 6.95
W = R - L


def rgb(h):
    return RGBColor.from_string(h)


def _plain(shape):
    st = shape._element.find(qn("p:style"))
    if st is not None:
        shape._element.remove(st)


def _run(p, text, size, color, bold=False, font=BODY, link=None, italic=False):
    r = p.add_run()
    r.text = text
    f = r.font
    f.size, f.bold, f.italic, f.name = Pt(size), bold, italic, font
    f.color.rgb = rgb(color)
    if link:
        r.hyperlink.address = link
    return r


def _bullet(p, color, indent=0.2):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(Emu(Inches(indent))))
    pPr.set("indent", str(-Emu(Inches(indent))))
    for tag, attrs in (("a:buClr", None), ("a:buFont", {"typeface": "Arial"}), ("a:buChar", {"char": "•"})):
        el = pPr.makeelement(qn(tag), attrs or {})
        if tag == "a:buClr":
            el.append(el.makeelement(qn("a:srgbClr"), {"val": color}))
        pPr.append(el)


def fill(tf, items, size=14, color=DARK, align=PP_ALIGN.LEFT, gap=4, accent=BLUE, line=1.05):
    """items: strings, or (kind, text[, extra]) with kind
    p paragraph, h heading, b bullet, n big number, cap caption, link (text, url).
    **bold** marks bold runs inside p, b and cap."""
    for i, it in enumerate(items):
        kind, text = ("p", it) if isinstance(it, str) else it[:2]
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment, p.line_spacing, p.space_after = align, line, Pt(gap)
        if kind == "h":
            _run(p, text, it[2] if len(it) > 2 else size + 2, DARK, bold=True, font=HEAD)
            p.space_after = Pt(3)
        elif kind == "n":
            _run(p, text, it[2] if len(it) > 2 else 40, it[3] if len(it) > 3 else accent, bold=True, font=HEAD)
            p.space_after, p.line_spacing = Pt(0), 0.95
        elif kind == "link":
            _run(p, text, size, BLUE, link=it[2])
        else:
            sz = it[2] if kind == "cap" and len(it) > 2 else size - 2.5 if kind == "cap" else size
            col = GRAY if kind == "cap" else color
            for j, chunk in enumerate(text.split("**")):
                if chunk:
                    _run(p, chunk, sz, col, bold=j % 2 == 1)
            if kind == "b":
                _bullet(p, accent)


def text(slide, x, y, w, h, items, anchor="t", name=None, **kw):
    s = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = s.text_frame
    tf.word_wrap, tf.auto_size = True, MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    if name:
        s.name = name
    fill(tf, items, **kw)
    return s


def rect(slide, x, y, w, h, color=TINT, line=None, shape=MSO_SHAPE.RECTANGLE, name=None):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if color:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(color)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb, s.line.width = rgb(line), Pt(0.75)
    else:
        s.line.fill.background()
    _plain(s)
    if name:
        s.name = name
    return s


def rule(slide, x, y, w, color=LINE, weight=0.75, vertical=False):
    x2, y2 = (x, y + w) if vertical else (x + w, y)
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y), Inches(x2), Inches(y2))
    c.line.color.rgb, c.line.width = rgb(color), Pt(weight)
    _plain(c)
    c.name = "Rule"
    return c


def arrow(slide, x, y, w):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y), Inches(x + w), Inches(y))
    c.line.color.rgb, c.line.width = rgb(GRAY), Pt(1.25)
    _plain(c)
    ln = c.line._get_or_add_ln()
    ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    c.name = "Arrow"
    return c


def shot(slide, path, x, y, w=None, h=None, focus=None, alt="", border=True, crop=None):
    """A screenshot, first cut to `crop` (pixels) if given. With both w and h and a focus
    (fx, fy), it is cropped to that box around the focus point, so screenshots line up."""
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    if w and h and focus:
        want = w / h
        if im.width / im.height > want:      # too wide: keep the height
            cw = int(im.height * want)
            cx = int(min(max(focus[0] * im.width - cw / 2, 0), im.width - cw))
            im = im.crop((cx, 0, cx + cw, im.height))
        else:
            ch = int(im.width / want)
            cy = int(min(max(focus[1] * im.height - ch / 2, 0), im.height - ch))
            im = im.crop((0, cy, im.width, cy + ch))
    elif w and not h:
        h = w * im.height / im.width
    elif h and not w:
        w = h * im.width / im.height
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    buf.seek(0)
    pic = slide.shapes.add_picture(buf, Inches(x), Inches(y), Inches(w), Inches(h))
    pic._element.nvPicPr.cNvPr.set("descr", alt)
    pic.name = "Screenshot: " + alt[:40]
    if border:
        pic.line.color.rgb, pic.line.width = rgb(LINE), Pt(0.75)
    return w, h


def number(slide, x, y, w, value, label, color=BLUE, size=40, label_size=13):
    return text(slide, x, y, w, 1.3, [("n", value, size, color), ("cap", label, label_size)], gap=2,
                name=f"Figure: {value}")


# ---------------------------------------------------------------- template frame

def set_text(shape, new):
    """Replace a template text box's text, keeping its first run's look."""
    p = shape.text_frame.paragraphs[0]
    p.runs[0].text = new
    for r in p.runs[1:]:
        r._r.getparent().remove(r._r)
    for extra in shape.text_frame.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)


def replace(shape, old, new):
    """Swap a placeholder inside a template paragraph, keeping the runs around it."""
    for p in shape.text_frame.paragraphs:
        for r in p.runs:
            if old in r.text:
                r.text = r.text.replace(old, new)
                return True
    for p in shape.text_frame.paragraphs:        # the placeholder spans runs: merge them into the first
        full = "".join(r.text for r in p.runs)
        if old in full:
            p.runs[0].text = full.replace(old, new)
            for r in p.runs[1:]:
                r._r.getparent().remove(r._r)
            return True
    return False


def frame(slide, title, message=None):
    """Keep the logo, title and footer; drop the template's instructions; add the slide's message."""
    for s in list(slide.shapes):
        if s.shape_type != MSO_SHAPE_TYPE.PICTURE and 1.0 < Emu(s.top).inches < 7.0:
            s._element.getparent().remove(s._element)
    title_box = min((s for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip()), key=lambda s: s.top)
    set_text(title_box, title)
    if message:
        text(slide, L, 0.95, W, 0.45, [message], size=16, color=GRAY, name="Message")


def clone(prs, index):
    """Copy slide `index` (logo, title, footer) to a new slide right after it."""
    src = prs.slides[index]
    new = prs.slides.add_slide(src.slide_layout)
    for s in list(new.shapes):
        s._element.getparent().remove(s._element)
    for s in src.shapes:
        if s.shape_type == MSO_SHAPE_TYPE.PICTURE:
            new.shapes.add_picture(io.BytesIO(s.image.blob), s.left, s.top, s.width, s.height)
        else:
            new.shapes._spTree.append(copy.deepcopy(s._element))
    ids = prs.slides._sldIdLst
    el = list(ids)[-1]
    ids.remove(el)
    ids.insert(index + 1, el)
    return new


def notes(slide, words):
    slide.notes_slide.notes_text_frame.text = words


# ================================================================ the presentation
prs = Presentation(str(DECK_TEMPLATE))
clone(prs, 7)   # evaluation: two slides
clone(prs, 4)   # solution: two slides
S = list(prs.slides)

# ---- 1. title
t = S[0]
for s in t.shapes:
    if not s.has_text_frame:
        continue
    replace(s, "[Solution Name]", "RAD-SMART")
    replace(s, "[Short subtitle explaining what your solution does]",
            "Radiotherapy appointments that hold: one daily time per patient, a new plan in seconds "
            "when the machine breaks down, and messages in the patient's own language")
    replace(s, "[Insert team name]", TEAM)
    replace(s, "[Insert team code]", CODE_)
notes(t, "RAD-SMART schedules radiotherapy inside CARE, the open-source hospital system, for a "
         "department with one machine.")

# ---- 2. team
s = S[1]
frame(s, "Team Overview & Background",
      "Doctors from the department RAD-SMART is built for, and the engineers who built it with them.")
team = [
    ("Dr Akshay Dinesan", "Team leader, doctor partner",
     "Wrote the problem statement from daily work; owns the clinical rules and the pilot"),
    ("Dr Shirley Lewis Salins", "Doctor partner", "Clinical review of the department's rules and the design"),
    ("Dr Umesh Velu", "Doctor partner", "Clinical review of the department's rules and the design"),
    ("Abhinand T M", "Technical lead", "Coordinates the team, the doctors and the submissions; reviews the build"),
    ("P S Raghotham Rao", "Lead engineer",
     "Built the scheduling engine, the digital twin, the CARE plugin and the Sarvam AI layer"),
]
y = TOP + 0.05
for i, (name, role, did) in enumerate(team):
    if i:
        rule(s, L, y - 0.12, 7.35)
    text(s, L, y, 2.75, 0.8, [("h", name, 15), ("cap", role, 12.5)], gap=1)
    text(s, L + 2.95, y + 0.02, 4.4, 0.8, [did], size=13.5, color=DARK)
    y += 1.03
x2 = 8.35
rect(s, x2, TOP, R - x2, BOTTOM - TOP, TINT, name="Background panel")
text(s, x2 + 0.3, TOP + 0.25, R - x2 - 0.6, 5.0, [
    ("h", "The department", 15),
    "Radiotherapy, Kasturba Medical College, Manipal (MAHE). One Elekta Versa HD treats 70 to 90 patients a day, "
    "08:30 until about 01:00; a second machine arrives in 2027.",
    ("h", "The doctor partner's role", 15),
    "Dr Akshay Dinesan brought the problem and the department's own records. The technologists' and doctors' "
    "written answers (21 Sep, 24 Oct) are in the code as rules, and their feedback (27 Oct) added preferred "
    "times and treating patients out of turn.",
    ("h", "The platform", 15),
    "CARE, the open-source hospital information system of the Open Healthcare Network. RAD-SMART is a "
    "plugin: it uses CARE's patients, staff and roles, with no change to CARE.",
], size=13, gap=8)
notes(s, "Five people: three doctors from the department and two engineers.")

# ---- 3. problem
s = S[2]
frame(s, "Problem Statement and Supporting Evidence",
      "One machine, 70 to 90 patients a day, and the delay builds up every day of a one to seven week course.")
pw, ph = shot(s, fig / "fig0_department_records.png", L, TOP + 0.05, w=7.6,
              alt="The department's records: waits build up through the day")
text(s, L, TOP + 0.15 + ph, 7.6, 0.4, [("cap", "55 working days, used only as anonymised totals.", 11)])
x2 = 8.55
for i, (v, lab) in enumerate([("109 min", "one patient in ten waits longer than this, from arrival to treatment"),
                              ("22%", "are treated more than an hour after their appointment time"),
                              ("69%", "of India's radiotherapy facilities have only one machine, like this one")]):
    if i:
        rule(s, x2, TOP + i * 1.42 - 0.1, R - x2)
    number(s, x2, TOP + i * 1.42, R - x2, v, lab, size=38)
text(s, x2, TOP + 4.3, R - x2, 1.2, [
    "Times are given by hand, without knowing how long a session takes. A breakdown is handled by phone, "
    "and patients already on the bus are not told."], size=13.5)
notes(s, "The waits come from the way times are given, not from the machine being too slow.")

# ---- 4. users
s = S[3]
frame(s, "Target Users and Use Case",
      "Five people shape a patient's day. Each gets one screen inside CARE, which the hospital already uses.")
rows = [
    ("Radiation oncologist", "A time that fits the treatment plan",
     "Enters the course from the patient's visit; approves a first day and one daily time"),
    ("Technologist", "To run the machine's day, and a fast answer when it breaks",
     "The day board: Call next, Priority for an emergency, a re-plan in seconds after a breakdown"),
    ("Reception", "Fast, certain check-in", "Scans the code on the patient's phone"),
    ("Patient and family", "To know when to come, in their language",
     "One private link: times, voice notes, one-tap replies, morning, afternoon or evening"),
    ("Head of department", "Evidence that long waits are falling", "Insights from the times the board records"),
]
cx = [L, L + 2.75, L + 6.55]
for x, head in zip(cx, ("Who", "What they need", "What RAD-SMART gives them")):
    text(s, x, TOP + 0.02, 3.6, 0.3, [("cap", head, 12.5)])
y = TOP + 0.42
for who, need, gets in rows:
    rule(s, L, y - 0.08, W)
    text(s, cx[0], y + 0.04, 2.6, 0.8, [("h", who, 14.5)])
    text(s, cx[1], y + 0.04, 3.6, 0.8, [need], size=13.5, color=GRAY)
    text(s, cx[2], y + 0.04, W - 6.55, 0.8, [gets], size=13.5)
    y += 0.86
rule(s, L, y - 0.08, W)
text(s, L, y + 0.12, W, 0.5, [("cap", "Setting: a radiotherapy department with one linear accelerator, every weekday "
                                     "from 08:30 to about 01:00, running CARE.", 12.5)])
notes(s, "The technologist is the heaviest user: the day board is open all day at the console.")

# ---- 5. solution (1 of 2)
s = S[4]
frame(s, "Solution Overview, Key Features & Impact",
      "RAD-SMART predicts, plans, re-plans and tells. A person approves every change.")
steps = [("Predict", "how many minutes each session will take, from the technique, site and the patient's needs."),
         ("Plan", "each course a first day and one daily time, with an optimiser that cannot break a department rule."),
         ("Re-plan", "the rest of the day in about 10 to 14 seconds when the machine breaks down."),
         ("Tell", "patients in Kannada, Malayalam, Hindi or Konkani, with a voice note, on a phone page and WhatsApp.")]
y = TOP + 0.05
for i, (h, body) in enumerate(steps):
    text(s, L, y, 0.5, 0.6, [("n", str(i + 1), 26, BLUE)])
    text(s, L + 0.55, y + 0.02, 4.75, 1.0, [("h", h, 16), body], size=13.5, gap=2)
    y += 1.16
sw, sh = shot(s, fig / "app1_today.png", 6.05, TOP + 0.05, w=R - 6.05, crop=(300, 330, 2200, 1240),
              alt="The technologist's day board on the live demonstration")
text(s, 6.05, TOP + 0.15 + sh, R - 6.05, 0.6, [("cap", "The day board on the live demonstration: who is in the room, "
                                                    "whom to call next, and the rule check.", 11.5)])
rect(s, L, 6.25, W, 0.62, TINT, name="Decision line")
text(s, L + 0.25, 6.25, W - 0.5, 0.62, [
    "RAD-SMART decides only **when** a patient is treated, never whether or how. Staff can always override it: "
    "take a patient in out of turn, or put one first."], size=14, anchor="m")
notes(s, "Four steps; the optimiser guarantees the rules and a person approves.")

# ---- 6. solution (2 of 2): the journey, and the impact
s = S[5]
frame(s, "Solution Overview, Key Features & Impact",
      "From the doctor's prescription to the patient's phone, and what it does to the waiting.")
journey = [
    (fig / "app3_proposal.png", (170, 560, 1190, 1000), (0.22, 0.5), "Doctor",
     "Enters the course; approves a first day and a daily time, with reasons"),
    (fig / "app10_patient_phone.png", None, (0.5, 0.2), "Patient", "One private link: the time to come, a voice note, a QR code"),
    (fig / "app13_queue.png", None, (0.5, 0.5), "Technologist", "Call next, out of turn with a reason, Priority for an emergency"),
    (fig / "app5_breakdown.png", (170, 560, 1080, 1185), (0.5, 0.5), "Breakdown",
     "A re-plan under the department's rules; approved by a person"),
]
gx, gw, gh = L, (W - 3 * 0.25) / 4, 2.05
for i, (path, crop, focus, who, what) in enumerate(journey):
    x = gx + i * (gw + 0.25)
    shot(s, path, x, TOP + 0.05, gw, gh, focus=focus, alt=who, crop=crop)
    text(s, x, TOP + gh + 0.15, gw, 0.85, [("h", who, 14), what], size=12.5, gap=1)
    if i < 3:
        arrow(s, x + gw + 0.03, TOP + gh / 2 + 0.05, 0.19)
y = TOP + gh + 1.2
rule(s, L, y - 0.12, W)
impact = [("−35%", "90th-percentile wait, 108.6 to 70.4 min, on the department's own 55 days"),
          ("22% to 5.7%", "of patients treated more than an hour late"),
          ("29% to 50%", "treated within 15 minutes of their time"),
          ("104 to 39 min", "median wait after a 150-minute breakdown, with a new plan in 14 s")]
iw = W / 4
for i, (v, lab) in enumerate(impact):
    if i:
        rule(s, L + i * iw - 0.12, y, 1.35, vertical=True)
    number(s, L + i * iw, y + 0.05, iw - 0.3, v, lab, size=28, label_size=12)
text(s, L, 6.62, W, 0.3, [("cap", "Expected impact: the department's recorded days re-planned in a digital twin calibrated on "
                                 "them, and synthetic breakdown days. A pilot measures it live.", 11)])
notes(s, "The impact is a replay, not yet a trial: the pilot measures it for real.")

# ---- 7. technology
s = S[6]
frame(s, "Technology, Tools and AI Approach",
      "Each part does what it is best at: the optimiser guarantees the rules; language models only translate and explain.")
flow = [("Course in CARE", "the doctor's prescription and checklist"),
        ("Session minutes", "gradient boosting, scikit-learn"),
        ("The plan", "mixed-integer optimiser, SciPy with HiGHS"),
        ("Rule checker", "independent of the optimiser"),
        ("A person approves", "doctor or technologist"),
        ("Sarvam AI", "Translate, Bulbul v3 voice, Sarvam-105B explanations"),
        ("The patient", "phone page, WhatsApp")]
bw, gap = 1.56, 0.25
for i, (h, sub) in enumerate(flow):
    x = L + i * (bw + gap)
    green = h in ("Rule checker", "A person approves")
    rect(s, x, TOP + 0.15, bw, 1.35, "FFFFFF", line=GREEN if green else BLUE, name=f"Step: {h}")
    text(s, x + 0.1, TOP + 0.25, bw - 0.2, 1.2, [("h", h, 13.5), ("cap", sub, 11.5)], gap=2)
    if i < len(flow) - 1:
        arrow(s, x + bw + 0.02, TOP + 0.82, gap - 0.04)
text(s, L, TOP + 1.65, W, 0.35, [("cap", "Green: the safety gate. A plan that breaks a hard rule cannot be produced, and "
                                       "nothing reaches a patient before a person approves it.", 11.5)])
cols = [
    ("Why this mix", ["Only optimisation guarantees the rules; only language models talk to patients in their language. "
                      "We scored five approaches and this hybrid was the only one that does both.",
                      "The language models never schedule. Every translation and explanation is checked for changed times."]),
    ("Data", ["The department's records: 55 days, anonymised totals, to calibrate the digital twin.",
              "Synthetic patients for training and every demonstration.",
              "Real session minutes, recorded by the board's In room and Out taps, for retraining in the pilot."]),
    ("Stack and integrations", ["Django and React plugins in CARE; PostgreSQL.",
                                "One Docker image on Microsoft Azure Container Apps.",
                                "WhatsApp from the department's phone; QR check-in; Telegram in the demonstration only."]),
]
cw = (W - 2 * 0.4) / 3
for i, (h, items) in enumerate(cols):
    x = L + i * (cw + 0.4)
    rule(s, x, TOP + 2.2, cw)
    text(s, x, TOP + 2.35, cw, 3.0, [("h", h, 15)] + [("b", b) for b in items], size=13, gap=5)
notes(s, "Hybrid by design: guarantees from optimisation, language from Sarvam.")

# ---- 8. build sprint
s = S[7]
frame(s, "Build Sprint Journey and Progress",
      "From a Round 1 engine to a working app inside CARE, live on Azure and shaped by the department.")
miles = [("19 Sep", "Round 1: engine, digital twin"), ("5 Oct", "Shortlisted"),
         ("24 Oct", "Department's rules; app inside CARE"), ("25 Oct", "Sarvam AI, patient page, QR check-in"),
         ("26 Oct", "Live on Microsoft Azure"), ("27 Oct", "Preferred times, live queue"),
         ("3 Nov", "Priority override, emergency starts, guided demo")]
ty = TOP + 0.55
rule(s, L + 0.1, ty, W - 0.2, color=PALE, weight=1.5)
mw = W / len(miles)
for i, (d, what) in enumerate(miles):
    cx_ = L + mw * i + mw / 2
    dot = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx_ - 0.08), Inches(ty - 0.08), Inches(0.16), Inches(0.16))
    dot.fill.solid()
    dot.fill.fore_color.rgb = rgb(GREEN if i == len(miles) - 1 else BLUE)
    dot.line.fill.background()
    _plain(dot)
    text(s, cx_ - mw / 2, ty - 0.5, mw, 0.3, [("h", d, 13.5)], align=PP_ALIGN.CENTER)
    text(s, cx_ - mw / 2 + 0.05, ty + 0.18, mw - 0.1, 0.8, [("cap", what, 11.5)], align=PP_ALIGN.CENTER)
cols = [
    (4.6, "Working now", ["Course intake with a standing daily time, approved by a doctor",
                          "Day board: Call next, out of turn, Priority, rule check",
                          "Breakdown re-planning under the department's rules",
                          "Preferred part of the day, with better-time offers",
                          "Messages in four Indian languages, with voice notes",
                          "Patient phone page, QR check-in, Insights"]),
    (4.1, "How it changed", ["Round 1 was an engine and a simulation; now it runs inside CARE",
                             "The department's answers became rules: one standing time, new starts by 17:00, "
                             "the 60-minute breakdown rule",
                             "Testing fixed four translation and wording problems before anyone saw them"]),
    (3.2, "Not built yet", ["Automatic WhatsApp sending (needs Meta verification)",
                            "Spoken replies from patients",
                            "Reading the oncology system (MOSAIQ, ARIA)",
                            "Live planning for two machines"]),
]
x = L
for cwid, h, items in cols:
    rule(s, x, TOP + 1.55, cwid - 0.3)
    text(s, x, TOP + 1.7, cwid - 0.3, 3.7, [("h", h, 15)] + [("b", b) for b in items], size=12.5, gap=4)
    x += cwid
notes(s, "Milestones are outputs delivered, each in the repository and on the live server.")

# ---- 9. evaluation (1 of 2): scheduling
s = S[8]
frame(s, "Evaluation and User Validation",
      "Replayed on the department's own days and on synthetic ones: long waits fall, and no rule is broken.")
cd = CategoryChartData()
cd.categories = ["Department's 55 days", "Its busiest days (70+ patients)", "12 synthetic weeks",
                 "One busy synthetic day (87)", "150-min breakdown, re-planned"]
cd.add_series("Without RAD-SMART", (108.6, 130, 82, 210, 210))
cd.add_series("With RAD-SMART", (70.4, 70, 49, 76, 110))
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(L), Inches(TOP + 0.05), Inches(7.7), Inches(4.85), cd)
gf.name = "Chart: 90th-percentile wait with and without"
ch = gf.chart
ch.has_title = True
ch.chart_title.text_frame.text = "90th-percentile wait, minutes"
tp = ch.chart_title.text_frame.paragraphs[0]
tp.runs[0].font.size, tp.runs[0].font.bold, tp.runs[0].font.name = Pt(13), True, HEAD
tp.runs[0].font.color.rgb = rgb(DARK)
ch.has_legend = True
ch.legend.position, ch.legend.include_in_layout = XL_LEGEND_POSITION.BOTTOM, False
ch.legend.font.size, ch.legend.font.name = Pt(12), BODY
ca = ch.category_axis
ca.reverse_order = True
ca.tick_labels.font.size, ca.tick_labels.font.name = Pt(12), BODY
ca.format.line.color.rgb = rgb(LINE)
va = ch.value_axis
va.visible = False
va.has_major_gridlines = False
plot = ch.plots[0]
plot.gap_width, plot.overlap = 55, -10
for ser, col in zip(plot.series, (PALE, BLUE)):
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = rgb(col)
    ser.data_labels.show_value = True
    ser.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    ser.data_labels.font.size, ser.data_labels.font.name = Pt(11.5), BODY
x2 = 8.55
for i, (v, lab) in enumerate([("−35%", "90th-percentile wait on the department's 55 days, 108.6 to 70.4 min"),
                              ("14 s", "for a new plan after a breakdown; median wait 104 to 39 min"),
                              ("0", "hard rules broken on any evaluation day, by an independent checker")]):
    if i:
        rule(s, x2, TOP + i * 1.45 - 0.12, R - x2)
    number(s, x2, TOP + i * 1.45, R - x2, v, lab, size=34)
text(s, x2, TOP + 4.35, R - x2, 1.0, [("cap", "Method: the same patients and events with and without RAD-SMART, in a "
                                             "digital twin that reproduces today's long wait (106 against 109 min).", 11.5)])
notes(s, "Two datasets kept apart: the department's own days, and synthetic scenarios.")

# ---- 10. evaluation (2 of 2): AI parts and users
s = S[9]
frame(s, "Evaluation and User Validation",
      "The AI parts are measured, and the department's feedback changed the design.")
rows = [("Session-minute prediction", "2,000 held-out synthetic sessions", "2.15 min mean error, against 2.62 for a table of averages"),
        ("Optimiser", "87-patient day, about 4,800 variables", "Proven optimum in 7.1 s on a laptop"),
        ("Sarvam Translate", "112 messages in Kannada, Malayalam, Hindi and Konkani", "112 of 112 kept every time; back-translation chrF 76 to 80"),
        ("Sarvam-105B explanations", "20 synthetic plans", "20 of 20 accepted, 0 invented times"),
        ("Safety guards", "49 automated tests, the engine's run by GitHub on every change", "All pass")]
cx = [L, L + 2.65, L + 5.35]
for x, head in zip(cx, ("Part", "Test", "Result")):
    text(s, x, TOP + 0.02, 3, 0.3, [("cap", head, 12)])
y = TOP + 0.38
for part, test, res in rows:
    rule(s, L, y - 0.07, 7.75)
    text(s, cx[0], y, 2.55, 0.6, [("h", part, 13)])
    text(s, cx[1], y, 2.6, 0.6, [test], size=12, color=GRAY)
    text(s, cx[2], y, 7.75 - 5.35 + L - 0.45 + 0.4, 0.6, [res], size=12.5)
    y += 0.68
rule(s, L, y - 0.07, 7.75)
text(s, L, y + 0.15, 7.75, 1.2, [("h", "Limits, said plainly", 14),
                                ("b", "A replay, not a trial: the pilot measures the gain live."),
                                ("b", "Session lengths are synthetic until the board has recorded real ones."),
                                ("b", "Still to come: native speakers rating every translation, and a technologist trial.")],
     size=12.5, gap=3)
x2 = 8.6
rect(s, x2, TOP, R - x2, BOTTOM - TOP, TINT, name="Feedback panel")
text(s, x2 + 0.28, TOP + 0.22, R - x2 - 0.56, 5.1, [
    ("h", "What the department changed", 15),
    ("b", "**21 Sep and 24 Oct**, written answers from the technologists and doctors: one standing time per course, "
          "new starts by 17:00, the 60-minute breakdown rule, who approves what."),
    ("b", "**27 Oct**, the doctor partner: patients choose morning, afternoon or evening; a late patient's turn "
          "goes to whoever is ready."),
    ("b", "**3 Nov**: staff can put a patient first, and an emergency starts the same day."),
    ("h", "Fixed in testing", 15),
    ("b", "Kannada suffixes on times; Konkani's “next week” (messages now name the date); an explanation "
          "using the proposed time; an unclear button."),
], size=12.5, gap=5)
notes(s, "Every number here is reproducible from the repository's evaluation scripts.")

# ---- 11. safety
s = S[10]
frame(s, "Safety and Responsible AI",
      "RAD-SMART proposes and people decide. The language models are fenced in, and patients' details stay out of them.")
quads = [
    ("People decide", ["A doctor approves each course and its time; a technologist approves every change on the day",
                       "Hard rules are optimiser constraints, re-checked by an independent checker",
                       "Staff can always override: out of turn with a reason, or Priority; it warns, never blocks",
                       "If a rule breaks in practice, the department returns to manual scheduling"]),
    ("The AI, fenced in", ["Language models never schedule; they translate and explain",
                           "A translation that drops or changes a time is discarded: the patient gets English",
                           "An explanation that mentions a time not in the plan is rejected",
                           "Without Sarvam, everything still works in English"]),
    ("Privacy and consent", ["No names, hospital or phone numbers go to Sarvam: only the message text",
                             "The patient page shows a first name only, behind a long random link",
                             "Synthetic data in every demonstration; the department's records only as totals",
                             "The pilot follows the DPDP Act 2023 and Rules 2025, with ethics review"]),
    ("Fairness and access", ["Older patients, public transport, the hospice bus and time windows are explicit rules",
                             "Messages in Kannada, Malayalam, Hindi and Konkani, with voice notes for those who read little",
                             "Patients choose morning, afternoon or evening; staff agree any change with them"]),
]
qw = (W - 0.5) / 2
for i, (h, items) in enumerate(quads):
    x = L + (i % 2) * (qw + 0.5)
    y = TOP + (i // 2) * 2.75
    rule(s, x, y, qw, color=GREEN if i == 0 else LINE, weight=1.5 if i == 0 else 0.75)
    text(s, x, y + 0.14, qw, 2.5, [("h", h, 15)] + [("b", b) for b in items], size=12.5, gap=3)
notes(s, "The safety case rests on three things: hard constraints, human approval, checked AI output.")

# ---- 12. deployment and cost
s = S[11]
frame(s, "Deployment, Cost and Sustainability Plan",
      "Live today on Microsoft Azure as one Docker image; the pilot runs the same image with demonstration mode off.")
text(s, L, TOP, 5.7, 5.4, [
    ("h", "To pilot it", 15),
    ("b", "A CARE instance: the hospital's own, or our image; RAD-SMART installs as a plugin"),
    ("b", "A laptop or tablet at the console and at reception; a USB scanner or camera"),
    ("b", "The department's WhatsApp on a staff phone; internet for Sarvam"),
    ("b", "Approval by the head of department, hospital IT and the ethics committee"),
    ("h", "Integration", 15),
    ("b", "Uses CARE's own patients, users and roles; no change to CARE"),
    ("b", "Next: a read-only feed from the oncology system (MOSAIQ or ARIA, HL7 v2 or FHIR), so courses are not typed twice"),
    ("h", "Scale and sustain", 15),
    ("b", "Versa HD pilot, then the second machine (2027), then other CARE hospitals: 69% of Indian centres have one machine"),
    ("b", "Open source, no licence fee; the department's own staff can run it"),
], size=12.5, gap=4)
x2 = 6.6
costs = [("One-time", None),
         ("Server, or an existing hospital VM", "₹0 to 1,50,000"),
         ("Tablets or existing PCs; QR scanner", "₹5,000 to 75,000"),
         ("Software licence", "₹0"),
         ("Ongoing", None),
         ("Per message: translation and voice note", "about ₹1"),
         ("Per course: about 3 messages and explanations", "₹3 to 5"),
         ("Per month, on the hospital's server", "about ₹500 to 900"),
         ("Per month, on Azure Central India instead", "about ₹4,500 to 7,000")]
y = TOP
for item, cost in costs:
    if cost is None:
        text(s, x2, y + (0.12 if y > TOP else 0), R - x2, 0.35, [("h", item, 14)])
        y += 0.47 if y > TOP else 0.38
        continue
    rule(s, x2, y - 0.04, R - x2)
    text(s, x2, y + 0.04, 4.4, 0.4, [item], size=12.5)
    text(s, R - 1.75, y + 0.04, 1.75, 0.4, [("h", cost, 12.5)], align=PP_ALIGN.RIGHT)
    y += 0.44
rule(s, x2, y - 0.04, R - x2)
text(s, x2, y + 0.08, R - x2, 1.3, [("cap", "Assumptions: Sarvam list prices (Translate ₹20 and Bulbul v3 ₹30 per 10,000 "
                                           "characters); a message of about 190 characters; about 1,000 courses a year. "
                                           "Azure: one always-on container (0.5 vCPU) and a small managed database. "
                                           "WhatsApp Business API costs come later.", 11)])
notes(s, "Running costs are a few thousand rupees a year on the hospital's own server.")

# ---- 13. what next
s = S[12]
frame(s, "What Next? Plans to take initiative forward (if any)",
      "Validate with the department, then a 90-day pilot on the Versa HD.")
plan = [("Nov to Dec 2026", "Technologist trial and native-speaker ratings; approvals from the head of department, "
                            "hospital IT and the ethics committee; patient notice and consent for messages"),
        ("Jan 2027", "Pilot, phase 1: two weeks measuring today's waits with the day board"),
        ("Feb 2027", "Phase 2: three weeks in shadow mode, RAD-SMART proposing while staff schedule by hand"),
        ("Feb to Apr 2027", "Phase 3: eight weeks live. Target: a 90th-percentile wait at least 25% below 109 minutes"),
        ("Later in 2027", "WhatsApp Business API, spoken replies, the second machine, an oncology-system feed, "
                          "and the plugin offered to other CARE hospitals")]
y = TOP + 0.05
for when, what in plan:
    rule(s, L, y - 0.1, 8.1)
    text(s, L, y, 2.1, 0.8, [("h", when, 14)])
    text(s, L + 2.25, y, 5.85, 0.95, [what], size=13)
    y += 0.98
rule(s, L, y - 0.1, 8.1)
x2 = 9.0
rect(s, x2, TOP, R - x2, 3.0, TINT, name="Public answer")
text(s, x2 + 0.3, TOP + 0.25, R - x2 - 0.6, 2.6, [
    ("cap", "Make all the solution information publicly available?", 13),
    ("n", "Yes", 54, GREEN),
    "The code, website, deck, research paper and demo video are already public and open source.",
], size=13, gap=6)
notes(s, "We want the department to run it after the pilot, and other CARE hospitals to install it.")

# ---- 14. thank you
s = S[13]
for sh in s.shapes:
    if not sh.has_text_frame:
        continue
    replace(sh, "[Team name]", TEAM)
    replace(sh, "[Team code]", CODE_)
    if "[Contact email]" in sh.text_frame.text:
        p0 = sh.text_frame.paragraphs[0]
        look = p0.runs[0].font
        size = look.size.pt if look.size else 11
        for extra in sh.text_frame.paragraphs[1:]:
            extra._p.getparent().remove(extra._p)
        for r in p0.runs:
            r._r.getparent().remove(r._r)
        lines = [("Contact", CONTACT, "mailto:" + CONTACT), ("Try the live demo", LIVE, LIVE),
                 ("Demo video", VIDEO, VIDEO), ("Code", REPO, REPO)]
        for i, (lab, shown, url) in enumerate(lines):
            p = p0 if i == 0 else sh.text_frame.add_paragraph()
            p.alignment = PP_ALIGN.CENTER
            p.space_after = Pt(3)
            _run(p, lab + ": ", max(size, 12), GRAY, bold=True, font=HEAD)
            _run(p, shown, max(size, 12), BLUE, font=HEAD, link=url)
        sh.top = Emu(sh.top) - Inches(0.15)
        sh.height = Inches(1.4)
notes(s, "Thank you. The live demo needs no password: every step is one click.")

prs.save(str(DECK))
print("wrote", DECK.relative_to(root), len(prs.slides), "slides")


# ================================================================ the two-page brief
def rewrite(shape, blocks, size=10.5):
    """Fill one of the brief's boxes: (heading, items) blocks, the template's heading look kept."""
    tf = shape.text_frame
    head = None
    for p in tf.paragraphs:
        for r in p.runs:
            if r.font.underline and r.text.strip():
                head = copy.deepcopy(r._r)
                break
        if head is not None:
            break
    for p in list(tf.paragraphs)[1:]:
        p._p.getparent().remove(p._p)
    for r in list(tf.paragraphs[0].runs):
        r._r.getparent().remove(r._r)
    tf.word_wrap = True
    first = True
    for h, items in blocks:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_before, p.space_after, p.line_spacing = Pt(0 if p is tf.paragraphs[0] else 7), Pt(3), 1.0
        if head is not None:
            p._p.append(copy.deepcopy(head))
            p.runs[-1].text = h
        else:                       # a placeholder whose heading look is inherited: set it here
            _run(p, h, 12.5, "275B9D", bold=True, font=HEAD).font.underline = True
        p.runs[-1].font.size = Pt(12.5)
        for it in items:
            kind, body = ("p", it) if isinstance(it, str) else it[:2]
            q = tf.add_paragraph()
            q.space_after, q.line_spacing = Pt(2.5), 1.0
            for j, chunk in enumerate(body.split("**")):
                if chunk:
                    _run(q, chunk, size, DARK, bold=j % 2 == 1).font.underline = False   # the placeholder underlines
            for k, (shown, url) in enumerate(it[2] if kind == "l" else []):   # l: bullet, then (shown, url) links
                if k:
                    _run(q, " and ", size, DARK).font.underline = False
                _run(q, shown, size, BLUE, link=url).font.underline = True
            if kind in ("b", "l"):
                _bullet(q, BLUE, 0.16)


def heading(shape):
    for p in shape.text_frame.paragraphs:
        if "[Team Name]" in "".join(r.text for r in p.runs):
            runs = p.runs
            runs[0].text = "RAD-SMART "
            for r in runs[1:]:
                r.text = ""
            runs[-1].text = "| Radiotherapy scheduling"
            shape.width = Inches(8.1)


brief = Presentation(str(BRIEF_TEMPLATE))
p1, p2 = brief.slides[0], brief.slides[1]
for slide in (p1, p2):
    for sh in list(slide.shapes):
        if sh.has_text_frame and sh.text_frame.text.strip() == "Armman":   # a stray label in the template
            sh._element.getparent().remove(sh._element)
        elif sh.has_text_frame and "[Team Name]" in sh.text_frame.text:
            heading(sh)

boxes = {sh.shape_id: sh for sh in p1.shapes}
left, right = boxes[7], boxes[10]
rewrite(left, [
    ("About the Team / Organisation", [
        "**A. The team.** Radiotherapy department, Kasturba Medical College, Manipal (MAHE), with two engineers: "
        "Abhinand T M (technical lead) and P S Raghotham Rao (lead engineer: the scheduling engine, digital twin, "
        "CARE plugin and Sarvam AI layer). Built on CARE, the open-source hospital information system of the "
        "Open Healthcare Network. Team code YU8PAK.",
        "**B. The doctors.** Dr Akshay Dinesan (team leader, doctor partner) wrote the problem statement from daily "
        "work, brought the department's records and owns the clinical rules and the pilot. Dr Shirley Lewis Salins "
        "and Dr Umesh Velu reviewed the rules and the design. The department's technologists and doctors answered "
        "our questions in writing on 21 September and 24 October; those answers are now rules in the code."]),
    ("Problem Statement (use case specific)", [
        "One linear accelerator (Elekta Versa HD) treats **70 to 90 patients a day**, 08:30 until about 01:00. "
        "A course means coming every weekday for one to seven weeks. Times are given by hand, without knowing how "
        "long a session takes, so the delay builds through the day.",
        ("b", "In the department's records (55 days, 3,137 visits, anonymised totals), **one patient in ten waits "
              "more than 109 minutes**, and **22% are treated over an hour late**."),
        ("b", "A breakdown is handled by phone; patients already travelling are not told."),
        ("b", "69% of India's radiotherapy facilities have one machine: this is the common case."),
        "**Users:** radiation oncologists, technologists, reception, patients and families, the head of department."]),
], size=12)
right.height = Inches(6.2)
rewrite(right, [
    ("AI Solution Description", [
        "RAD-SMART plans the machine's day so that waits are short and every department rule is kept. It runs "
        "**inside CARE** as a plugin. The doctor enters a course on the patient's visit and approves a first day "
        "and **one daily time** for the whole course. The technologist runs the day on a live board, and when the "
        "machine breaks down RAD-SMART **re-plans the rest of the day in seconds** under the department's own "
        "rules. Patients get each time on a private phone page and WhatsApp, **in their own language with a voice "
        "note**. A person approves every change; RAD-SMART decides only when, never whether or how."]),
    ("Technology and Tools Used", [
        ("b", "**Gradient boosting** (scikit-learn) predicts each session's minutes."),
        ("b", "**Mixed-integer optimisation** (SciPy with HiGHS) plans with the rules as hard constraints; an "
              "independent checker re-verifies every plan; a calibrated **digital twin** tests plans first."),
        ("b", "**Sarvam AI**: Translate, Bulbul v3 voice notes, Sarvam-105B plain-language explanations, each "
              "output checked for changed times."),
        ("b", "Django and React plugins in CARE, PostgreSQL, one Docker image on Microsoft Azure."),
    ]),
    ("Key Features of the solution", [
        ("b", "**Standing daily time** per course, inside the patient's preferred morning, afternoon or evening; "
              "better times offered as slots free up, agreed by staff with the patient."),
        ("b", "**Day board** with Call next, out of turn with a reason, and **Priority** and same-day "
              "**emergency starts** that staff decide."),
        ("b", "**Breakdown re-planning** in about 10 to 14 seconds, approved by a person."),
        ("b", "**Messages** in Kannada, Malayalam, Hindi and Konkani with voice notes; a phone page with one-tap "
              "replies and QR check-in."),
        ("b", "**Insights**: measured waits against the 109-minute baseline."),
    ]),
], size=11.5)

boxes = {sh.shape_id: sh for sh in p2.shapes}
left, right = boxes[5], boxes[3]
left.height = Inches(5.55)
rewrite(left, [
    ("Build Sprint Progress", [
        "From a Round 1 engine and simulation (19 Sep) to a working application inside CARE, live on Azure:",
        ("b", "**24 Oct**: the department's rules (standing times, new starts by 17:00, the 60-minute breakdown "
              "rule, roles) built into the engine and a CARE app."),
        ("b", "**25 Oct**: Sarvam messages and voice notes, the patient phone page, QR check-in, explanations."),
        ("b", "**26 Oct**: deployed on Microsoft Azure in one Docker image, open to try."),
        ("b", "**27 Oct**: from the doctor partner, preferred part of the day and a live queue for early and "
              "late patients."),
        ("b", "**3 Nov**: Priority override, same-day emergency starts, a guided demonstration."),
        "Not yet: automatic WhatsApp sending, spoken replies, the oncology-system feed, two machines."]),
    ("User Validation and AI Evaluation", [
        ("b", "On the department's 55 recorded days, re-planned in a calibrated twin: **90th-percentile wait "
              "108.6 to 70.4 min (−35%)**; over-an-hour lateness **22.2% to 5.7%**."),
        ("b", "After a 150-minute breakdown: median wait **104 to 39 min**, new plan in 14 s. No hard rule broken."),
        ("b", "Prediction error 2.15 min; optimum in 7.1 s; **112 of 112** translations kept every time; 20 of 20 "
              "explanations with no invented time; 49 automated tests pass."),
        ("b", "The department's feedback changed the design (standing times, breakdown rules, preferred times, "
              "out-of-turn). Limits: a replay, not a trial; native-speaker ratings and a technologist trial next."),
    ]),
], size=11)
rewrite(right, [
    ("Safety and Responsible AI", [
        ("b", "**People decide**: a doctor approves each course; a technologist approves every change on the day; "
              "staff can always override."),
        ("b", "**Rules are guaranteed**: hard constraints in the optimiser, re-checked independently."),
        ("b", "**AI fenced in**: language models never schedule; a translation or explanation that changes a time "
              "is discarded; without Sarvam it works in English."),
        ("b", "**Privacy**: no names or numbers sent to Sarvam; first name only on the patient page; synthetic "
              "demonstration data; DPDP Act consent and ethics review for the pilot."),
    ]),
    ("Deployment and Sustainability Plan", [
        ("b", "Live on Azure as one Docker image; the pilot runs the same image on the hospital's server or in an "
              "Indian Azure region. Installs as a CARE plugin, no change to CARE."),
        ("b", "Costs: hardware ₹0 to 2.25 lakh (existing PCs cost nothing); about ₹1 a message, ₹3 to 5 "
              "a course; open source, no licence fee."),
        ("b", "90-day pilot on the Versa HD (baseline, shadow, live; target −25%), then the second machine and "
              "other CARE hospitals."),
    ]),
    ("Supporting Links", [   # clickable; the server's own address opens the guided tour
        ("l", "**MVP, no password**: ", [(MVP.split("//")[1], MVP)]),
        ("l", "**Video demo walkthrough**: ", [(VIDEO.split("//")[1], VIDEO)]),
        ("l", "**Website and documents**: ", [(SITE.split("//")[1].rstrip("/"), SITE)]),
        ("l", "**Code**: ", [(REPO.split("//")[1], REPO)]),
    ]),
], size=11.5)
brief.save(str(BRIEF))
print("wrote", BRIEF.relative_to(root))
