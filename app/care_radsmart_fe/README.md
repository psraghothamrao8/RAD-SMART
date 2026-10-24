# care_radsmart_fe

RAD-SMART's frontend plugin for [care_fe](https://github.com/ohcnetwork/care_fe), loaded at runtime
through Vite Module Federation. It is a separate build and never imports from `care_fe`; React,
React Query, raviger, react-i18next and sonner are shared with the host.

| Route (in a facility) | Page |
|---|---|
| `/facility/:id/radsmart` | Today: machines, rule check, timeline, patients (arrived, in room, out) |
| `…/radsmart/courses` | Courses, and slot-change requests waiting for a decision |
| `…/radsmart/courses/new` | Intake: prescription and the priority checklist |
| `…/radsmart/courses/:courseId` | RAD-SMART's proposal, approval, slots, slot change, sessions |
| `…/radsmart/breakdown` | Report a breakdown, review and approve RAD-SMART's response |
| `…/radsmart/insights` | Measured waits against the baseline and target |

Extension points: `PatientInfoCardQuickActions` (the **RADSMART** button on the visit page),
`PatientHomeActions` and `FacilityHomeActions`. The facility menu gets a **RAD-SMART** item.

```bash
npm install
npm run dev        # watch build + preview on :19102
npm run typecheck
npm run strings    # rebuild public/locale/en.json from the tr("key", "English") calls
```

Setup with CARE: see [`../README.md`](../README.md).
