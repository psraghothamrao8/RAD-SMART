"""CARE's WSGI application, with every URL and view loaded at once instead of on
a worker's first request, which took about 3 s on half a vCPU. gunicorn runs it
with --preload, so this happens once, before the workers are forked."""

from django.urls import get_resolver

from config.wsgi import application  # noqa: F401  (sets Django up)

get_resolver().url_patterns
