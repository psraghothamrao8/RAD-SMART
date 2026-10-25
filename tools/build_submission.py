"""Fill the official Health-a-thon 2026 final-submission template with RAD-SMART's content.

Reads docs/Health-a-thon 2026 Submission Template.pptx (the organisers' template) and writes
docs/RAD-SMART_Phase2_Submission.pptx, the file to upload. The template's own logo, titles,
footers and fonts are kept; each slide's instructions are replaced by the content of
docs/Phase2_Submission.md.
The two sections the template allows two slides for (solution, evaluation) get a second slide.

Run: python tools/build_submission.py   (needs python-pptx and Pillow)
"""
import copy
import io
from pathlib import Path

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

root = Path(__file__).resolve().parent.parent
docs = root / "docs"
fig = docs / "figures"
template = docs / "Health-a-thon 2026 Submission Template.pptx"
out = docs / "RAD-SMART_Phase2_Submission.pptx"

TEAM_NAME = "RAD-SMART"
TEAM_CODE = "YU8PAK"
CONTACT = "Dr Akshay Dinesan (team leader), Manipal, akshay.dinesan@manipal.edu"
SITE = "https://psraghothamrao8.github.io/RAD-SMART/"
VIDEO = SITE + "#demo"
CODE = "https://github.com/psraghothamrao8/RAD-SMART"

# the template's colours, plus light tints of them for cards
BLUE, GREEN, DARK, GRAY = "1F3DA9", "0D8743", "232F3E", "5D6A79"
BLUE_T, GREEN_T, GRAY_T, LINE = "EDF0FA", "E8F4EC", "F2F4F6", "D5DBE3"
HEAD, BODY = "Arial", "Calibri"

# content area under the title and the slide's one-line message
L, R, TOP = 0.42, 12.8, 1.5
W = R - L


def rgb(h):
    return RGBColor.from_string(h)


# ---------------------------------------------------------------- text

def _run(p, text, size, color, bold=False, italic=False, font=BODY, spc=None, link=None):
    r = p.add_run()
    r.text = text
    f = r.font
    f.size, f.bold, f.italic, f.name = Pt(size), bold, italic, font
    f.color.rgb = rgb(color)
    if spc:
        r.font._rPr.set("spc", str(spc))
    if link:
        r.hyperlink.address = link
    return r


def _plain(shape):
    """No theme style on a shape (it adds a shadow): fill, line and text colours are all set here."""
    st = shape._element.find(qn("p:style"))
    if st is not None:
        shape._element.remove(st)


def _bullet(p, color, indent=0.17):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(Emu(Inches(indent))))
    pPr.set("indent", str(-Emu(Inches(indent))))
    buClr = etree.SubElement(pPr, qn("a:buClr"))
    etree.SubElement(buClr, qn("a:srgbClr")).set("val", color)
    etree.SubElement(pPr, qn("a:buFont")).set("typeface", "Arial")
    etree.SubElement(pPr, qn("a:buChar")).set("char", "•")


def fill_text(tf, items, size=12, color=DARK, align=PP_ALIGN.LEFT, gap=3, accent=BLUE):
    """items: strings, or (kind, text) with kind in
    p (paragraph), b (bullet), label (small caps heading), h (bold heading), big (stat number),
    c (paragraph in the accent colour), cap (caption), link (text, url). **bold** marks bold runs inside p, b and cap."""
    first = True
    for it in items:
        kind, text = ("p", it) if isinstance(it, str) else it[:2]
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = align
        p.line_spacing = 1.0
        p.space_after = Pt(gap)
        if kind == "label":
            _run(p, text.upper(), 10.5, accent, bold=True, font=HEAD, spc=60)
            p.space_after = Pt(4)
        elif kind == "h":
            _run(p, text, size + 2, DARK, bold=True, font=HEAD)
            p.space_after = Pt(2)
        elif kind == "big":
            _run(p, text, it[2] if len(it) > 2 else 26, accent, bold=True, font=HEAD)
            p.space_after = Pt(2)
        elif kind == "link":
            _run(p, text, size, BLUE, link=it[2])
        else:
            sz = {"cap": 10.5}.get(kind, size)
            col = GRAY if kind == "cap" else accent if kind == "c" else color
            if kind == "b":
                p.space_after = Pt(gap + 1)
            for i, chunk in enumerate(text.split("**")):
                if chunk:
                    _run(p, chunk, sz, col, bold=i % 2 == 1)
            if kind == "b":
                _bullet(p, accent)


def box(slide, x, y, w, h, items=(), fill=None, line=None, inset=0.12, anchor="t", name=None,
        radius=0.08, shape=MSO_SHAPE.ROUNDED_RECTANGLE, **kw):
    """A text box, or a card (rounded rectangle) when fill or line is given."""
    if fill or line:
        s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
        if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
            s.adjustments[0] = min(0.5, radius / min(w, h))
        if fill:
            s.fill.solid()
            s.fill.fore_color.rgb = rgb(fill)
        else:
            s.fill.background()
        if line:
            s.line.color.rgb = rgb(line)
            s.line.width = Pt(0.75)
        else:
            s.line.fill.background()
        _plain(s)
    else:
        s = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        inset = 0.0
    if name:
        s.name = name
    tf = s.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = Inches(inset)
    tf.margin_top = tf.margin_bottom = Inches(min(inset, 0.1))
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    if items:
        fill_text(tf, items, **kw)
    return s


def picture(slide, path, x, y, w=None, h=None, crop=None, alt="", border=True):
    im = Image.open(path)
    if crop:
        im = im.crop(crop)
    if w and not h:
        h = w * im.height / im.width
    if h and not w:
        w = h * im.width / im.height
    buf = io.BytesIO()
    im.save(buf, "PNG")
    buf.seek(0)
    pic = slide.shapes.add_picture(buf, Inches(x), Inches(y), Inches(w), Inches(h))
    pic._element.nvPicPr.cNvPr.set("descr", alt)
    pic.name = "Screenshot: " + alt[:40] if alt else pic.name
    if border:
        pic.line.color.rgb = rgb(LINE)
        pic.line.width = Pt(0.75)
    return pic, w, h


def circle(slide, x, y, d, text, fill, size=12):
    s = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    s.line.fill.background()
    _plain(s)
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    _run(p, text, size, "FFFFFF", bold=True, font=HEAD)
    return s


def arrow(slide, x, y, w, h, color=GRAY):
    s = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(color)
    s.line.fill.background()
    _plain(s)
    s.name = "Arrow"
    return s


def stat(slide, x, y, w, h, number, label, fill=BLUE_T, accent=BLUE, size=26):
    return box(slide, x, y, w, h, [("big", number, size), label], fill=fill, inset=0.14,
               accent=accent, name=f"Stat: {number}", size=12)


# ---------------------------------------------------------------- slide frame

def set_text(shape, text):
    """Replace a template text box's text, keeping its first run's formatting."""
    p = shape.text_frame.paragraphs[0]
    runs = p.runs
    runs[0].text = text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)


def frame(slide, title, message):
    """Keep the logo, title and footer; drop the template's instructions; add the message line."""
    for s in list(slide.shapes):
        if s.shape_type != MSO_SHAPE_TYPE.PICTURE and 1.2 < Emu(s.top).inches < 7.0:
            s._element.getparent().remove(s._element)
    title_box = min((s for s in slide.shapes if s.has_text_frame), key=lambda s: s.top)
    set_text(title_box, title)
    box(slide, L, 0.92, W, 0.4, [message], size=15, color=GRAY, name="Message")


def clone(prs, index):
    """Copy slide `index` (logo, title, footer) to a new slide right after it."""
    src = prs.slides[index]
    new = prs.slides.add_slide(src.slide_layout)
    for s in list(new.shapes):
        s._element.getparent().remove(s._element)
    bg = src._element.cSld.bg
    if bg is not None:
        new._element.cSld.insert(0, copy.deepcopy(bg))
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


prs = Presentation(str(template))
clone(prs, 8)  # evaluation gets two slides
clone(prs, 4)  # solution gets two slides
S = list(prs.slides)
(cover, team, problem, users, sol1, sol2, mvp, tech, sprint, ev1, ev2, safety, deploy, nxt,
 thanks) = S

# ---------------------------------------------------------------- 1 cover

shapes = {s.name.split(";")[1]: s for s in cover.shapes}
set_text(shapes["89"], "RAD-SMART")
set_text(shapes["90"], "AI-assisted radiotherapy scheduling inside CARE: one standing time per course, "
                       "re-planning in seconds after a breakdown, and messages to patients in their own language")
set_text(shapes["91"], f"TEAM NAME  {TEAM_NAME}")
set_text(shapes["92"], f"TEAM CODE  {TEAM_CODE}")
box(cover, 1.8, 4.95, 9.7, 0.35, ["Cancer track  ·  Use case 04: Clinic Operations & Patient Flow"],
    size=13, color=GRAY, align=PP_ALIGN.CENTER, name="Track")

# ---------------------------------------------------------------- 2 team

frame(team, "Team Overview & Background",
      "Clinicians from the department RAD-SMART is built for, and the engineers who built it")
box(team, L, TOP, 7.9, 0.3, [("label", "The team")])
members = [
    ("AD", "Dr Akshay Dinesan", "Team leader · doctor partner",
     "Clinical owner and pilot sponsor. Wrote the problem statement from daily work in the department", GREEN),
    ("SL", "Dr Shirley Lewis Salins", "Doctor partner",
     "Clinical review of the department's rules and of the design; joins the pilot", GREEN),
    ("UV", "Dr Umesh Velu", "Doctor partner",
     "Clinical review of the department's rules and of the design; joins the pilot", GREEN),
    ("AT", "Abhinand T M", "Technical lead",
     "Coordinates the team, the doctors and the submissions; reviews the build", BLUE),
    ("PR", "P S Raghotham Rao", "Lead engineer",
     "Built the scheduling engine, the digital twin, the CARE plugin and the Sarvam AI layer; ran the evaluation", BLUE),
]
for i, (ini, name, role, what, col) in enumerate(members):
    row, k = (0, i) if i < 3 else (1, i - 3)
    n = 3 if row == 0 else 2
    w = (7.9 - (n - 1) * 0.2) / n
    x, y = L + k * (w + 0.2), TOP + 0.35 + row * 2.6
    box(team, x, y, w, 2.4, fill=GRAY_T, name=f"Member: {name}")
    circle(team, x + 0.15, y + 0.15, 0.5, ini, col, 12)
    box(team, x + 0.15, y + 0.75, w - 0.3, 1.6, [("h", name), ("c", role), what], size=12, accent=col, gap=4)
box(team, 8.55, TOP, R - 8.55, 3.2, [
    ("label", "The department"),
    ("h", "Radiotherapy department, Manipal"),
    ("b", "One linear accelerator, an Elekta Versa HD; a second machine arrives in 2027"),
    ("b", "70–90 patients a day, from 08:30 until about 01:00"),
    ("b", "Its technologists and doctors answered our questions in writing on 21 Sep and 24 Oct; "
          "their rules are in the code"),
    ("b", "Shared 55 days of records (3,137 visits) as anonymised totals"),
], fill=BLUE_T, inset=0.18, size=12, name="The department")
box(team, 8.55, TOP + 3.4, R - 8.55, 6.85 - TOP - 3.4, [
    ("label", "The platform"),
    "**CARE**, the open-source hospital information system of the Open Healthcare Network.",
    "RAD-SMART is a CARE plugin: it uses CARE's own patients, users and roles, with no change to CARE's code.",
], fill=GREEN_T, inset=0.18, size=12, accent=GREEN, name="The platform")

# ---------------------------------------------------------------- 3 problem

frame(problem, "Problem Statement and Supporting Evidence",
      "One machine, 70–90 patients a day, times given by hand: waits build up every day of a 1–7 week course")
stats = [("109 min", "1 patient in 10 waits longer than this, from arrival to treatment"),
         ("22%", "are treated more than an hour after their appointment time"),
         ("29%", "are treated within 15 minutes of their appointment time"),
         ("69%", "of India's radiotherapy facilities have only one machine, like this one")]
sw = (W - 3 * 0.2) / 4
for i, (num, lab) in enumerate(stats):
    stat(problem, L + i * (sw + 0.2), TOP, sw, 1.3, num, lab)
_, pw, ph = picture(problem, fig / "fig0_department_records.png", L, 3.0, w=7.1,
                    alt="The department's records: waits build up over the day, and appointment times stop being kept")
box(problem, L, 3.0 + ph + 0.05, 7.1, 0.5, [("cap", "The department's records: 55 working days, Oct–Dec 2024, 3,137 visits, "
                                            "anonymised totals. Blue: RAD-SMART in the calibrated digital twin.")])
box(problem, 7.75, 3.0, R - 7.75, 3.45, [
    ("label", "Why it matters"),
    ("p", "Patients come every weekday for 1–7 weeks, usually with a family member, many by public transport "
          "or the hospice bus."),
    ("label", "What goes wrong today"),
    ("b", "Times are given by hand, without knowing how long each session takes, so too many patients are "
          "asked to come at once"),
    ("b", "A breakdown is handled by phone calls and guesswork; patients already on a bus are not told"),
    ("label", "What must improve"),
    ("p", "Times that are kept, a fast and fair answer to breakdowns, and patients told early, in their own language."),
], fill=GRAY_T, inset=0.18, size=12, gap=5, name="Why it matters")

# ---------------------------------------------------------------- 4 users

frame(users, "Target Users and Use Case",
      "Setting: a radiotherapy department with one linear accelerator, running the CARE hospital system")
people = [
    ("Radiation oncologist", "A time that fits the treatment plan, without phone calls",
     "Enters the course from the patient's visit; approves the first day and one standing daily time"),
    ("Radiation therapy technologist", "A day that runs to time, and a quick answer when the machine breaks",
     "Runs the day board (arrived, in room, out); declares a breakdown and approves the re-plan; sends messages"),
    ("Reception", "Fast, certain check-in",
     "Scans the QR code on the patient's phone, or types its six letters"),
    ("Patient and family", "To know when to come, in their own language, before leaving home",
     "Open one private link: today's time, any change, a voice note, and four reply buttons"),
    ("Head of department", "Evidence that long waits are falling",
     "Sees waiting times and punctuality on Insights, from the times the board records"),
]
cw = (W - 4 * 0.16) / 5
for i, (who, need, does) in enumerate(people):
    x = L + i * (cw + 0.16)
    box(users, x, TOP, cw, 3.3, [("h", who), ("label", "Needs"), ("p", need), ("label", "In RAD-SMART"), ("p", does)],
        fill=BLUE_T if i != 3 else GREEN_T, accent=BLUE if i != 3 else GREEN, inset=0.15, size=12, gap=8,
        name=f"User: {who}")
box(users, L, 5.0, W, 0.3, [("label", "How it fits the workflow")])
fits = [("Inside CARE", "A RADSMART button on the patient's visit page; CARE's own logins, roles and patient records"),
        ("On the day", "One board at the machine console and a check-in page at reception; one tap per patient"),
        ("For patients", "One private link with no app or login; messages open in WhatsApp, which patients already use")]
fw = (W - 2 * 0.2) / 3
for i, (h, t) in enumerate(fits):
    box(users, L + i * (fw + 0.2), 5.35, fw, 1.5, [("h", h), t], fill=GRAY_T, inset=0.15, size=12,
        name=f"Fit: {h}")

# ---------------------------------------------------------------- 5 solution (1 of 2)

frame(sol1, "Solution Overview, Key Features & Impact",
      "An assistive scheduler inside CARE: it predicts, plans, re-plans and tells; a person approves every change")
steps = [("1", "Predict", "How many minutes each session takes on the machine, from technique, site and patient needs"),
         ("2", "Plan", "Each course gets a first day and one standing daily time, from an optimiser that cannot "
                       "break the department's hard rules"),
         ("3", "Re-plan", "After a breakdown, a new plan in 10 to 14 seconds under the department's own rules"),
         ("4", "Tell", "Messages and voice notes in Kannada, Malayalam, Hindi or Konkani by Sarvam AI, "
                       "on WhatsApp and a phone page")]
gw = 0.4
stw = (W - 3 * gw) / 4
for i, (n, verb, text) in enumerate(steps):
    x = L + i * (stw + gw)
    box(sol1, x, TOP, stw, 1.8, fill=BLUE_T, name=f"Step {n}: {verb}")
    circle(sol1, x + 0.15, TOP + 0.15, 0.45, n, BLUE, 13)
    box(sol1, x + 0.72, TOP + 0.17, stw - 0.85, 0.45, [("h", verb)], size=15)
    box(sol1, x + 0.15, TOP + 0.7, stw - 0.3, 1.05, [text], size=12)
    if i < 3:
        arrow(sol1, x + stw + 0.08, TOP + 0.75, gw - 0.16, 0.3)
box(sol1, L, 3.55, W, 0.3, [("label", "Key features, built and working")])
feats = [("Standing slots", "One time per course, free on every treatment date"),
         ("Day board", "Arrival, in room, out, and a live check of 9 hard rules"),
         ("Breakdown re-plan", "A proposal for each remaining patient, approved by a person"),
         ("Requests", "Patients ask for another daily time; staff decide"),
         ("Messages", "Drafted after every approval, translated, with a voice note"),
         ("Patient phone page", "Today's time, changes and replies; no app, no login"),
         ("QR check-in", "Reception scans the code on the patient's phone"),
         ("Explain and Insights", "Why this time, in plain words; waits from the board")]
fw = (W - 3 * 0.2) / 4
for i, (h, t) in enumerate(feats):
    r, c = divmod(i, 4)
    box(sol1, L + c * (fw + 0.2), 3.9 + r * 1.1, fw, 0.95, [("h", h), t], fill=GRAY_T, inset=0.14, size=12,
        name=f"Feature: {h}")
box(sol1, L, 6.2, W, 0.6, ["**A person approves every change.** RAD-SMART decides only **when** a patient is treated, "
                            "never whether or how."], fill=GREEN_T, anchor="m", inset=0.2, size=14,
    name="Human approval")

# ---------------------------------------------------------------- 6 solution (2 of 2)

frame(sol2, "Solution Overview, Key Features & Impact",
      "The journey, from the doctor's course entry to the patient's phone, and the impact we expect")
journey = [("Doctor", "Enter the course", "Prescription, technique, needs and a priority checklist, from the visit in CARE",
            "A first day and a standing time, with reasons and an alternative"),
           ("Doctor", "Approve", "The proposal", "The course is booked; the patient's link and QR code are ready"),
           ("Technologist", "Run the day", "Arrived, in room and out taps on the day board",
            "A live rule check; real session minutes recorded"),
           ("Technologist", "Breakdown", "The fault and its expected length",
            "A re-plan in seconds; a person approves it"),
           ("Patient", "Is told", "The approved time or change",
            "A WhatsApp message and voice note in their language; check-in by QR")]
jw = (W - 4 * 0.3) / 5
for i, (who, what, inp, outp) in enumerate(journey):
    x = L + i * (jw + 0.3)
    green = who == "Patient"
    box(sol2, x, TOP, jw, 2.6, [("label", who), ("h", what), ("p", "**In:** " + inp), ("p", "**Out:** " + outp)],
        fill=GREEN_T if green else BLUE_T, accent=GREEN if green else BLUE, inset=0.14, size=12, gap=6,
        name=f"Journey {i + 1}: {what}")
    if i < 4:
        arrow(sol2, x + jw + 0.05, TOP + 1.15, 0.2, 0.25)
box(sol2, L, 4.35, W, 0.3, [("label", "Expected impact")])
impact = [("−35%", "90th-percentile wait on the department's 55 days: 108.6 → 70.4 min"),
          ("22% → 5.7%", "of patients treated more than an hour late"),
          ("29% → 50%", "of patients treated within 15 minutes of their time"),
          ("104 → 39 min", "median wait after a 150-min breakdown, re-planned live; new plan in 14 s")]
for i, (num, lab) in enumerate(impact):
    stat(sol2, L + i * (sw + 0.2), 4.7, sw, 1.35, num, lab, size=24)
box(sol2, L, 6.2, W, 0.6, [("cap", "Replayed in a digital twin calibrated on the department's records (it reproduces "
                                   "today's long wait: 106 against 109 min), and on synthetic breakdown days. Not yet a "
                                   "live trial: the 90-day pilot targets a 90th-percentile wait at least 25% below 109 min.")])

# ---------------------------------------------------------------- 7 MVP

frame(mvp, "Solution Working MVP / Demo",
      "A working application inside CARE today, shown here with synthetic patients")
_, _, h1 = picture(mvp, fig / "app1_today.png", L, TOP, w=6.0, crop=(140, 60, 1720, 900),
                   alt="Today page: the machine card, the live check of 9 hard rules and the day's timeline")
box(mvp, L, TOP + h1 + 0.04, 6.0, 0.3, [("cap", "**Today:** the machine card, the live check of 9 hard rules, the day's timeline")])
y2 = TOP + h1 + 0.42
_, _, h2 = picture(mvp, fig / "app3_proposal.png", L, y2, w=6.0, crop=(150, 500, 1700, 870),
                   alt="Course page: RAD-SMART's proposal of a first day and a standing slot, with reasons")
box(mvp, L, y2 + h2 + 0.04, 6.0, 0.3, [("cap", "**Course:** a first day and a standing time, with reasons; a doctor approves")])
mx, mw = 6.62, 3.55
_, _, h3 = picture(mvp, fig / "app5_breakdown.png", mx, TOP, w=mw, crop=(150, 560, 1180, 1120),
                   alt="Breakdown page: what happens to each remaining patient, waiting for approval")
box(mvp, mx, TOP + h3 + 0.04, mw, 0.3, [("cap", "**Breakdown:** a proposal per patient, approved by a person")])
y4 = TOP + h3 + 0.42
_, _, h4 = picture(mvp, fig / "app12_messages_crop.png", mx, y4, w=mw,
                   alt="Messages page: each message in Kannada and English, with Open WhatsApp and Mark sent")
box(mvp, mx, y4 + h4 + 0.04, mw, 0.3, [("cap", "**Messages:** Kannada and English, voice note, WhatsApp")])
yv = y4 + h4 + 0.45
box(mvp, mx, yv, mw, 6.85 - yv, [
    ("label", "Demo video · 3½ min, narrated"),
    ("p", "The real app, one day from course entry to a breakdown and the patient's phone"),
    ("link", "Watch it on the project website", VIDEO),
    ("link", "Code on GitHub", CODE),
], fill=BLUE_T, inset=0.14, size=12, gap=3, name="Demo video")
_, pw, ph = picture(mvp, fig / "app10_patient_phone.png", 10.42, TOP, h=4.7,
                    alt="The patient's phone page in Kannada: today's time to come, the check-in QR code and the next treatment days")
box(mvp, 10.42, TOP + ph + 0.04, R - 10.42, 0.6, [("cap", "**Patient's phone page**, in Kannada, with the check-in QR code")])

# ---------------------------------------------------------------- 8 technology

frame(tech, "Technology, Tools and AI Approach",
      "Each part does what it is best at: the optimiser guarantees the rules; language models only translate and explain")
flow = [(GRAY_T, DARK, "Input", "Course in CARE", "The doctor's entry on the patient's visit page"),
        (BLUE_T, BLUE, "1 · Predict", "Gradient boosting", "scikit-learn: minutes each session takes"),
        (BLUE_T, BLUE, "2 · Plan, re-plan", "Mixed-integer optimiser", "SciPy with HiGHS: the rules are hard constraints"),
        (GREEN_T, GREEN, "Safety gate", "Check and approve", "An independent rule checker, then a person approves"),
        (BLUE_T, BLUE, "3 · Tell", "Sarvam AI", "Translate, Bulbul v3 voice, Sarvam-105B explanations; every output checked"),
        (GRAY_T, DARK, "Output", "The patient", "WhatsApp message, voice note and phone page")]
fgw = 0.28
fcw = (W - 5 * fgw) / 6
for i, (fill, acc, lab, h, t) in enumerate(flow):
    x = L + i * (fcw + fgw)
    box(tech, x, TOP, fcw, 1.8, [("label", lab), ("h", h), t], fill=fill, accent=acc, inset=0.12, size=12,
        name=f"Flow: {h}")
    if i < 5:
        arrow(tech, x + fcw + 0.04, TOP + 0.77, fgw - 0.08, 0.26)
box(tech, L, 3.5, W, 0.3, [("label", "Testing, data, integrations and stack")])
cards = [
    ("Digital twin", [("b", "A simulation calibrated on the department's 55 days; it reproduces today's long wait "
                            "(106 against 109 min)"),
                      ("b", "Tests every plan and measures with and without RAD-SMART before patients are affected")]),
    ("Data", [("b", "Department records, 55 days, as anonymised totals: calibrate the twin"),
              ("b", "Synthetic patients: train the minute model, run the demo and the evaluation"),
              ("b", "Real session minutes: recorded by the day board from the first pilot day")]),
    ("Integrations", [("b", "CARE's patients, users and roles; installs as a plugin"),
                      ("b", "WhatsApp: a message opens in the department's own WhatsApp; staff press send"),
                      ("b", "QR check-in by USB scanner or camera"),
                      ("b", "Sarvam over HTTPS; everything else runs offline")]),
    ("Stack", [("b", "Python, Django REST framework, PostgreSQL (CARE)"),
               ("b", "React and TypeScript (CARE frontend plugin)"),
               ("b", "scikit-learn, SciPy with HiGHS, NumPy"),
               ("b", "Docker Compose · about 10,600 lines of code")]),
]
for i, (h, items) in enumerate(cards):
    box(tech, L + i * (sw + 0.2), 3.85, sw, 3.0, [("h", h)] + items, fill=GRAY_T, inset=0.14, size=12, gap=3,
        name=f"Card: {h}")

# ---------------------------------------------------------------- 9 build sprint

frame(sprint, "Build Sprint Journey and Progress",
      "From a Round 1 engine to a working CARE application with a patient side (sprint: 5 Oct – 8 Nov)")
miles = [("19 Sep", "Round 1 entry: engine, digital twin, results page", True),
         ("22 Sep", "Department's first answers built in; twin calibrated on its 55 days", True),
         ("5 Oct", "Shortlisted; build sprint starts", True),
         ("21 Oct", "Technical guide and maths notes for the department", True),
         ("24 Oct", "Department's second answers built in; a working app inside CARE", True),
         ("25 Oct", "Sarvam AI layer, patient page, QR check-in, evaluation, narrated video", True),
         ("By 8 Nov", "Technologist trial, native-speaker ratings, final submission", False)]
mw7 = W / 7
line_y = TOP + 0.55
ln = sprint.shapes.add_connector(1, Inches(L + mw7 / 2), Inches(line_y), Inches(R - mw7 / 2), Inches(line_y))
ln.line.color.rgb = rgb(LINE)
ln.line.width = Pt(2)
for i, (d, t, done) in enumerate(miles):
    cx = L + mw7 * (i + 0.5)
    box(sprint, cx - mw7 / 2, TOP, mw7, 0.3, [("h", d)], size=11, align=PP_ALIGN.CENTER)
    dot = sprint.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - 0.11), Inches(line_y - 0.11), Inches(0.22), Inches(0.22))
    dot.fill.solid()
    dot.fill.fore_color.rgb = rgb(GREEN if done else "FFFFFF")
    dot.line.color.rgb = rgb(GREEN if done else GRAY)
    dot.line.width = Pt(1.5)
    _plain(dot)
    dot.name = f"Milestone {d}"
    box(sprint, cx - mw7 / 2 + 0.05, line_y + 0.2, mw7 - 0.1, 1.0, [t], size=11, color=DARK if done else GRAY,
        align=PP_ALIGN.CENTER)
cw3 = (W - 2 * 0.2) / 3
ytop = 3.35
box(sprint, L, ytop, cw3, 6.85 - ytop, [
    ("label", "Functional now"),
    ("b", "Course entry with a standing time, approved by a doctor"),
    ("b", "Day board: arrival, in room, out, live rule check"),
    ("b", "Breakdown re-planning, approved by a person"),
    ("b", "Requests for another time, decided by staff"),
    ("b", "Messages in 4 Indian languages with voice notes, opened in WhatsApp"),
    ("b", "Patient phone page, replies and QR check-in"),
    ("b", "Plain-words explanations, with a time check"),
    ("b", "Insights · 20 automated safety tests"),
], fill=GREEN_T, accent=GREEN, inset=0.16, size=12, gap=2, name="Functional now")
box(sprint, L + cw3 + 0.2, ytop, cw3, 6.85 - ytop, [
    ("label", "How it changed"),
    ("p", "**From idea to app:** Round 1 was an engine with a simulation; it now runs inside CARE, with a patient side."),
    ("p", "**After the department's answers:** one standing time per course; new starts finish before 17:00; "
          "their 60-minute breakdown rule; only a doctor approves a course."),
    ("p", "**Challenges found in testing, fixed:** Kannada attaches suffixes to times; Konkani turned \"the next "
          "working day\" into \"next week\", so messages now name the date; an explanation used the proposed time; "
          "one patient button was unclear."),
], fill=BLUE_T, inset=0.16, size=12, gap=6, name="How it changed")
box(sprint, L + 2 * (cw3 + 0.2), ytop, cw3, 6.85 - ytop, [
    ("label", "Not yet built"),
    ("b", "Automatic WhatsApp sending (needs the hospital's Meta business verification)"),
    ("b", "Spoken replies from patients"),
    ("b", "A Tulu voice (no Sarvam model; staff can record one)"),
    ("b", "Importing Excel lists and paper prescriptions"),
    ("b", "Changing rules in plain words"),
    ("b", "A read-only feed from MOSAIQ or ARIA"),
    ("b", "Live planning for two machines (forecast only)"),
], fill=GRAY_T, accent=GRAY, inset=0.16, size=12, gap=2, name="Not yet built")

# ---------------------------------------------------------------- 10 evaluation (1 of 2)

frame(ev1, "Evaluation and User Validation",
      "Scheduling: the department's own 55 days replayed in a calibrated digital twin, and synthetic scenarios")
box(ev1, L, TOP, 7.3, 0.3, [("label", "90th-percentile wait, minutes: without and with RAD-SMART")])
cd = CategoryChartData()
cd.categories = ["Department's 55 days", "Its busiest days (70+ patients)", "12 synthetic weeks",
                 "One busy synthetic day (87)", "150-min breakdown, live re-plan"]
cd.add_series("Without (today's booking)", (108.6, 130, 82, 210, 210))
cd.add_series("With RAD-SMART", (70.4, 70, 49, 76, 110))
gf = ev1.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(L), Inches(TOP + 0.3), Inches(7.3), Inches(4.6), cd)
gf.name = "Chart: 90th-percentile wait"
ch = gf.chart
ch.font.size, ch.font.name = Pt(11), BODY
ch.font.color.rgb = rgb(DARK)
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.TOP
ch.legend.include_in_layout = False
ch.category_axis.reverse_order = True
ch.category_axis.format.line.color.rgb = rgb(LINE)
ch.category_axis.has_major_gridlines = False
va = ch.value_axis
va.has_major_gridlines = False
va.visible = False
va.maximum_scale = 240
plot = ch.plots[0]
plot.gap_width = 60
plot.overlap = -10
plot.has_data_labels = True
dl = plot.data_labels
dl.number_format, dl.number_format_is_linked = 'General', False
dl.position = XL_LABEL_POSITION.OUTSIDE_END
dl.font.size = Pt(11)
for s, col in zip(plot.series, ("A3ABB6", BLUE)):
    s.format.fill.solid()
    s.format.fill.fore_color.rgb = rgb(col)
box(ev1, L, 6.45, 7.3, 0.45, [("cap", "Same patients and the same random events with and without RAD-SMART. "
                                    "The breakdown row is 300 synthetic days with a 150-minute fault at 10:00.")])
ex = 8.0
rw = R - ex
for i, (num, lab) in enumerate([("22.2% → 5.7%", "treated more than an hour late, on the department's days"),
                                ("28.9% → 49.5%", "treated within 15 minutes of their time"),
                                ("104 → 39 min", "median wait after the breakdown; a new plan in 14 s"),
                                ("0", "hard rules broken on any evaluation day, by an independent checker")]):
    stat(ev1, ex, TOP + i * 1.18, rw, 1.03, num, lab, size=22,
         fill=GREEN_T if i == 3 else BLUE_T, accent=GREEN if i == 3 else BLUE)
box(ev1, ex, TOP + 4.75, rw, 0.62, [("cap", "**Limitation:** a replay, not a live trial. The pilot measures the gain for real.")])

# ---------------------------------------------------------------- 11 evaluation (2 of 2)

frame(ev2, "Evaluation and User Validation",
      "The AI parts are measured, and the department's feedback and our tests changed the design")
ai = [("2.15 min", "session-length error on 2,000 held-out synthetic sessions (2.62 for a table of averages)"),
      ("7.1 s", "to a proven optimum for an 87-patient day, about 4,800 variables, on a laptop"),
      ("112 / 112", "Sarvam translations kept every clock time: Kannada, Malayalam, Hindi, Konkani"),
      ("76–80", "median back-translation score (chrF) by language: meaning kept, a rough check"),
      ("20 / 20", "Sarvam-105B explanations accepted, with no invented time")]
aw = (W - 4 * 0.16) / 5
for i, (num, lab) in enumerate(ai):
    stat(ev2, L + i * (aw + 0.16), TOP, aw, 1.6, num, lab, size=22)
yb = TOP + 1.85
box(ev2, L, yb, cw3, 6.85 - yb, [
    ("label", "User validation so far"),
    ("p", "**The department's technologists and doctors** answered in writing on 21 Sep and 24 Oct: roles, "
          "standing slots, breakdown rules and the screens they need. All of it is built."),
    ("p", "**Planned before 8 Nov:** technologists run the demo day on the app, and native speakers rate all 112 "
          "translations (the rating sheet is ready)."),
    ("p", "**Evidence:** every translation with its back-translation, and the full results, are in "
          "docs/evaluation in the code repository."),
], fill=BLUE_T, inset=0.16, size=13, gap=8, name="User validation")
box(ev2, L + cw3 + 0.2, yb, cw3, 6.85 - yb, [
    ("label", "Improved from the results"),
    ("b", "The time check reads times in every Indian script; Kannada suffixes were missed at first"),
    ("b", "Messages name the date: Konkani turned \"the next working day\" into \"next week\""),
    ("b", "Explanations use the time in force, not the proposed one"),
    ("b", "An unclear patient button was reworded"),
    ("b", "20 automated safety tests now guard all of this"),
], fill=GREEN_T, accent=GREEN, inset=0.16, size=13, gap=3, name="Improvements")
box(ev2, L + 2 * (cw3 + 0.2), yb, cw3, 6.85 - yb, [
    ("label", "Limitations"),
    ("b", "Scheduling results are a replay, not a live trial"),
    ("b", "Session lengths are synthetic until the board records real ones"),
    ("b", "If patients keep arriving very early, the busy-day wait is 110 min, not 76"),
    ("b", "Back-translation is a rough check; native speakers must rate"),
    ("b", "Sarvam has no Tulu model: Tulu speakers get Kannada"),
], fill=GRAY_T, accent=GRAY, inset=0.16, size=13, gap=3, name="Limitations")

# ---------------------------------------------------------------- 12 safety

frame(safety, "Safety and Responsible AI",
      "RAD-SMART proposes and people decide; the AI is fenced in, and patients' details stay out of it")
quads = [
    ("Human oversight and safeguards", BLUE_T, BLUE, [
        "A doctor approves each course and its time; a technologist or doctor approves every change on the day, "
        "breakdowns included. The approver and time are recorded",
        "Hard rules are optimiser constraints, so a plan that breaks one cannot be made; an independent checker "
        "re-checks every plan",
        "It decides only when, never whether or how; it is not a diagnostic or treatment-planning tool",
        "If a hard rule is broken during the pilot, the department returns to manual scheduling"]),
    ("AI limits and error handling", BLUE_T, BLUE, [
        "Language models never schedule; they translate and explain decisions already approved",
        "A translation that drops, changes or adds a clock time is discarded: the patient gets English",
        "An explanation with a time not in the engine's facts is rejected; the prompt forbids medical advice",
        "If Sarvam is down, messages go in English: scheduling never depends on it. Staff read both texts before sending"]),
    ("Privacy, consent and security", GREEN_T, GREEN, [
        "No names, hospital numbers or phone numbers go to Sarvam: only message text with times and dates",
        "Patient page: a long random link, first name only, six replies a day at most; the QR holds a six-letter code",
        "Sent from the department's own WhatsApp by a person; demo and evaluation data are synthetic",
        "Pilot: DPDP Act 2023 and Rules 2025 (notice and consent for messaging) and ethics committee review"]),
    ("Fairness, access and inclusion", GREEN_T, GREEN, [
        "Older patients, patients on public transport or the hospice bus, and doctors' time windows are protected "
        "by explicit rules, not left to chance",
        "Messages in Kannada, Malayalam, Hindi and Konkani, with voice notes for those who read little",
        "Tulu speakers read Kannada; staff can record a Tulu voice note",
        "Works on any phone with a browser: no app, no login; the page switches between the patient's language and English",
        "Patients can ask for another daily time from the page; staff decide"]),
]
qw, qh = (W - 0.2) / 2, (6.85 - TOP - 0.2) / 2
for i, (h, fill, acc, items) in enumerate(quads):
    r, c = divmod(i, 2)
    box(safety, L + c * (qw + 0.2), TOP + r * (qh + 0.2), qw, qh, [("label", h)] + [("b", t) for t in items],
        fill=fill, accent=acc, inset=0.16, size=12, gap=2, name=h)

# ---------------------------------------------------------------- 13 deployment

frame(deploy, "Deployment, Cost and Sustainability Plan",
      "Installs as a CARE plugin on the hospital's own server; about ₹1 a message to run")
lw = 5.75
box(deploy, L, TOP, lw, 2.75, [
    ("label", "What a pilot needs"),
    ("b", "A CARE instance (the hospital's, or a VM running CARE with Docker Compose); RAD-SMART installs as a "
          "backend and a frontend plugin"),
    ("b", "A laptop or tablet at the machine console and at reception; a USB QR scanner or the camera"),
    ("b", "The department's WhatsApp on a staff phone or WhatsApp Web"),
    ("b", "Internet and an API key for Sarvam; everything else works offline"),
    ("b", "Approval by the head of department, the ethics committee and hospital IT"),
], fill=GRAY_T, inset=0.16, size=12, gap=2, name="Requirements")
box(deploy, L, TOP + 2.9, lw, 1.5, [
    ("label", "Integration"),
    ("p", "Uses CARE's own patients, facilities, users and permissions, adds its own tables, and installs and "
          "removes like any CARE plugin. **Next:** a read-only feed from the oncology information system (MOSAIQ or "
          "ARIA, HL7 v2 or FHIR R4), so courses are not typed twice; later, the WhatsApp Business API."),
], fill=BLUE_T, inset=0.16, size=12, gap=4, name="Integration")
tx = L + lw + 0.25
tw = R - tx
rows = [("One-time", None),
        ("Server with UPS (₹0 on an existing hospital VM)", "0 – 1,50,000"),
        ("Tablets for console and reception (₹0 on existing PCs)", "0 – 60,000"),
        ("QR scanner and labels", "5,000 – 15,000"),
        ("Software licence (open source)", "0"),
        ("Ongoing", None),
        ("Per message, about 190 characters: translation ₹0.38 + voice ₹0.57", "about 1"),
        ("Per course: about 3 messages, plus explanations under ₹0.10", "about 3 – 5"),
        ("Per facility per month: about 85 new courses, plus breakdown messages", "about 400 – 850"),
        ("Hosting on the hospital's own server or VM", "0")]
tbl = deploy.shapes.add_table(len(rows) + 1, 2, Inches(tx), Inches(TOP), Inches(tw), Inches(3.8))
tbl.name = "Cost table"
t = tbl.table
t.columns[0].width = Inches(tw - 1.55)
t.columns[1].width = Inches(1.55)


def cell(c, text, bold=False, color=DARK, fill="FFFFFF", align=PP_ALIGN.LEFT, size=11.5):
    c.fill.solid()
    c.fill.fore_color.rgb = rgb(fill)
    c.margin_left = c.margin_right = Inches(0.1)
    c.margin_top = c.margin_bottom = Inches(0.04)
    c.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf = c.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    _run(p, text, size, color, bold=bold)


cell(t.cell(0, 0), "Item, with the pricing assumption", True, "FFFFFF", BLUE)
cell(t.cell(0, 1), "Estimate (₹)", True, "FFFFFF", BLUE, PP_ALIGN.RIGHT)
for i, (a, b) in enumerate(rows, 1):
    if b is None:
        t.cell(i, 0).merge(t.cell(i, 1))
        cell(t.cell(i, 0), a.upper(), True, BLUE, BLUE_T, size=10.5)
    else:
        cell(t.cell(i, 0), a, fill="FFFFFF" if i % 2 else GRAY_T)
        cell(t.cell(i, 1), b, True, fill="FFFFFF" if i % 2 else GRAY_T, align=PP_ALIGN.RIGHT)
box(deploy, tx, TOP + 3.9, tw, 0.55, [("cap", "Sarvam list prices, to confirm before the pilot: Translate ₹20 and Bulbul v3 "
                                          "₹30 per 10,000 characters; Sarvam-105B ₹4 and ₹16 per million tokens in and out. "
                                          "About 1,000 courses a year. Voice notes are made only when played.")])
box(deploy, L, 6.05, W, 0.8, [
    "**Scale and sustain:** a 90-day pilot on the Versa HD, then the second machine in 2027, then other hospitals that "
    "run CARE. 69% of India's radiotherapy centres have one machine. Open source and a few thousand rupees a year "
    "to run, so the department's own staff can keep it going after the pilot."],
    fill=GREEN_T, anchor="m", inset=0.2, size=12.5, name="Scale and sustain")

# ---------------------------------------------------------------- 14 next steps

frame(nxt, "What Next? Plans to Take It Forward",
      "Validate with the department, then a 90-day pilot on the Versa HD")
plan = [("By 8 Nov 2026", "Technologist trial of the demo; native speakers rate every translation"),
        ("Nov – Dec 2026", "Head of department approval; ethics committee review; hospital IT sign-off; "
                           "patient notice and consent for messaging"),
        ("Jan 2027", "Pilot phase 1, two weeks: measure today's waits with the day board"),
        ("Feb 2027", "Pilot phase 2, three weeks in shadow mode: RAD-SMART proposes, staff still schedule by hand, "
                     "and we compare"),
        ("Feb – Apr 2027", "Pilot phase 3, eight weeks live; retrain the minute model on real minutes. "
                           "Target: 90th-percentile wait at least 25% below 109 min"),
        ("Later in 2027", "WhatsApp Business API, spoken replies, the second machine, a read-only OIS feed, "
                          "and the plugin offered to other CARE hospitals")]
pw8 = 8.1
rh = (6.85 - TOP - 5 * 0.12) / 6
for i, (when, what) in enumerate(plan):
    y = TOP + i * (rh + 0.12)
    box(nxt, L, y, 1.75, rh, [("h", when)], fill=BLUE_T, anchor="m", inset=0.12, size=11, name=f"When: {when}")
    box(nxt, L + 1.9, y, pw8 - 1.9, rh, [what], fill=GRAY_T, anchor="m", inset=0.14, size=12, name=f"Plan: {when}")
nx = L + pw8 + 0.25
box(nxt, nx, TOP, R - nx, 1.85, [
    ("label", "Pilot budget"),
    ("p", "Up to about ₹2.3 lakh for a server, tablets and a QR scanner, or close to nothing on existing hospital "
          "PCs and a VM; Sarvam about ₹5,000–10,000 a year. No licence fee."),
], fill=GRAY_T, inset=0.16, size=12, gap=4, name="Pilot budget")
box(nxt, nx, TOP + 2.05, R - nx, 6.85 - TOP - 2.05, [
    ("label", "Make the solution public?"),
    ("big", "Yes", 30),
    ("p", "The code, website, deck, research paper and demo video are already public and open source."),
], fill=GREEN_T, accent=GREEN, inset=0.16, size=12, gap=4, name="Public")

# ---------------------------------------------------------------- 15 thank you

shapes = {s.name.split(";")[1]: s for s in thanks.shapes if ";" in s.name}
set_text(shapes["191"], f"{TEAM_NAME}  •  {TEAM_CODE}")
links = shapes["192"]
tf = links.text_frame
proto = tf.paragraphs[0].runs[0]
size, color = proto.font.size.pt, str(proto.font.color.rgb)
for p in list(tf.paragraphs):
    p._p.getparent().remove(p._p)
for label, text, url in [("Contact", CONTACT, None),
                         ("MVP and website", "psraghothamrao8.github.io/RAD-SMART", SITE),
                         ("Demo video", "psraghothamrao8.github.io/RAD-SMART/#demo", VIDEO),
                         ("Code repository", "github.com/psraghothamrao8/RAD-SMART", CODE)]:
    p = tf.add_paragraph()
    p.alignment = PP_ALIGN.CENTER
    p.space_after = Pt(4)
    _run(p, label + ":  ", size, color, bold=True, font=HEAD)
    _run(p, text, size, BLUE if url else color, font=HEAD, link=url)
shapes["193"].top = Inches(5.6)

for slide in prs.slides:
    for s in slide.shapes:
        if s.shape_type == MSO_SHAPE_TYPE.PICTURE and s._element.nvPicPr.cNvPr.get("descr") in ("image(3).png", "image.png"):
            s._element.nvPicPr.cNvPr.set("descr", "Health-a-thon 2026 logo")

prs.save(str(out))
print("wrote", out, f"{out.stat().st_size / 1024:.0f} KB,", len(prs.slides), "slides")
