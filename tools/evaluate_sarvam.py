"""Evaluate the Sarvam AI layer on RAD-SMART's own patient messages.

For every message template, with several sets of times, in every patient
language:
  1. translate English -> language (Sarvam Translate, as the app does);
  2. check that every clock time survived (the app's own guard);
  3. translate back to English and score it against the source (chrF,
     character n-gram F-score: 100 = identical);
  4. time each call.
Then ask Sarvam-105B to explain synthetic plans and count answers that
mention a time not in the facts (the app rejects those).

Only synthetic text is sent: no patient names, numbers or department data.

    set SARVAM_API_KEY=...   (or --env-file path/to/.env with SARVAM_API_KEY=...)
    python tools/evaluate_sarvam.py

Writes docs/evaluation/sarvam_evaluation.md, .json, and a CSV with one row per
translation for native speakers to rate (1-5: correct and natural).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import statistics
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

API = "https://api.sarvam.ai"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evaluation"
DEPT = "Radiotherapy department"

# Patient language -> Sarvam code (Tulu is sent in Kannada script; see sarvam.py).
LANGUAGES = {"Kannada": "kn-IN", "Malayalam": "ml-IN", "Hindi": "hi-IN", "Konkani": "kok-IN", "Tulu": "kn-IN"}

# The same wording as care_radsmart/messages.py.
TEMPLATES = {
    "course": lambda a, b: (f"{DEPT}: your radiotherapy starts on Tuesday, 27 October. Please come at {a}. After the first "
                            f"day, please come at {b} on every treatment day. This time stays the same until your course ends."),
    "course_pelvis": lambda a, b: (f"{DEPT}: your radiotherapy starts on Monday, 2 November. Please come at {a}. After the "
                                   f"first day, please come at {b} on every treatment day. This time stays the same until "
                                   "your course ends. Please drink the water as the staff told you, before you come."),
    "slot": lambda a, b: (f"{DEPT}: from Thursday, 29 October, please come at {a} on every treatment day. This is the new "
                          "time you asked for."),
    "new_time": lambda a, b: (f"{DEPT}: the treatment machine has a fault. Please come at {a} today, not at {b}. Please "
                              "do not leave home before then."),
    "do_not_travel": lambda a, b: (f"{DEPT}: the treatment machine is being repaired. Please do not travel today. Please "
                                   f"come on Tuesday, 27 October at your usual time, {b}. The missed treatment is added "
                                   "at the end of your course."),
    "send_home": lambda a, b: (f"{DEPT}: the treatment machine is being repaired, so you cannot be treated today. Please "
                               f"come on Tuesday, 27 October at your usual time, {b}. The missed treatment is added at the "
                               "end of your course."),
    "start_next_day": lambda a, b: (f"{DEPT}: the treatment machine has a fault, so your first treatment moves to "
                                    f"Tuesday, 27 October. Please come at {a}."),
}

TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)(?:\s*([AaPp])\.?\s*[Mm](?![A-Za-z])\.?)?")


def times(text):
    out = []
    for h, m, ap in TIME.findall(text or ""):
        h = int(h) % 12 + (12 if ap.lower() == "p" else 0) if ap else int(h)
        out.append(f"{h:02d}:{m}")
    return sorted(out)


def chrf(hyp: str, ref: str, n: int = 6, beta: float = 2.0) -> float:
    """chrF (Popovic 2015): character n-gram F-score, 0-100."""
    hyp, ref = " ".join(hyp.lower().split()), " ".join(ref.lower().split())
    precisions, recalls = [], []
    for k in range(1, n + 1):
        h = Counter(hyp[i:i + k] for i in range(len(hyp) - k + 1))
        r = Counter(ref[i:i + k] for i in range(len(ref) - k + 1))
        if not h or not r:
            continue
        match = sum((h & r).values())
        precisions.append(match / sum(h.values()))
        recalls.append(match / sum(r.values()))
    p, r = statistics.mean(precisions), statistics.mean(recalls)
    return 0.0 if p + r == 0 else 100 * (1 + beta**2) * p * r / (beta**2 * p + r)


class Sarvam:
    def __init__(self, key: str):
        self.h = {"api-subscription-key": key, "Content-Type": "application/json"}

    def post(self, path, body, timeout=60):
        t = time.perf_counter()
        for attempt in range(6):
            r = requests.post(f"{API}{path}", json=body, headers=self.h, timeout=timeout)
            if r.status_code != 429:
                break
            time.sleep(1.5 * 2**attempt)
        r.raise_for_status()
        return r.json(), time.perf_counter() - t

    def translate(self, text, src, tgt):
        data, secs = self.post("/translate", {"input": text, "source_language_code": src, "target_language_code": tgt,
                                              "model": "sarvam-translate:v1", "mode": "formal",
                                              "numerals_format": "international"})
        return data["translated_text"], secs


def hm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def time_pairs(k, rng):
    """Come-at times across the day, including evening slots up to 22:00."""
    pairs = []
    for _ in range(k):
        a = rng.randrange(8 * 60, 22 * 60)
        b = min(max(a + rng.choice([-90, -45, 30, 60, 120]), 8 * 60), 22 * 60)
        pairs.append((hm(a), hm(b)))
    return pairs


def previous():
    """Results of the last run that succeeded, so a rerun (for example after a
    credit top-up) only asks Sarvam for what is missing."""
    f = OUT / "sarvam_evaluation.json"
    if not f.exists():
        return {}, {}
    data = json.loads(f.read_text(encoding="utf-8"))
    tr = {(r["code"], r["source"]): {k: r[k] for k in ("local", "back", "latency", "error")}
          for r in data.get("translations", []) if not r["error"]}
    ex = {json.dumps(r["facts"], sort_keys=True): r for r in data.get("explanations", []) if not r["error"]}
    return tr, ex


def run_translation(sv: Sarvam, variants: int, seed: int, prev: dict):
    rng = random.Random(seed)
    jobs = []
    for name, make in TEMPLATES.items():
        pairs = time_pairs(variants, rng)
        for a, b in pairs:
            text = make(a, b)
            for lang, code in LANGUAGES.items():
                jobs.append({"template": name, "language": lang, "code": code, "source": text})
    # Tulu and Kannada share a model: translate once per text, report both.
    unique = {(j["code"], j["source"]) for j in jobs}

    def one(key):
        if key in prev:
            return key, prev[key]
        code, src = key
        try:
            local, t1 = sv.translate(src, "en-IN", code)
            back, t2 = sv.translate(local, code, "en-IN")
            return key, {"local": local, "back": back, "latency": t1, "error": ""}
        except (requests.RequestException, KeyError, ValueError) as exc:
            return key, {"local": "", "back": "", "latency": None, "error": str(exc)[:120]}

    with ThreadPoolExecutor(max_workers=3) as pool:
        done = dict(pool.map(one, sorted(unique)))
    rows = []
    for j in jobs:
        d = done[(j["code"], j["source"])]
        rows.append({**j, **d,
                     "times_kept": (not d["error"]) and times(j["source"]) == times(d["local"]),
                     "chrf_back": round(chrf(d["back"], j["source"]), 1) if d["back"] else None})
    return rows


EXPLAIN_SYSTEM = (
    "You explain radiotherapy appointment times for a hospital radiotherapy department. You are given facts "
    "from the scheduling engine. Use only those facts and do not add any reason that is not in them. Never give "
    "medical advice and never comment on the treatment itself. Write times exactly as they appear in the facts "
    "(24-hour HH:MM). Write plain English for the technologist and the patient, in at most 3 short sentences, with "
    "no lists, no headings and no markdown.")

NEEDS = ["public transport", "older", "full bladder", "gap-sensitive", "wheelchair", "concurrent chemotherapy", "works"]
REASONS = ["new start on the first free slot that finishes by 17:00", "standing slot kept free of the evening queue",
           "slot after chemotherapy day-care", "slot within the patient's preferred window",
           "leaves a 30-minute gap for urgent palliative patients", "machine with the bolus and mask accessories"]


def run_explain(sv: Sarvam, n: int, seed: int, prev: dict):
    rng = random.Random(seed + 1)
    rows = []
    for i in range(n):
        first = rng.randrange(9 * 60, 15 * 60, 5)
        lead = rng.choice([20, 45])
        later = rng.randrange(9 * 60, 21 * 60, 5)
        facts = {
            "Treatment": f"{rng.choice(['IMRT', 'VMAT', '3D-CRT', 'Palliative'])}, {rng.choice([5, 10, 25, 28, 30])} fractions",
            "Patient needs": ", ".join(rng.sample(NEEDS, rng.randint(1, 3))),
            "First treatment (new start)": f"2026-11-0{rng.randint(2, 6)}, treatment at {hm(first)}, come at {hm(first - lead)}. "
                                           "Department rule: every new start must finish by 17:00",
            "Every later treatment": f"at {hm(later)} on the Versa HD, come at {hm(later - lead)} ({lead} minutes early)",
            "Engine's reasons": "; ".join(rng.sample(REASONS, 2)),
        }
        lines = "\n".join(f"- {k}: {v}" for k, v in facts.items())
        if json.dumps(facts, sort_keys=True) in prev:
            rows.append(prev[json.dumps(facts, sort_keys=True)])
            continue
        try:
            data, secs = sv.post("/v1/chat/completions", {
                "model": "sarvam-105b", "temperature": 0.2, "max_tokens": 500, "reasoning_effort": None,
                "messages": [{"role": "system", "content": EXPLAIN_SYSTEM},
                             {"role": "user", "content": f"Facts:\n{lines}\n\nExplain why these times were chosen."}]})
            text = re.sub(r"<think>.*?</think>", "", data["choices"][0]["message"].get("content") or "", flags=re.S)
            text = text.replace("**", "").strip()
            err = ""
        except (requests.RequestException, KeyError, ValueError, IndexError) as exc:
            text, secs, err = "", None, str(exc)[:120]
        invented = sorted(set(times(text)) - set(times(lines)))
        rows.append({"facts": facts, "text": text, "latency": secs, "error": err, "empty": not text,
                     "invented_times": invented, "accepted": bool(text) and not invented,
                     "mentions_all_key_times": all(t in text for t in (hm(first - lead), hm(later)))})
    return rows


def pct(x, n):
    return f"{100 * x / n:.0f}%" if n else "—"


def report(tr, ex, args):
    OUT.mkdir(parents=True, exist_ok=True)
    by_lang = defaultdict(list)
    for r in tr:
        by_lang[r["language"]].append(r)
    lines = [
        "# Sarvam AI evaluation on RAD-SMART's patient messages",
        "",
        f"Run on {time.strftime('%d %B %Y')} with `tools/evaluate_sarvam.py --variants {args.variants} --explain {args.explain}`. "
        "Synthetic text only. Sarvam Translate (`sarvam-translate:v1`) and Sarvam-105B, the same settings as the app.",
        "",
        "## Translation of patient messages",
        "",
        f"{len(TEMPLATES)} message templates (new course, pelvic new course, new standing time, the four breakdown messages) with "
        f"{args.variants} sets of times each, in every patient language. **Times kept** is the app's own guard: a translation "
        "that drops, changes or adds a clock time is not sent (the patient gets English). **Back-translation chrF** "
        "translates the result back to English and compares it with the source (0-100; a rough meaning check, "
        "not a substitute for native speakers).",
        "",
        "| Language | Messages | Times kept (of those returned) | Back-translation chrF (median) | Lowest chrF | Median seconds | Errors |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for lang, rows in by_lang.items():
        ok = [r for r in rows if not r["error"]]
        scores = [r["chrf_back"] for r in ok if r["chrf_back"] is not None]
        lat = [r["latency"] for r in ok if r["latency"]]
        lines.append(f"| {lang}{' (Kannada script)' if lang == 'Tulu' else ''} | {len(rows)} | "
                     f"{pct(sum(r['times_kept'] for r in ok), len(ok))} | "
                     f"{statistics.median(scores):.0f} | {min(scores):.0f} | "
                     f"{statistics.median(lat):.1f} | {len(rows) - len(ok)} |" if scores else
                     f"| {lang} | {len(rows)} | — | — | — | — | {len(rows) - len(ok)} |")
    # Tulu patients get the Kannada translation, so count each distinct translation once.
    own = [r for r in tr if r["language"] != "Tulu"]
    allk, got = sum(r["times_kept"] for r in own), sum(not r["error"] for r in own)
    lines += ["", f"Overall: {allk} of {got} distinct translations kept every time ({pct(allk, got)}), in "
              f"{len({r['language'] for r in own})} languages; the Tulu row repeats Kannada's, because Sarvam has no "
              f"Tulu model and Tulu speakers get the Kannada text. {len(own) - got} requests failed after retries "
              f"(the app sends English in that case).", ""]
    if any("402" in r["error"] for r in tr) or any("402" in r["error"] for r in ex):
        lines += ["**Incomplete run:** the Sarvam account ran out of credit (HTTP 402) part-way. Rerun the script "
                  "after a top-up: it keeps every result above and asks only for the missing ones.", ""]
    lost = [r for r in tr if not r["times_kept"] and not r["error"]]
    if lost:
        lines += ["Translations the guard stopped (sent in English instead):", ""]
        for r in lost[:8]:
            lines.append(f"- {r['language']}, {r['template']}: source times {times(r['source'])}, "
                         f"translation times {times(r['local'])}")
        lines.append("")
    worst = sorted((r for r in tr if r["chrf_back"] is not None), key=lambda r: r["chrf_back"])[:3]
    if worst:
        lines += ["Lowest back-translation scores (for the native-speaker check):", ""]
        for r in worst:
            lines.append(f"- {r['language']}, {r['template']} (chrF {r['chrf_back']:.0f}): \"{r['back']}\"")
        lines.append("")
    n = len(ex)
    acc = sum(r["accepted"] for r in ex)
    lat = [r["latency"] for r in ex if r["latency"]]
    lines += [
        "## Plain-language explanations (Sarvam-105B)",
        "",
        f"{n} synthetic plans (random needs, reasons, first-day and standing times). The app rejects an answer that "
        "mentions a time not in the facts and shows the engine's own reasons instead.",
        "",
        "| Measure | Result |",
        "|---|---:|",
        f"| Answers accepted by the time check | {acc} of {n} ({pct(acc, n)}) |",
        f"| Answers with an invented time (rejected) | {sum(bool(r['invented_times']) for r in ex)} |",
        f"| Empty answers or errors (fall back to the engine's reasons) | {sum(r['empty'] for r in ex)} |",
        f"| Accepted answers that state both come-at times | {sum(r['accepted'] and r['mentions_all_key_times'] for r in ex)} |",
        f"| Median seconds per answer | {statistics.median(lat):.1f} |" if lat else "| Median seconds per answer | — |",
        "",
        "Sample accepted answer:",
        "",
        f"> {next((r['text'] for r in ex if r['accepted']), '—')}",
        "",
        "## Still to do with people",
        "",
        f"`sarvam_translations_for_rating.csv` has every translation with its back-translation. Native speakers of "
        "Kannada, Tulu, Malayalam, Konkani and Hindi at the department rate each 1-5 (correct and natural for a "
        "patient). Messages below 4 get their English wording simplified before the pilot.",
        "",
    ]
    (OUT / "sarvam_evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "sarvam_evaluation.json").write_text(json.dumps({"translations": tr, "explanations": ex}, ensure_ascii=False,
                                                           indent=1), encoding="utf-8")
    with open(OUT / "sarvam_translations_for_rating.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["language", "template", "english", "translation", "back_translation", "times_kept", "chrf_back",
                    "rating_1_to_5", "comment"])
        seen = set()
        for r in tr:
            if (r["language"], r["template"]) in seen:   # one example per template and language is enough to rate
                continue
            seen.add((r["language"], r["template"]))
            w.writerow([r["language"], r["template"], r["source"], r["local"], r["back"], r["times_kept"], r["chrf_back"],
                        "", ""])
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", help="a .env file holding SARVAM_API_KEY=...")
    ap.add_argument("--variants", type=int, default=4, help="sets of times per template")
    ap.add_argument("--explain", type=int, default=20, help="synthetic plans to explain")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    key = os.environ.get("SARVAM_API_KEY", "")
    if args.env_file:
        for line in Path(args.env_file).read_text(encoding="utf-8").splitlines():
            if line.startswith("SARVAM_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("Set SARVAM_API_KEY or pass --env-file.")
    sv = Sarvam(key)
    prev_tr, prev_ex = previous()
    tr = run_translation(sv, args.variants, args.seed, prev_tr)
    ex = run_explain(sv, args.explain, args.seed, prev_ex)
    report(tr, ex, args)


if __name__ == "__main__":
    main()
