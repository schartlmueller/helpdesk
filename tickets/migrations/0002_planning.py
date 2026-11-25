import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import tickets.models


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlannerProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("daily_hours", models.DecimalField(decimal_places=2, default=8, max_digits=4, verbose_name="Verplanbare Stunden pro Tag")),
                ("calendar_token", models.CharField(default=tickets.models.generate_calendar_token, editable=False, max_length=64, unique=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="planner_profile", to=settings.AUTH_USER_MODEL, verbose_name="Bearbeiter")),
            ],
            options={
                "verbose_name": "Planungsprofil",
                "verbose_name_plural": "Planungsprofile",
            },
        ),
        migrations.CreateModel(
            name="Absence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField(verbose_name="Von")),
                ("end_date", models.DateField(verbose_name="Bis")),
                ("reason", models.CharField(blank=True, max_length=100, verbose_name="Grund")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="absences", to=settings.AUTH_USER_MODEL, verbose_name="Bearbeiter")),
            ],
            options={
                "verbose_name": "Abwesenheit",
                "verbose_name_plural": "Abwesenheiten",
                "ordering": ["start_date"],
            },
        ),
        migrations.CreateModel(
            name="RecurringTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Betreff")),
                ("description", models.TextField(verbose_name="Beschreibung")),
                ("priority", models.CharField(choices=[("low", "Niedrig"), ("normal", "Normal"), ("high", "Hoch"), ("urgent", "Dringend")], default="normal", max_length=20, verbose_name="Priorität")),
                ("estimated_minutes", models.PositiveIntegerField(blank=True, null=True, verbose_name="Geplanter Aufwand (Minuten)")),
                ("interval", models.CharField(choices=[("daily", "Jeden Arbeitstag"), ("weekly", "Wöchentlich"), ("biweekly", "Alle zwei Wochen"), ("monthly", "Monatlich"), ("quarterly", "Vierteljährlich"), ("halfyearly", "Halbjährlich"), ("yearly", "Jährlich")], default="monthly", max_length=20, verbose_name="Wiederholung")),
                ("next_run", models.DateField(help_text="An diesem Tag ist das nächste Ticket eingeplant.", verbose_name="Nächster Termin")),
                ("lead_days", models.PositiveSmallIntegerField(default=0, help_text="Das Ticket wird so viele Tage vor dem Termin angelegt.", verbose_name="Vorlauf (Tage)")),
                ("anchor_day", models.PositiveSmallIntegerField(blank=True, editable=False, null=True)),
                ("active", models.BooleanField(default=True, verbose_name="Aktiv")),
                ("last_created_at", models.DateTimeField(blank=True, null=True, verbose_name="Zuletzt angelegt")),
                ("assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recurring_assigned", to=settings.AUTH_USER_MODEL, verbose_name="Bearbeiter")),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="tickets.category", verbose_name="Kategorie")),
                ("requester", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recurring_requested", to=settings.AUTH_USER_MODEL, verbose_name="Gemeldet von")),
                ("team", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="tickets.team", verbose_name="Team")),
            ],
            options={
                "verbose_name": "Wiederkehrendes Ticket",
                "verbose_name_plural": "Wiederkehrende Tickets",
                "ordering": ["next_run", "title"],
            },
        ),
    ]
