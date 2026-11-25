from django.conf import settings
from django.core.management.base import BaseCommand

from tickets.mail_fetch import fetch_mail


class Command(BaseCommand):
    help = "Ruft das Postfach einmal ab (zum Testen; im Betrieb erledigt das der Dienst 'worker')."

    def handle(self, *args, **options):
        if not settings.IMAP_HOST:
            self.stdout.write("IMAP_HOST ist nicht gesetzt.")
            return
        count = fetch_mail(self.stdout.write)
        self.stdout.write(f"{count} E-Mail(s) zu Tickets verarbeitet.")
