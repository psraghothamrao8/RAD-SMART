# Run in the CARE backend shell before a recording take: cancel the recording patient's earlier
# courses and their unsent messages, so the take can start a new course. The recording patient is
# the one scripts/ids.py prints.
#   ./.agent/compose.sh exec -T backend python manage.py shell < scripts/prep_take.py
from care.emr.models import Encounter
from care.facility.models import Facility
from care_radsmart.models import Course, Message, PatientReply, SlotRequest

patient = (
    Encounter.objects.filter(facility=Facility.objects.get(name="FACILITY WITH PATIENTS"))
    .exclude(patient__name__startswith="Demo patient")
    .order_by("-created_date")
    .first()
    .patient
)
qs = Course.objects.filter(patient=patient, demo=False).exclude(status="cancelled")
for c in qs:
    c.sessions.filter(status="scheduled").update(status="cancelled")
    c.status = "cancelled"
    c.save()
n = Message.objects.filter(course__patient=patient, status="to_send").update(status="cancelled")
r = PatientReply.objects.filter(course__patient=patient, status="open").update(status="done")
s = SlotRequest.objects.filter(course__patient=patient, status="proposed").update(status="rejected")
print("cancelled courses", qs.count(), "messages", n, "replies", r, "requests", s)
