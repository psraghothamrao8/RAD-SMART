# care_radsmart

RAD-SMART's backend plugin for [CARE](https://github.com/ohcnetwork/care). It adds radiotherapy scheduling to a facility:

- **Course intake** by the oncologist, with a priority checklist of every hard rule and soft goal.
- **Standing slots**: the new-start slot (before 17:00) and one standing slot for the whole course, both allocated by the RAD-SMART engine.
- **Technologist board**: arrival, room-in and room-out times, and machine online or offline.
- **Breakdown triage**: overtime up to 60 minutes, then who is sent back, for a person to approve.
- **Slot-change requests** and **measured waits**.

The scheduling engine is the `radsmart` package in `../../poc`. See `../README.md` for setup.
