# Run in the CARE backend shell: prints the values that scripts/record.mjs needs.
#   ./.agent/compose.sh exec -T backend python manage.py shell < scripts/ids.py
# The recording patient is the last of CARE's fixture patients with an encounter at the fixture facility
# (the fixtures give them new random names every time they are loaded).
from care.emr.models import Encounter
from care.facility.models import Facility

facility = Facility.objects.get(name="FACILITY WITH PATIENTS")
encounter = (
    Encounter.objects.filter(facility=facility)
    .exclude(patient__name__startswith="Demo patient")
    .order_by("-created_date")
    .first()
)
print(f"FACILITY={facility.external_id}")
print(f"PATIENT={encounter.patient.external_id}")
print(f"ENCOUNTER={encounter.external_id}")
print(f"PATIENT_NAME={encounter.patient.name}")
