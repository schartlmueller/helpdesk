import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import api.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ApiToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="z. B. Monitoring", max_length=100, verbose_name="Verwendung")),
                ("key", models.CharField(default=api.models.generate_key, max_length=64, unique=True, verbose_name="Schlüssel")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True, verbose_name="Zuletzt verwendet")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_tokens", to=settings.AUTH_USER_MODEL, verbose_name="Benutzer")),
            ],
            options={
                "verbose_name": "API-Schlüssel",
                "verbose_name_plural": "API-Schlüssel",
            },
        ),
    ]
