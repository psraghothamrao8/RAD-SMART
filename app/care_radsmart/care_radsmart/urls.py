"""Mounted by CARE at /api/care_radsmart/ (the PLUGIN_APPS loop in config/urls.py)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from care_radsmart.patient import PatientAudio, PatientPage
from care_radsmart.telegram import Webhook as TelegramWebhook
from care_radsmart.tryout import TryEnter, TryPage, TryPatient, TryRestart, TrySignIn
from care_radsmart.viewsets import (CheckInView, ConfigView, CourseViewSet, DayView, DemoSeedView, InsightsView,
                                    MachineViewSet, MessageViewSet, PatientSearchView, ReplyViewSet, SessionViewSet,
                                    SlotRequestViewSet, TriageViewSet)

router = DefaultRouter()
router.register("machines", MachineViewSet, basename="radsmart-machine")
router.register("courses", CourseViewSet, basename="radsmart-course")
router.register("sessions", SessionViewSet, basename="radsmart-session")
router.register("slot-requests", SlotRequestViewSet, basename="radsmart-slot-request")
router.register("triage", TriageViewSet, basename="radsmart-triage")
router.register("messages", MessageViewSet, basename="radsmart-message")
router.register("replies", ReplyViewSet, basename="radsmart-reply")

urlpatterns = [
    *router.urls,
    path("config/", ConfigView.as_view(), name="care_radsmart-config"),
    path("day/", DayView.as_view(), name="care_radsmart-day"),
    path("insights/", InsightsView.as_view(), name="care_radsmart-insights"),
    path("patients/", PatientSearchView.as_view(), name="care_radsmart-patients"),
    path("demo/seed/", DemoSeedView.as_view(), name="care_radsmart-demo-seed"),
    path("checkin/", CheckInView.as_view(), name="care_radsmart-checkin"),
    # The patient's own page: a private link, no login.
    path("p/<str:token>/", PatientPage.as_view(), name="care_radsmart-patient"),
    path("p/<str:token>/audio/<uuid:message>/", PatientAudio.as_view(), name="care_radsmart-patient-audio"),
    # Telegram's webhook (demonstrations only); it carries its own secret.
    path("telegram/", TelegramWebhook.as_view(), name="care_radsmart-telegram"),
    # The public demonstration's front door (RADSMART_OPEN_DEMO only).
    path("try/", TryPage.as_view(), name="care_radsmart-try"),
    path("try/restart/", TryRestart.as_view(), name="care_radsmart-try-restart"),
    path("try/patient/", TryPatient.as_view(), name="care_radsmart-try-patient"),
    path("try/signin/", TrySignIn.as_view(), name="care_radsmart-try-signin"),
    path("try/<str:role>/", TryEnter.as_view(), name="care_radsmart-try-enter"),
]
