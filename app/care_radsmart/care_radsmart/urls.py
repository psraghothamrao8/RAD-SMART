"""Mounted by CARE at /api/care_radsmart/ (the PLUGIN_APPS loop in config/urls.py)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from care_radsmart.viewsets import (ConfigView, CourseViewSet, DayView, DemoSeedView, InsightsView, MachineViewSet,
                                    PatientSearchView, SessionViewSet, SlotRequestViewSet, TriageViewSet)

router = DefaultRouter()
router.register("machines", MachineViewSet, basename="radsmart-machine")
router.register("courses", CourseViewSet, basename="radsmart-course")
router.register("sessions", SessionViewSet, basename="radsmart-session")
router.register("slot-requests", SlotRequestViewSet, basename="radsmart-slot-request")
router.register("triage", TriageViewSet, basename="radsmart-triage")

urlpatterns = [
    *router.urls,
    path("config/", ConfigView.as_view(), name="care_radsmart-config"),
    path("day/", DayView.as_view(), name="care_radsmart-day"),
    path("insights/", InsightsView.as_view(), name="care_radsmart-insights"),
    path("patients/", PatientSearchView.as_view(), name="care_radsmart-patients"),
    path("demo/seed/", DemoSeedView.as_view(), name="care_radsmart-demo-seed"),
]
