import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import tickets.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("projects", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Team",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="Name")),
                ("members", models.ManyToManyField(blank=True, related_name="helpdesk_teams", to=settings.AUTH_USER_MODEL, verbose_name="Mitglieder")),
            ],
            options={
                "verbose_name": "Team",
                "verbose_name_plural": "Teams",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="Name")),
                ("team", models.ForeignKey(blank=True, help_text="Neue Tickets dieser Kategorie gehen automatisch an dieses Team.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="categories", to="tickets.team", verbose_name="Zuständiges Team")),
            ],
            options={
                "verbose_name": "Kategorie",
                "verbose_name_plural": "Kategorien",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="CannedResponse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=100, verbose_name="Titel")),
                ("body", models.TextField(verbose_name="Text")),
            ],
            options={
                "verbose_name": "Textbaustein",
                "verbose_name_plural": "Textbausteine",
                "ordering": ["title"],
            },
        ),
        migrations.CreateModel(
            name="Ticket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Betreff")),
                ("description", models.TextField(verbose_name="Problembeschreibung")),
                ("status", models.CharField(choices=[("new", "Neu"), ("open", "In Bearbeitung"), ("waiting", "Wartet auf Rückmeldung"), ("resolved", "Gelöst"), ("closed", "Geschlossen")], default="new", max_length=20, verbose_name="Status")),
                ("priority", models.CharField(choices=[("low", "Niedrig"), ("normal", "Normal"), ("high", "Hoch"), ("urgent", "Dringend")], default="normal", max_length=20, verbose_name="Priorität")),
                ("cc", models.TextField(blank=True, help_text="Weitere E-Mail-Adressen, durch Komma getrennt. Sie erhalten alle Antworten.", verbose_name="In Kopie")),
                ("solution", models.TextField(blank=True, verbose_name="Lösung")),
                ("estimated_minutes", models.PositiveIntegerField(blank=True, null=True, verbose_name="Geplanter Aufwand (Minuten)")),
                ("planned_for", models.DateField(blank=True, null=True, verbose_name="Geplant für")),
                ("due_at", models.DateTimeField(blank=True, null=True, verbose_name="Fällig bis")),
                ("escalated_at", models.DateTimeField(blank=True, null=True, verbose_name="Eskaliert am")),
                ("resolved_at", models.DateTimeField(blank=True, null=True, verbose_name="Gelöst am")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Erstellt")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Geändert")),
                ("assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_tickets", to=settings.AUTH_USER_MODEL, verbose_name="Bearbeiter")),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tickets", to="tickets.category", verbose_name="Kategorie")),
                ("merged_into", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="merged_tickets", to="tickets.ticket", verbose_name="Zusammengeführt in")),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tickets", to="projects.project", verbose_name="Projekt")),
                ("requester", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="requested_tickets", to=settings.AUTH_USER_MODEL, verbose_name="Gemeldet von")),
                ("team", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tickets", to="tickets.team", verbose_name="Team")),
            ],
            options={
                "verbose_name": "Ticket",
                "verbose_name_plural": "Tickets",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Comment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField(verbose_name="Nachricht")),
                ("internal", models.BooleanField(default=False, verbose_name="Interne Notiz (für den Melder nicht sichtbar)")),
                ("is_solution", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ticket_comments", to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="tickets.ticket")),
            ],
            options={
                "verbose_name": "Kommentar",
                "verbose_name_plural": "Kommentare",
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="TicketEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.CharField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="tickets.ticket")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ticket_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Verlaufseintrag",
                "verbose_name_plural": "Verlaufseinträge",
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="Attachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to=tickets.models.attachment_path, verbose_name="Datei")),
                ("name", models.CharField(max_length=255, verbose_name="Dateiname")),
                ("size", models.PositiveIntegerField(default=0, verbose_name="Größe")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("comment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="tickets.comment")),
                ("task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="projects.task")),
                ("ticket", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="tickets.ticket")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ticket_attachments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Anhang",
                "verbose_name_plural": "Anhänge",
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="TimeEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now, verbose_name="Beginn")),
                ("ended_at", models.DateTimeField(blank=True, null=True, verbose_name="Ende")),
                ("note", models.CharField(blank=True, max_length=200, verbose_name="Notiz")),
                ("task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="time_entries", to="projects.task", verbose_name="Aufgabe")),
                ("ticket", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="time_entries", to="tickets.ticket")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="time_entries", to=settings.AUTH_USER_MODEL, verbose_name="Bearbeiter")),
            ],
            options={
                "verbose_name": "Zeiteintrag",
                "verbose_name_plural": "Zeiteinträge",
                "ordering": ["started_at", "id"],
            },
        ),
    ]
