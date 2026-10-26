"""CARE settings for the RAD-SMART demonstration server (deploy/azure).

Installed in the image as config/settings/radsmart_azure.py. Everything else
comes from the environment, as for any CARE deployment.
"""

from .production import *  # noqa: F403

# One container, no Celery worker: CARE's background tasks run in the request.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
