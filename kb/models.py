import os
import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class Article(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Entwurf"
        PUBLISHED = "published", "Veröffentlicht"
        ARCHIVED = "archived", "Archiviert"

    title = models.CharField("Titel", max_length=200)
    problem = models.TextField("Problem")
    solution = models.TextField(
        "Lösung",
        help_text="Formatierung mit Markdown: **fett**, # Überschrift, - Liste, 1. Schritte, `Befehl`.",
    )
    category = models.ForeignKey(
        "tickets.Category",
        verbose_name="Kategorie",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="articles",
    )
    organization = models.ForeignKey(
        "core.Organization",
        verbose_name="Nur sichtbar für",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="articles",
        help_text="Leer lassen, damit alle den Artikel lesen können.",
    )
    status = models.CharField(
        "Status", max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    source_ticket = models.OneToOneField(
        "tickets.Ticket",
        verbose_name="Entstanden aus Ticket",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kb_article",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kb_articles",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_kb_articles",
    )
    views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Wissensartikel"
        verbose_name_plural = "Wissensartikel"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("kb:detail", args=[self.pk])


class ArticleVote(models.Model):
    """Rückmeldung eines Lesers: Hat der Artikel geholfen?"""

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kb_votes"
    )
    helpful = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["article", "user"], name="one_vote_per_user")
        ]
        verbose_name = "Artikelbewertung"
        verbose_name_plural = "Artikelbewertungen"


def article_file_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"kb/{instance.article_id}/{uuid.uuid4().hex}{ext}"


class ArticleFile(models.Model):
    """Bild oder Datei zu einem Artikel, im Text per Markdown eingebunden."""

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="files")
    file = models.FileField("Datei", upload_to=article_file_path)
    name = models.CharField("Dateiname", max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kb_files",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Artikeldatei"
        verbose_name_plural = "Artikeldateien"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("kb:file", args=[self.pk])

    @property
    def image_type(self):
        return IMAGE_TYPES.get(os.path.splitext(self.name)[1].lower())

    @property
    def markdown(self):
        prefix = "!" if self.image_type else ""
        return f"{prefix}[{self.name}]({self.get_absolute_url()})"


@receiver(post_delete, sender=ArticleFile)
def _delete_article_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
