from django.db import migrations, models


def fill_closed_at(apps, schema_editor):
    """Bereits erledigte Tickets bekommen ihren Erledigt-Zeitpunkt nachgetragen."""
    Ticket = apps.get_model("tickets", "Ticket")
    done = Ticket.objects.filter(status__in=["resolved", "closed"], closed_at__isnull=True)
    for ticket in done.iterator():
        Ticket.objects.filter(pk=ticket.pk).update(
            closed_at=ticket.resolved_at or ticket.updated_at
        )


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0004_pause_followup_checklists"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="kind",
            field=models.CharField(blank=True, choices=[("bug", "Fehler"), ("feature", "Erweiterung"), ("nice", "Nice to have")], help_text="Fehler, Erweiterung oder Nice to have. Leer = noch nicht eingestuft.", max_length=20, verbose_name="Art"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="closed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Erledigt seit"),
        ),
        migrations.RunPython(fill_closed_at, migrations.RunPython.noop),
    ]
