import datetime as dt

from rest_framework import serializers

from radsmart.config import DEPARTMENT, GAP_CATEGORIES, PATTERNS, TECHNIQUES, fmt

from care_radsmart.engine import CHECKLIST, IMAGING, LANGUAGES, MOBILITY, SITES, flags
from care_radsmart.models import Course, Machine, SlotRequest, Triage

CHECK_KEYS = {item["key"] for group in ("hard", "soft") for item in CHECKLIST[group]}


def to_minutes(value) -> int | None:
    """'HH:MM' -> minutes after midnight; the day runs past midnight, so 00:00-05:59 is 24:00-29:59."""
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    try:
        h, m = str(value).split(":")
        minutes = int(h) * 60 + int(m)
    except ValueError as exc:
        raise serializers.ValidationError("Use HH:MM") from exc
    if not 0 <= minutes < 1440:
        raise serializers.ValidationError("Use a time between 00:00 and 23:59")
    return minutes + 1440 if minutes < 6 * 60 else minutes


class ClockField(serializers.Field):
    def to_representation(self, value):
        return None if value is None else fmt(value)

    def to_internal_value(self, data):
        return to_minutes(data)


class MachineSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="external_id", read_only=True)

    class Meta:
        model = Machine
        fields = ("id", "code", "name", "status", "status_since", "expected_back", "status_note")


class CourseSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="external_id", read_only=True)
    patient = serializers.UUIDField(source="patient.external_id", read_only=True)
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    preferred_time = ClockField(required=False, allow_null=True)
    earliest_start = ClockField(required=False, allow_null=True)
    latest_end = ClockField(required=False, allow_null=True)
    approved_by = serializers.CharField(source="approved_by.username", read_only=True, default=None)
    flags = serializers.SerializerMethodField()
    technique_label = serializers.SerializerMethodField()
    sessions_done = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ("id", "patient", "patient_name", "hospital_number", "diagnosis", "total_dose_gy",
                  "fractions", "pattern", "technique", "technique_label", "site", "mobility", "imaging",
                  "machines", "checklist", "preferred_time", "earliest_start", "latest_end", "gap_category",
                  "language", "start_date", "status", "approved_by", "approved_at", "proposal", "first",
                  "slots", "minutes", "first_minutes", "dates", "note", "demo", "flags", "sessions_done",
                  "created_date", "modified_date")
        read_only_fields = ("status", "approved_by", "approved_at", "proposal", "first", "slots", "minutes",
                            "first_minutes", "dates", "demo")

    def get_flags(self, obj):
        return flags(obj)

    def get_technique_label(self, obj):
        return TECHNIQUES.get(obj.technique, {}).get("label", obj.technique)

    def get_sessions_done(self, obj):
        return obj.sessions.filter(status="done").count()

    def validate_technique(self, v):
        if v not in TECHNIQUES:
            raise serializers.ValidationError(f"Choose one of {', '.join(TECHNIQUES)}")
        return v

    def validate_site(self, v):
        if v not in SITES:
            raise serializers.ValidationError("Unknown site")
        return v

    def validate_pattern(self, v):
        if v not in PATTERNS:
            raise serializers.ValidationError("Unknown treatment days")
        return v

    def validate_mobility(self, v):
        if v not in MOBILITY:
            raise serializers.ValidationError("Unknown mobility")
        return v

    def validate_imaging(self, v):
        if v not in IMAGING:
            raise serializers.ValidationError("Unknown imaging")
        return v

    def validate_language(self, v):
        if v not in LANGUAGES:
            raise serializers.ValidationError("Unknown language")
        return v

    def validate_fractions(self, v):
        if not 1 <= v <= 60:
            raise serializers.ValidationError("Between 1 and 60 fractions")
        return v

    def validate_total_dose_gy(self, v):
        if not 0 < v <= 100:
            raise serializers.ValidationError("Between 0 and 100 Gy")
        return v

    def validate_gap_category(self, v):
        if v not in GAP_CATEGORIES:
            raise serializers.ValidationError("Category 1, 2 or 3")
        return v

    def validate_machines(self, v):
        bad = [m for m in v if m not in DEPARTMENT["machines"]]
        if bad or not isinstance(v, list):
            raise serializers.ValidationError(f"Unknown machine {bad}")
        return v

    def validate_checklist(self, v):
        if not isinstance(v, dict) or any(k not in CHECK_KEYS for k in v):
            raise serializers.ValidationError("Unknown checklist item")
        return {k: bool(x) for k, x in v.items()}

    def validate_start_date(self, v):
        if v.weekday() >= 5:
            raise serializers.ValidationError("Choose a working day")
        return v

    def validate(self, attrs):
        tech = attrs.get("technique", getattr(self.instance, "technique", None))
        machines = attrs.get("machines", getattr(self.instance, "machines", None)) or []
        if tech and machines and not set(machines) & set(TECHNIQUES[tech]["machines"]):
            raise serializers.ValidationError({"machines": "This technique cannot be delivered on those machines"})
        ck = attrs.get("checklist", getattr(self.instance, "checklist", {}) or {})
        lo = attrs.get("earliest_start", getattr(self.instance, "earliest_start", None))
        hi = attrs.get("latest_end", getattr(self.instance, "latest_end", None))
        if ck.get("time_window") and lo is None and hi is None:
            raise serializers.ValidationError({"earliest_start": "Give the time window"})
        if lo is not None and hi is not None and hi - lo < 30:
            raise serializers.ValidationError({"latest_end": "The window must be at least 30 minutes"})
        if ck.get("preferred") and attrs.get("preferred_time", getattr(self.instance, "preferred_time", None)) is None:
            raise serializers.ValidationError({"preferred_time": "Give the preferred time"})
        if ck.get("gap_sensitive"):
            attrs["gap_category"] = 1
        return attrs


class TriageSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="external_id", read_only=True)
    machine = serializers.CharField(source="machine.code", read_only=True)
    decided_by = serializers.CharField(source="decided_by.username", read_only=True, default=None)

    class Meta:
        model = Triage
        fields = ("id", "machine", "date", "fault_start", "expected_minutes", "proposal", "status",
                  "decided_by", "decided_at", "note", "created_date")


class SlotRequestSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="external_id", read_only=True)
    course = serializers.UUIDField(source="course.external_id", read_only=True)
    patient_name = serializers.CharField(source="course.patient.name", read_only=True)
    hospital_number = serializers.CharField(source="course.hospital_number", read_only=True)
    current = serializers.SerializerMethodField()
    wanted = ClockField()
    decided_by = serializers.CharField(source="decided_by.username", read_only=True, default=None)

    class Meta:
        model = SlotRequest
        fields = ("id", "course", "patient_name", "hospital_number", "current", "from_date", "wanted",
                  "reason", "proposal", "status", "decided_by", "decided_at", "created_date")

    def get_current(self, obj):
        slots = obj.course.slots or []
        return fmt(slots[-1]["start"]) if slots else None


def parse_date(value, default=None) -> dt.date:
    if not value:
        return default
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise serializers.ValidationError({"date": "Use YYYY-MM-DD"}) from exc
