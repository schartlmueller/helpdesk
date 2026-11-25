import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Name")),
                ("description", models.TextField(blank=True, verbose_name="Beschreibung")),
                ("status", models.CharField(choices=[("planned", "Geplant"), ("active", "Aktiv"), ("on_hold", "Pausiert"), ("done", "Abgeschlossen")], default="active", max_length=20, verbose_name="Status")),
                ("start_date", models.DateField(blank=True, null=True, verbose_name="Start")),
                ("due_date", models.DateField(blank=True, null=True, verbose_name="Fällig am")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="owned_projects", to=settings.AUTH_USER_MODEL, verbose_name="Projektleitung")),
            ],
            options={
                "verbose_name": "Projekt",
                "verbose_name_plural": "Projekte",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Milestone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Meilenstein")),
                ("due_date", models.DateField(blank=True, null=True, verbose_name="Termin")),
                ("done", models.BooleanField(default=False, verbose_name="Erreicht")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="milestones", to="projects.project")),
            ],
            options={
                "verbose_name": "Meilenstein",
                "verbose_name_plural": "Meilensteine",
                "ordering": ["due_date", "id"],
            },
        ),
        migrations.CreateModel(
            name="Task",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Titel")),
                ("description", models.TextField(blank=True, verbose_name="Beschreibung")),
                ("status", models.CharField(choices=[("todo", "Offen"), ("doing", "In Arbeit"), ("review", "Prüfung"), ("done", "Erledigt")], default="todo", max_length=20, verbose_name="Status")),
                ("priority", models.CharField(choices=[("low", "Niedrig"), ("normal", "Normal"), ("high", "Hoch")], default="normal", max_length=20, verbose_name="Priorität")),
                ("start_date", models.DateField(blank=True, null=True, verbose_name="Beginn")),
                ("due_date", models.DateField(blank=True, null=True, verbose_name="Fällig am")),
                ("estimated_minutes", models.PositiveIntegerField(blank=True, null=True, verbose_name="Geplanter Aufwand (Minuten)")),
                ("position", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tasks", to=settings.AUTH_USER_MODEL, verbose_name="Zuständig")),
                ("milestone", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tasks", to="projects.milestone", verbose_name="Meilenstein")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="projects.project", verbose_name="Projekt")),
            ],
            options={
                "verbose_name": "Aufgabe",
                "verbose_name_plural": "Aufgaben",
                "ordering": ["position", "id"],
            },
        ),
        migrations.CreateModel(
            name="TaskComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField(verbose_name="Kommentar")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="task_comments", to=settings.AUTH_USER_MODEL)),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="projects.task")),
            ],
            options={
                "verbose_name": "Aufgabenkommentar",
                "verbose_name_plural": "Aufgabenkommentare",
                "ordering": ["created_at", "id"],
            },
        ),
    ]
