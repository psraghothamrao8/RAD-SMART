from django.apps import AppConfig

PLUGIN_NAME = "care_radsmart"


class CareRadsmartConfig(AppConfig):
    name = PLUGIN_NAME
    verbose_name = "RAD-SMART"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from care.security.permissions.base import PermissionController

        # Importing the module registers RadsmartAccess with the AuthorizationController.
        from care_radsmart.security import RadsmartPermissions  # noqa: F401

        PermissionController.register_permission_handler(RadsmartPermissions)
