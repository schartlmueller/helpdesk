from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="planned_for",
            field=models.DateField(blank=True, help_text="Tag in der Wochenplanung.", null=True, verbose_name="Geplant für"),
        ),
    ]
