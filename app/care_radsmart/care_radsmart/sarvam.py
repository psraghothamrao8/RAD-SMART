"""Sarvam AI: translation (Sarvam Translate), voice notes (Bulbul) and
plain-language explanations (Sarvam-105B).

The language model never schedules. It only explains a plan the optimiser
made, from the reasons the engine gives, and every answer is checked:
a translation or explanation that changes, drops or invents a time is thrown
away and the English text is used instead. Nothing sent to Sarvam carries a
patient's name, hospital number or phone number.

Without a key (or when Sarvam cannot be reached) every function falls back:
patients get the English message and staff see the engine's own reasons.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from django.core.cache import cache

from care_radsmart.settings import plugin_settings

log = logging.getLogger(__name__)

API = "https://api.sarvam.ai"
TRANSLATE_MODEL = "sarvam-translate:v1"
VOICE_MODEL = "bulbul:v3"
CHAT_MODEL = "sarvam-105b"
WEEK = 7 * 24 * 3600

# Patient language -> (text language, voice language, note for staff).
# Tulu has no Sarvam model: Tulu speakers read Kannada script, and staff can
# record a Tulu voice note themselves. Konkani has text but no Sarvam voice.
LANGUAGES = {
    "English": ("en-IN", "en-IN", ""),
    "Kannada": ("kn-IN", "kn-IN", ""),
    "Malayalam": ("ml-IN", "ml-IN", ""),
    "Hindi": ("hi-IN", "hi-IN", ""),
    "Konkani": ("kok-IN", None, "Konkani text in Devanagari script; no voice note for Konkani yet."),
    "Tulu": ("kn-IN", "kn-IN", "Tulu has no Sarvam model yet: sent in Kannada. Staff can add a Tulu voice note."),
}

# Digit lookarounds, not \b: Indian scripts join suffixes straight onto the
# time ("16:27ಕ್ಕೆ"), and \b does not hold between a digit and those letters.
TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)(?:\s*([AaPp])\.?\s*[Mm](?![A-Za-z])\.?)?")


def enabled() -> bool:
    return bool(str(plugin_settings.SARVAM_API_KEY or "").strip())


def _headers() -> dict:
    return {"api-subscription-key": str(plugin_settings.SARVAM_API_KEY).strip(), "Content-Type": "application/json"}


def _post(path: str, body: dict, timeout: float | None = None) -> dict:
    # A breakdown drafts many messages at once: wait and retry when Sarvam says
    # "too many requests" (429) rather than sending those patients English.
    for attempt in range(4):
        r = requests.post(f"{API}{path}", json=body, headers=_headers(),
                          timeout=timeout or float(plugin_settings.RADSMART_SARVAM_TIMEOUT))
        if r.status_code != 429 or attempt == 3:
            break
        wait = r.headers.get("Retry-After", "")
        time.sleep(min(float(wait), 10) if wait.replace(".", "", 1).isdigit() else 1.5 * 2**attempt)
    r.raise_for_status()
    return r.json()


def _key(*parts) -> str:
    return "radsmart:sarvam:" + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def times(text: str) -> list[str]:
    """Every clock time in a text, as HH:MM, in order."""
    out = []
    for h, m, ap in TIME.findall(text or ""):
        h = int(h) % 12 + (12 if ap.lower() == "p" else 0) if ap else int(h)
        out.append(f"{h:02d}:{m}")
    return out


def same_times(source: str, result: str) -> bool:
    """A translation must keep every time of the source, and add none."""
    return sorted(times(source)) == sorted(times(result))


# ---------------------------------------------------------------- translate
def translate(text: str, language: str) -> tuple[str | None, str, str]:
    """(translated text or None, status, note). Status is "ok", "english"
    (English patient, or no key) or "failed" (Sarvam erred, or the result
    changed a time: the English text is used)."""
    code, _, note = LANGUAGES.get(language, ("en-IN", None, ""))
    if code == "en-IN":
        return None, "english", ""
    if not enabled():
        return None, "english", "Sarvam AI is not connected: sent in English."
    k = _key("tr", TRANSLATE_MODEL, code, text)
    out = cache.get(k)
    if out is None:
        try:
            out = _post("/translate", {"input": text, "source_language_code": "en-IN", "target_language_code": code,
                                       "model": TRANSLATE_MODEL, "mode": "formal",
                                       "numerals_format": "international"})["translated_text"]
        except (requests.RequestException, KeyError, ValueError) as exc:
            log.warning("Sarvam translate failed: %s", exc)
            return None, "failed", "Sarvam AI could not be reached: sent in English."
        cache.set(k, out, WEEK)
    if not same_times(text, out):
        return None, "failed", "The translation changed a time, so it was not used: sent in English."
    return out, "ok", note


def translate_many(texts: list[str], language: str) -> dict[str, str]:
    """English -> translated text for a page's labels (English where a
    translation is not available). Requests run in parallel and are cached."""
    if LANGUAGES.get(language, ("en-IN",))[0] == "en-IN" or not enabled():
        return {t: t for t in texts}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda t: translate(t, language)[0], texts))
    return {t: (r or t) for t, r in zip(texts, results)}


# -------------------------------------------------------------------- voice
def voice_language(language: str) -> str | None:
    return LANGUAGES.get(language, ("en-IN", "en-IN", ""))[1]


def speak(text: str, language: str, speaker: str = "kavya") -> bytes | None:
    """An MP3 voice note of the text (Bulbul), or None."""
    code = voice_language(language)
    if not enabled() or not code or not text:
        return None
    k = _key("tts", VOICE_MODEL, speaker, code, text)
    audio = cache.get(k)
    if audio is None:
        try:
            data = _post("/text-to-speech", {"text": text[:2400], "language_code": code, "model": VOICE_MODEL,
                                             "speaker": speaker, "pace": 0.9, "output_audio_codec": "mp3"})
            audio = base64.b64decode(data["audios"][0])
        except (requests.RequestException, KeyError, ValueError, IndexError) as exc:
            log.warning("Sarvam voice failed: %s", exc)
            return None
        cache.set(k, audio, WEEK)
    return audio


# ------------------------------------------------------------------ explain
SYSTEM = (
    "You explain radiotherapy appointment times for a hospital radiotherapy department. You are given facts "
    "from the scheduling engine. Use only those facts and do not add any reason that is not in them. Never give "
    "medical advice and never comment on the treatment itself. Write times exactly as they appear in the facts "
    "(24-hour HH:MM). Write plain English for {audience}, in at most {sentences} short sentences, with no lists, "
    "no headings and no markdown."
)


def explain(facts: dict, audience: str = "the technologist and the patient", sentences: int = 3) -> tuple[str | None, str]:
    """(explanation or None, why not). Facts must not hold names or numbers
    that identify the patient."""
    if not enabled():
        return None, "Sarvam AI is not connected."
    lines = "\n".join(f"- {k}: {v}" for k, v in facts.items() if v not in (None, "", []))
    k = _key("explain", CHAT_MODEL, audience, sentences, lines)
    text = cache.get(k)
    if text is None:
        try:
            data = _post("/v1/chat/completions", {
                # Reasoning off: with it on, the model spends every token thinking. With clear
                # facts it answers in about a second, and the time check below still applies.
                "model": CHAT_MODEL, "temperature": 0.2, "max_tokens": 500, "reasoning_effort": None,
                "messages": [{"role": "system", "content": SYSTEM.format(audience=audience, sentences=sentences)},
                             {"role": "user", "content": f"Facts:\n{lines}\n\nExplain why these times were chosen."}]},
                timeout=60)
            text = (data["choices"][0]["message"].get("content") or "").strip()
        except (requests.RequestException, KeyError, ValueError, IndexError) as exc:
            log.warning("Sarvam explain failed: %s", exc)
            return None, "Sarvam AI could not be reached."
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).replace("**", "").strip()
        if not text:
            return None, "Sarvam AI gave no answer."
        cache.set(k, text, WEEK)
    if not set(times(text)) <= set(times(lines)):
        return None, "The explanation mentioned a time that is not in the plan, so it was not used."
    return text, ""
