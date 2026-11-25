from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0005_kind_closed_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="pool_week",
            field=models.DateField(blank=True, null=True, verbose_name="Wochenpool"),
        ),
    ]
