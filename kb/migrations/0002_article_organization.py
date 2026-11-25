import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("kb", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="organization",
            field=models.ForeignKey(blank=True, help_text="Leer lassen, damit alle den Artikel lesen können.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="articles", to="core.organization", verbose_name="Nur sichtbar für"),
        ),
    ]
