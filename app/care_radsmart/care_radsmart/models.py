"""RAD-SMART data in CARE.

Only foreign keys into core (facility, patient, user); core never refers to
these tables. Times of day are minutes after midnight in the facility's time
zone, on the engine's 2-minute grid; the day runs past midnight (25:00 = 01:00).
"""

from django.conf import settings
from django.db import models

from care.emr.models.base import EMRBaseModel


class Machine(EMRBaseModel):
    STATUS = (("online", "Online"), ("offline", "Offline"))

    facility = models.ForeignKey("facility.Facility", on_delete=models.CASCADE,
                                 related_name="radsmart_machines")
    code = models.CharField(max_length=32)            # engine name, e.g. VERSA
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=16, choices=STATUS, default="online")
    status_since = models.DateTimeField(null=True, blank=True)
    expected_back = models.DateTimeField(null=True, blank=True)
    status_note = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["facility", "code"])]

    def __str__(self):
        return f"{self.name} ({self.code})"


class MachineEvent(EMRBaseModel):
    """Every status change a technologist records (the downtime log)."""

    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=16, choices=Machine.STATUS)
    at = models.DateTimeField()
    expected_minutes = models.PositiveIntegerField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True, default="")


class Course(EMRBaseModel):
    """A radiotherapy course as the oncologist approved it, and the machine time
    RAD-SMART promised to it (new-start slot and standing slot)."""

    STATUS = (("draft", "Draft"), ("approved", "Approved"), ("completed", "Completed"),
              ("cancelled", "Cancelled"))

    facility = models.ForeignKey("facility.Facility", on_delete=models.CASCADE,
                                 related_name="radsmart_courses")
    patient = models.ForeignKey("emr.Patient", on_delete=models.CASCADE,
                                related_name="radsmart_courses")
    hospital_number = models.CharField(max_length=64, blank=True, default="")
    diagnosis = models.CharField(max_length=255)
    total_dose_gy = models.DecimalField(max_digits=6, decimal_places=2)
    fractions = models.PositiveIntegerField()
    pattern = models.CharField(max_length=16, default="daily")
    technique = models.CharField(max_length=16)
    site = models.CharField(max_length=16)
    mobility = models.CharField(max_length=16, default="walking")
    imaging = models.CharField(max_length=8, default="kv")
    machines = models.JSONField(default=list)          # machine codes the plan can be delivered on
    checklist = models.JSONField(default=dict)         # ticked hard and soft constraints
    preferred_time = models.IntegerField(null=True, blank=True)
    earliest_start = models.IntegerField(null=True, blank=True)
    latest_end = models.IntegerField(null=True, blank=True)
    gap_category = models.PositiveSmallIntegerField(default=2)
    language = models.CharField(max_length=32, default="Kannada")
    start_date = models.DateField()
    status = models.CharField(max_length=16, choices=STATUS, default="draft")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    proposal = models.JSONField(default=dict)          # the allocation shown to the doctor
    first = models.JSONField(default=dict)             # {"machine", "date", "start", "minutes"}
    slots = models.JSONField(default=list)             # [{"from", "machine", "start", "start2"}]
    minutes = models.FloatField(default=0.0)           # reserved minutes of a routine fraction
    first_minutes = models.FloatField(default=0.0)
    dates = models.JSONField(default=list)             # treatment dates, ISO
    note = models.TextField(blank=True, default="")
    demo = models.BooleanField(default=False)          # synthetic demonstration course
    patient_token = models.CharField(max_length=40, blank=True, default="", db_index=True)  # the patient's page link
    checkin_code = models.CharField(max_length=8, blank=True, default="")  # shown as a QR code at reception

    class Meta:
        indexes = [models.Index(fields=["facility", "status"])]


class Session(EMRBaseModel):
    """One fraction on one day: the plan, and what actually happened."""

    STATUS = (("scheduled", "Scheduled"), ("arrived", "Arrived"), ("in_room", "In the room"),
              ("done", "Done"), ("sent_home", "Sent home"), ("postponed", "Postponed"),
              ("missed", "Missed"), ("cancelled", "Cancelled"))
    KIND = (("new_start", "New start"), ("routine", "Standing slot"), ("moved", "Moved for one day"),
            ("added", "Added at the end of the course"))

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sessions")
    facility = models.ForeignKey("facility.Facility", on_delete=models.CASCADE,
                                 related_name="radsmart_sessions")
    date = models.DateField(db_index=True)
    fraction_no = models.PositiveIntegerField()
    kind = models.CharField(max_length=16, choices=KIND, default="routine")
    machine = models.CharField(max_length=32)
    planned_start = models.IntegerField()              # the slot the patient was given
    planned_minutes = models.FloatField()
    today_start = models.IntegerField(null=True, blank=True)   # changed for today only (breakdown)
    status = models.CharField(max_length=16, choices=STATUS, default="scheduled")
    arrived_at = models.DateTimeField(null=True, blank=True)
    in_room_at = models.DateTimeField(null=True, blank=True)
    out_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["facility", "date"]), models.Index(fields=["course", "date"])]

    @property
    def start(self) -> int:
        return self.today_start if self.today_start is not None else self.planned_start


class DayPlan(EMRBaseModel):
    """A day's plan as approved (the checker's result is kept with it)."""

    STATUS = (("draft", "Draft"), ("approved", "Approved"))

    facility = models.ForeignKey("facility.Facility", on_delete=models.CASCADE,
                                 related_name="radsmart_plans")
    date = models.DateField()
    status = models.CharField(max_length=16, choices=STATUS, default="draft")
    check_result = models.JSONField(default=dict)
    summary = models.JSONField(default=dict)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)


class Triage(EMRBaseModel):
    """RAD-SMART's proposed response to a breakdown, and the human decision."""

    STATUS = (("proposed", "Proposed"), ("approved", "Approved"), ("rejected", "Rejected"),
              ("superseded", "Superseded"))

    facility = models.ForeignKey("facility.Facility", on_delete=models.CASCADE,
                                 related_name="radsmart_triages")
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="triages")
    event = models.ForeignKey(MachineEvent, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField()
    fault_start = models.IntegerField()
    expected_minutes = models.PositiveIntegerField()
    proposal = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=STATUS, default="proposed")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True, default="")


class SlotRequest(EMRBaseModel):
    """A patient's request for another standing time, and the decision."""

    STATUS = (("proposed", "Proposed"), ("approved", "Approved"), ("rejected", "Rejected"))

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="slot_requests")
    from_date = models.DateField()
    wanted = models.IntegerField()
    reason = models.CharField(max_length=500, blank=True, default="")
    proposal = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=STATUS, default="proposed")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)


class Message(EMRBaseModel):
    """A message to a patient: drafted by RAD-SMART after a person approved the
    change, translated into the patient's language, and sent by staff."""

    KIND = (("course", "Course approved"), ("slot", "Standing time changed"), ("breakdown", "Breakdown"))
    STATUS = (("to_send", "To send"), ("sent", "Sent"), ("cancelled", "Cancelled"))
    LOCAL = (("pending", "Translating"), ("ok", "Translated"), ("english", "English only"),
             ("failed", "Translation failed"))

    facility = models.ForeignKey("facility.Facility", on_delete=models.CASCADE,
                                 related_name="radsmart_messages")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="messages")
    session = models.ForeignKey(Session, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    date = models.DateField(db_index=True)
    kind = models.CharField(max_length=16, choices=KIND)
    action = models.CharField(max_length=32, blank=True, default="")   # the breakdown action, if any
    text = models.TextField()                                          # English, as drafted
    language = models.CharField(max_length=32)
    local_text = models.TextField(blank=True, default="")
    local_status = models.CharField(max_length=16, choices=LOCAL, default="pending")
    local_note = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS, default="to_send")
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                blank=True, related_name="+")
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["facility", "date"])]


class PatientReply(EMRBaseModel):
    """What a patient tells the department from their page."""

    KIND = (("on_way", "On the way"), ("late", "Running late"), ("not_today", "Cannot come today"),
            ("other_time", "Asks for another time"))
    STATUS = (("open", "Open"), ("done", "Done"))

    facility = models.ForeignKey("facility.Facility", on_delete=models.CASCADE,
                                 related_name="radsmart_replies")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="replies")
    session = models.ForeignKey(Session, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    date = models.DateField(db_index=True)
    kind = models.CharField(max_length=16, choices=KIND)
    minutes = models.PositiveIntegerField(null=True, blank=True)       # how late
    wanted = models.IntegerField(null=True, blank=True)                # the time asked for
    reason = models.CharField(max_length=300, blank=True, default="")
    slot_request = models.ForeignKey(SlotRequest, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+")
    status = models.CharField(max_length=16, choices=STATUS, default="open")
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name="+")
    handled_at = models.DateTimeField(null=True, blank=True)
