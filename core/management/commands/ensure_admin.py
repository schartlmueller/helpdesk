import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from tickets import maintenance
from tickets.models import Category

DEFAULT_CATEGORIES = ["Hardware", "Software", "Netzwerk", "Zugang & Konten", "Sonstiges"]


class Command(BaseCommand):
    help = "Legt beim ersten Start Administrator, Standard-Kategorien und Feiertage an."

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(is_superuser=True).exists():
            username = os.environ.get("ADMIN_USER", "admin")
            password = os.environ.get("ADMIN_PASSWORD", "admin")
            email = os.environ.get("ADMIN_EMAIL", "")
            User.objects.create_superuser(username, email, password)
            self.stdout.write(f"Administrator '{username}' angelegt.")
        if not Category.objects.exists():
            Category.objects.bulk_create(Category(name=n) for n in DEFAULT_CATEGORIES)
            self.stdout.write("Standard-Kategorien angelegt.")
        added = maintenance.ensure_holidays()
        if added:
            self.stdout.write(f"{added} Feiertage eingetragen.")
