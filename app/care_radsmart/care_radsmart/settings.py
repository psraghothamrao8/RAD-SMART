"""Plugin settings.

Resolution order for every key:
    settings.PLUGIN_CONFIGS["care_radsmart"][key]  →  environment variable  →  DEFAULTS[key]

The environment cast is inferred from the *type of the default*, so every default must be
correctly typed (use "" / 0 / False, never None).
"""

from typing import Any

import environ
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed
from django.dispatch import receiver
from rest_framework.settings import perform_import

from care_radsmart.apps import PLUGIN_NAME

env = environ.Env()


class PluginSettings:  # pragma: no cover
    """Access plugin settings as attributes.

    >>> from care_radsmart.settings import plugin_settings
    >>> plugin_settings.RADSMART_ENABLED
    """

    def __init__(
        self,
        plugin_name: str = None,
        defaults: dict | None = None,
        import_strings: set | None = None,
        required_settings: set | None = None,
    ) -> None:
        if not plugin_name:
            raise ValueError("Plugin name must be provided")
        self.plugin_name = plugin_name
        self.defaults = defaults or {}
        self.import_strings = import_strings or set()
        self.required_settings = required_settings or set()
        self._cached_attrs = set()
        self.validate()

    def __getattr__(self, attr) -> Any:
        if attr not in self.defaults:
            raise AttributeError("Invalid setting: '%s'" % attr)

        val = self.defaults[attr]
        try:
            val = self.user_settings[attr]
        except KeyError:
            try:
                val = env(attr, cast=type(val))
            except environ.ImproperlyConfigured:
                pass

        if attr in self.import_strings:
            val = perform_import(val, attr)

        self._cached_attrs.add(attr)
        setattr(self, attr, val)
        return val

    @property
    def user_settings(self) -> dict:
        if not hasattr(self, "_user_settings"):
            self._user_settings = getattr(settings, "PLUGIN_CONFIGS", {}).get(
                self.plugin_name, {}
            )
        return self._user_settings

    def validate(self) -> None:
        for setting in self.required_settings:
            if not getattr(self, setting):
                raise ImproperlyConfigured(
                    f'The "{setting}" setting is required. '
                    f'Set it in the environment or in the {PLUGIN_NAME} plugin config.'
                )

    def reload(self) -> None:
        for attr in self._cached_attrs:
            delattr(self, attr)
        self._cached_attrs.clear()
        if hasattr(self, "_user_settings"):
            delattr(self, "_user_settings")


# Credentials without which the plugin cannot function. A misconfigured deploy fails at boot.
REQUIRED_SETTINGS: set[str] = set()

DEFAULTS = {
    "RADSMART_ENABLED": True,
    # Allow POST /api/care_radsmart/demo/seed/ (synthetic patients and courses for a
    # demonstration facility). Keep False anywhere real patients are treated.
    "RADSMART_DEMO": False,
    # Machines created for a facility the first time RAD-SMART is opened there:
    # "CODE:Label" pairs, comma separated. Codes match the engine's machine names.
    "RADSMART_MACHINES": "VERSA:Versa HD",
    # Public holidays (ISO dates, comma separated): no treatment is planned on them.
    "RADSMART_HOLIDAYS": "",
    # Sarvam AI (translation, voice notes, plain-language explanations). Without a key,
    # patients get the English message and staff see the engine's own reasons.
    "SARVAM_API_KEY": "",
    "RADSMART_SARVAM_TIMEOUT": 25,
    # The name patients see on their messages and page.
    "RADSMART_DEPARTMENT": "Radiotherapy department",
    # Address patients' phones reach this server on (e.g. https://care.example.org). When
    # empty, links use the address of the request that created them.
    "RADSMART_PUBLIC_URL": "",
}

plugin_settings = PluginSettings(
    PLUGIN_NAME, defaults=DEFAULTS, required_settings=REQUIRED_SETTINGS
)


@receiver(setting_changed)
def reload_plugin_settings(*args, **kwargs) -> None:
    if kwargs["setting"] == "PLUGIN_CONFIGS":
        plugin_settings.reload()
