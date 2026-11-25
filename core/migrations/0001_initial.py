import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, unique=True, verbose_name="Name")),
                ("email_domains", models.TextField(blank=True, help_text="z. B. firma.at, tochter.at. Neue Melder mit einer dieser Domains werden automatisch zugeordnet.", verbose_name="E-Mail-Domains")),
                ("notes", models.TextField(blank=True, verbose_name="Notizen")),
                ("active", models.BooleanField(default=True, verbose_name="Aktiv")),
            ],
            options={
                "verbose_name": "Organisation",
                "verbose_name_plural": "Organisationen",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Holiday",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(unique=True, verbose_name="Datum")),
                ("name", models.CharField(max_length=100, verbose_name="Bezeichnung")),
            ],
            options={
                "verbose_name": "Feiertag",
                "verbose_name_plural": "Feiertage",
                "ordering": ["date"],
            },
        ),
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_contact", models.BooleanField(default=False, help_text="Sieht alle Tickets der Organisation, nicht nur die eigenen.", verbose_name="Ansprechpartner")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="core.organization", verbose_name="Organisation")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="membership", to=settings.AUTH_USER_MODEL, verbose_name="Benutzer")),
            ],
            options={
                "verbose_name": "Zuordnung",
                "verbose_name_plural": "Zuordnungen",
            },
        ),
        migrations.CreateModel(
            name="Announcement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Überschrift")),
                ("text", models.TextField(blank=True, verbose_name="Text")),
                ("level", models.CharField(choices=[("info", "Hinweis"), ("warning", "Störung"), ("critical", "Schwere Störung")], default="warning", max_length=20, verbose_name="Art")),
                ("starts_at", models.DateTimeField(default=django.utils.timezone.now, verbose_name="Anzeigen ab")),
                ("ends_at", models.DateTimeField(blank=True, help_text="Leer = bis sie beendet wird.", null=True, verbose_name="Anzeigen bis")),
                ("active", models.BooleanField(default=True, verbose_name="Aktiv")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(blank=True, help_text="Leer lassen, damit alle die Meldung sehen.", null=True, on_delete=django.db.models.deletion.CASCADE, to="core.organization", verbose_name="Nur für Organisation")),
            ],
            options={
                "verbose_name": "Störungsmeldung",
                "verbose_name_plural": "Störungsmeldungen",
                "ordering": ["-starts_at"],
            },
        ),
    ]
