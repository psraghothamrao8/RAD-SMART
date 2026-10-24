# Sarvam AI evaluation on RAD-SMART's patient messages

Run on 25 October 2026 with `tools/evaluate_sarvam.py --variants 4 --explain 20`. Synthetic text only. Sarvam Translate (`sarvam-translate:v1`) and Sarvam-105B, the same settings as the app.

## Translation of patient messages

7 message templates (new course, pelvic new course, new standing time, the four breakdown messages) with 4 sets of times each, in every patient language. **Times kept** is the app's own guard: a translation that drops, changes or adds a clock time is not sent (the patient gets English). **Back-translation chrF** translates the result back to English and compares it with the source (0-100; a rough meaning check, not a substitute for native speakers).

| Language | Messages | Times kept (of those returned) | Back-translation chrF (median) | Lowest chrF | Median seconds | Errors |
|---|---:|---:|---:|---:|---:|---:|
| Kannada | 28 | 100% | 80 | 67 | 1.4 | 0 |
| Malayalam | 28 | 100% | 78 | 71 | 2.0 | 0 |
| Hindi | 28 | 100% | 78 | 74 | 1.3 | 0 |
| Konkani | 28 | 100% | 76 | 67 | 1.6 | 0 |
| Tulu (Kannada script) | 28 | 100% | 80 | 67 | 1.4 | 0 |

Overall: 112 of 112 distinct translations kept every time (100%), in 4 languages; the Tulu row repeats Kannada's, because Sarvam has no Tulu model and Tulu speakers get the Kannada text. 0 requests failed after retries (the app sends English in that case).

Lowest back-translation scores (for the native-speaker check):

- Kannada, course_pelvis (chrF 67): "Radiation Therapy Department: Your radiation treatment will begin on Monday, November 2nd. Please arrive at 17:56. After the first day, please arrive at 16:26 for each treatment day. This time will not change until your course is completed. Please drink water as instructed by the staff before arriving."
- Tulu, course_pelvis (chrF 67): "Radiation Therapy Department: Your radiation treatment will begin on Monday, November 2nd. Please arrive at 17:56. After the first day, please arrive at 16:26 for each treatment day. This time will not change until your course is completed. Please drink water as instructed by the staff before arriving."
- Kannada, course_pelvis (chrF 67): "Radiation Therapy Department: Your radiation treatment will begin on Monday, November 2nd. Please arrive at 16:39. After the first day, please arrive at 15:54 for each treatment day. This time will not change until your course is completed. Please drink water as instructed by the staff before arriving."

## Plain-language explanations (Sarvam-105B)

20 synthetic plans (random needs, reasons, first-day and standing times). The app rejects an answer that mentions a time not in the facts and shows the engine's own reasons instead.

| Measure | Result |
|---|---:|
| Answers accepted by the time check | 20 of 20 (100%) |
| Answers with an invented time (rejected) | 0 |
| Empty answers or errors (fall back to the engine's reasons) | 0 |
| Accepted answers that state both come-at times | 16 |
| Median seconds per answer | 1.5 |

Sample accepted answer:

> Your first appointment is at 10:40, so treatment begins at 11:25 on 3 November and will finish before 17:00. Every later appointment is at 17:00, and you should arrive at 16:15 on the Versa HD. These slots leave a 30-minute gap for urgent palliative patients and keep an evening slot free of the queue.

## Still to do with people

`sarvam_translations_for_rating.csv` has every translation with its back-translation. Native speakers of Kannada, Tulu, Malayalam, Konkani and Hindi at the department rate each 1-5 (correct and natural for a patient). Messages below 4 get their English wording simplified before the pilot.
