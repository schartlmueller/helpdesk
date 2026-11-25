import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0003_organizations_links_forms"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="ticket",
            name="status",
            field=models.CharField(choices=[("new", "Neu"), ("open", "In Bearbeitung"), ("waiting", "Wartet auf Rückmeldung"), ("on_hold", "Wartet auf Dritte"), ("resolved", "Gelöst"), ("closed", "Geschlossen")], default="new", max_length=20, verbose_name="Status"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="sla_paused_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Zielzeit pausiert seit"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="follow_up_on",
            field=models.DateField(blank=True, help_text="An diesem Tag wird der Bearbeiter erinnert und das Ticket wieder in Bearbeitung gesetzt.", null=True, verbose_name="Wiedervorlage am"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="waiting_reminded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="ChecklistTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, verbose_name="Name")),
                ("items", models.TextField(help_text="Ein Punkt pro Zeile.", verbose_name="Punkte")),
            ],
            options={
                "verbose_name": "Checklisten-Vorlage",
                "verbose_name_plural": "Checklisten-Vorlagen",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ChecklistItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.CharField(max_length=300, verbose_name="Punkt")),
                ("done", models.BooleanField(default=False, verbose_name="Erledigt")),
                ("done_at", models.DateTimeField(blank=True, null=True)),
                ("position", models.PositiveIntegerField(default=0)),
                ("done_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="checked_items", to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="checklist", to="tickets.ticket")),
            ],
            options={
                "verbose_name": "Checklisten-Punkt",
                "verbose_name_plural": "Checklisten-Punkte",
                "ordering": ["position", "id"],
            },
        ),
        migrations.AddField(
            model_name="requestform",
            name="checklist",
            field=models.ForeignKey(blank=True, help_text="Diese Punkte werden dem Ticket automatisch angehängt.", null=True, on_delete=django.db.models.deletion.SET_NULL, to="tickets.checklisttemplate", verbose_name="Checkliste"),
        ),
        migrations.AddField(
            model_name="recurringticket",
            name="checklist",
            field=models.ForeignKey(blank=True, help_text="Diese Punkte werden jedem angelegten Ticket angehängt.", null=True, on_delete=django.db.models.deletion.SET_NULL, to="tickets.checklisttemplate", verbose_name="Checkliste"),
        ),
    ]
