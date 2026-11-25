import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("tickets", "0002_planning"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="organization",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tickets", to="core.organization", verbose_name="Organisation"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="parent",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="children", to="tickets.ticket", verbose_name="Hauptticket"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="related",
            field=models.ManyToManyField(blank=True, to="tickets.ticket", verbose_name="Hängt zusammen mit"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="response_due_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Erste Antwort bis"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="first_response_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Erste Antwort am"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="response_escalated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="RequestForm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="z. B. Neuer Mitarbeiter", max_length=150, verbose_name="Name")),
                ("description", models.TextField(blank=True, help_text="Wird dem Melder über dem Formular angezeigt.", verbose_name="Erklärung")),
                ("priority", models.CharField(choices=[("low", "Niedrig"), ("normal", "Normal"), ("high", "Hoch"), ("urgent", "Dringend")], default="normal", max_length=20, verbose_name="Priorität")),
                ("estimated_minutes", models.PositiveIntegerField(blank=True, null=True, verbose_name="Geplanter Aufwand (Minuten)")),
                ("staff_only", models.BooleanField(default=False, help_text="Melder sehen dieses Formular nicht.", verbose_name="Nur für Bearbeiter")),
                ("active", models.BooleanField(default=True, verbose_name="Aktiv")),
                ("position", models.PositiveIntegerField(default=0, verbose_name="Reihenfolge")),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="tickets.category", verbose_name="Kategorie")),
                ("team", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="tickets.team", verbose_name="Team")),
            ],
            options={
                "verbose_name": "Anfrage-Formular",
                "verbose_name_plural": "Anfrage-Formulare",
                "ordering": ["position", "name"],
            },
        ),
        migrations.CreateModel(
            name="RequestField",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=150, verbose_name="Bezeichnung")),
                ("kind", models.CharField(choices=[("text", "Kurzer Text"), ("textarea", "Langer Text"), ("select", "Auswahl"), ("date", "Datum"), ("number", "Zahl"), ("checkbox", "Ja/Nein")], default="text", max_length=20, verbose_name="Art")),
                ("required", models.BooleanField(default=True, verbose_name="Pflichtfeld")),
                ("choices", models.TextField(blank=True, help_text="Nur für Auswahl: eine pro Zeile.", verbose_name="Auswahlmöglichkeiten")),
                ("help_text", models.CharField(blank=True, max_length=200, verbose_name="Hinweis")),
                ("in_title", models.BooleanField(default=False, help_text="Der Wert wird an den Betreff des Tickets angehängt.", verbose_name="Im Betreff anzeigen")),
                ("position", models.PositiveIntegerField(default=0, verbose_name="Reihenfolge")),
                ("form", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fields", to="tickets.requestform")),
            ],
            options={
                "verbose_name": "Formularfeld",
                "verbose_name_plural": "Formularfelder",
                "ordering": ["position", "id"],
            },
        ),
    ]
