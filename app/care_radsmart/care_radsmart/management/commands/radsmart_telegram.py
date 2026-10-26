"""The Telegram bot (demonstrations only; real use sends on WhatsApp).

    python manage.py radsmart_telegram --info
    python manage.py radsmart_telegram --poll                         # a local server Telegram cannot reach
    python manage.py radsmart_telegram --webhook https://care.example.org
    python manage.py radsmart_telegram --no-webhook

The token and the webhook secret come from RADSMART_TELEGRAM_TOKEN and
RADSMART_TELEGRAM_SECRET, and are never printed.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from care_radsmart import telegram
from care_radsmart.settings import plugin_settings


class Command(BaseCommand):
    help = "Set or remove the Telegram webhook, or poll Telegram for updates"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--info", action="store_true", help="the bot's name and its webhook")
        group.add_argument("--poll", action="store_true", help="ask Telegram for updates until stopped")
        group.add_argument("--webhook", metavar="PUBLIC_URL", help="have Telegram post updates to this server")
        group.add_argument("--no-webhook", action="store_true", help="remove the webhook (needed before --poll)")

    def handle(self, *args, **opts):
        if not telegram.enabled():
            raise CommandError("RADSMART_TELEGRAM_TOKEN is not set.")
        try:
            if opts["info"]:
                hook = telegram.call("getWebhookInfo")
                self.stdout.write(f"bot: @{telegram.username()}\nwebhook: {hook.get('url') or '(none)'}"
                                  f"\npending updates: {hook.get('pending_update_count', 0)}"
                                  + (f"\nlast error: {hook['last_error_message']}" if hook.get("last_error_message") else ""))
            elif opts["webhook"]:
                if not plugin_settings.RADSMART_TELEGRAM_SECRET:
                    raise CommandError("Set RADSMART_TELEGRAM_SECRET first.")
                url = opts["webhook"].rstrip("/") + "/api/care_radsmart/telegram/"
                telegram.call("setWebhook", {"url": url, "secret_token": str(plugin_settings.RADSMART_TELEGRAM_SECRET),
                                             "allowed_updates": ["message", "callback_query"],
                                             "drop_pending_updates": True})
                self.stdout.write(self.style.SUCCESS(f"Telegram now posts to {url}"))
            elif opts["no_webhook"]:
                telegram.call("deleteWebhook")
                self.stdout.write(self.style.SUCCESS("Webhook removed."))
            else:
                self.poll()
        except telegram.TelegramError as exc:
            raise CommandError(str(exc)) from exc

    def poll(self):
        self.stdout.write(f"Polling for @{telegram.username()} (Ctrl+C stops)")
        offset = None
        while True:
            updates = telegram.call("getUpdates", {"offset": offset, "timeout": 50,
                                                   "allowed_updates": ["message", "callback_query"]}, timeout=60)
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    telegram.handle(update)
                except Exception as exc:     # one bad update must not stop the bot
                    self.stderr.write(f"update {update['update_id']}: {exc!r}")
                finally:
                    close_old_connections()
