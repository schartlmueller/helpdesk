import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import kb.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("tickets", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Article",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Titel")),
                ("problem", models.TextField(verbose_name="Problem")),
                ("solution", models.TextField(help_text="Formatierung mit Markdown: **fett**, # Überschrift, - Liste, 1. Schritte, `Befehl`.", verbose_name="Lösung")),
                ("status", models.CharField(choices=[("draft", "Entwurf"), ("published", "Veröffentlicht"), ("archived", "Archiviert")], default="draft", max_length=20, verbose_name="Status")),
                ("views", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("author", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="kb_articles", to=settings.AUTH_USER_MODEL)),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="articles", to="tickets.category", verbose_name="Kategorie")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_kb_articles", to=settings.AUTH_USER_MODEL)),
                ("source_ticket", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="kb_article", to="tickets.ticket", verbose_name="Entstanden aus Ticket")),
            ],
            options={
                "verbose_name": "Wissensartikel",
                "verbose_name_plural": "Wissensartikel",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="ArticleVote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("helpful", models.BooleanField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("article", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="votes", to="kb.article")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="kb_votes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Artikelbewertung",
                "verbose_name_plural": "Artikelbewertungen",
                "constraints": [models.UniqueConstraint(fields=("article", "user"), name="one_vote_per_user")],
            },
        ),
        migrations.CreateModel(
            name="ArticleFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to=kb.models.article_file_path, verbose_name="Datei")),
                ("name", models.CharField(max_length=255, verbose_name="Dateiname")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("article", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="files", to="kb.article")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="kb_files", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Artikeldatei",
                "verbose_name_plural": "Artikeldateien",
                "ordering": ["id"],
            },
        ),
    ]
