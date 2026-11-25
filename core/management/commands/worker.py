import time
import traceback

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from tickets import maintenance
from tickets.mail_fetch import fetch_mail


class Command(BaseCommand):
    help = (
        "Hintergrunddienst: ruft E-Mails ab, eskaliert überfällige Tickets, legt wiederkehrende Tickets an, "
        "stoppt vergessene Uhren und löscht Tickets nach Ablauf der Aufbewahrungsfrist."
    )

    def handle(self, *args, **options):
        if not settings.IMAP_HOST:
            self.stdout.write("E-Mail-Eingang ist nicht eingerichtet (IMAP_HOST fehlt).")
        last_housekeeping = 0.0
        last_purge = 0.0
        while True:
            close_old_connections()
            now = time.monotonic()
            if settings.IMAP_HOST:
                self.run(lambda: fetch_mail(self.stdout.write))
            if now - last_housekeeping >= 300 or not last_housekeeping:
                last_housekeeping = now
                self.run(maintenance.escalate_overdue, "Tickets eskaliert")
                self.run(maintenance.stop_stale_timers, "vergessene Uhren gestoppt")
                self.run(maintenance.create_recurring_tickets, "wiederkehrende Tickets angelegt")
                self.run(maintenance.process_follow_ups, "Wiedervorlagen gemeldet")
                self.run(maintenance.remind_and_close, "Tickets erinnert oder geschlossen")
            if now - last_purge >= 86400 or not last_purge:
                last_purge = now
                self.run(maintenance.ensure_holidays, "Feiertage eingetragen")
                self.run(maintenance.purge_old_tickets, "alte Tickets gelöscht")
            time.sleep(settings.MAIL_POLL_SECONDS)

    def run(self, job, label=None):
        try:
            count = job()
            if label and count:
                self.stdout.write(f"{count} {label}.")
        except Exception:
            self.stderr.write(traceback.format_exc())
