import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("projects", "0002_task_planned_for"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="organization",
            field=models.ForeignKey(blank=True, help_text="Gebuchte Zeiten erscheinen im Leistungsnachweis dieser Organisation.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="projects", to="core.organization", verbose_name="Organisation"),
        ),
    ]
