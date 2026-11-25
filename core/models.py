import re

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Organization(models.Model):
    """Kunde oder Abteilung, zu der Melder und ihre Tickets gehören."""

    name = models.CharField("Name", max_length=150, unique=True)
    email_domains = models.TextField(
        "E-Mail-Domains",
        blank=True,
        help_text="z. B. firma.at, tochter.at. Neue Melder mit einer dieser Domains werden automatisch zugeordnet.",
    )
    notes = models.TextField("Notizen", blank=True)
    active = models.BooleanField("Aktiv", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Organisation"
        verbose_name_plural = "Organisationen"

    def __str__(self):
        return self.name

    @property
    def domain_list(self):
        return [d.lower().lstrip("@") for d in re.split(r"[,;\s]+", self.email_domains) if d]


class Membership(models.Model):
    """Ordnet einen Benutzer genau einer Organisation zu."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Benutzer",
        on_delete=models.CASCADE,
        related_name="membership",
    )
    organization = models.ForeignKey(
        Organization,
        verbose_name="Organisation",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    is_contact = models.BooleanField(
        "Ansprechpartner",
        default=False,
        help_text="Sieht alle Tickets der Organisation, nicht nur die eigenen.",
    )

    class Meta:
        verbose_name = "Zuordnung"
        verbose_name_plural = "Zuordnungen"

    def __str__(self):
        return f"{self.user} → {self.organization}"


class Holiday(models.Model):
    """Feiertag oder Betriebsurlaub: zählt nicht für Zielzeiten und Planung."""

    date = models.DateField("Datum", unique=True)
    name = models.CharField("Bezeichnung", max_length=100)

    class Meta:
        ordering = ["date"]
        verbose_name = "Feiertag"
        verbose_name_plural = "Feiertage"

    def __str__(self):
        return f"{self.date:%d.%m.%Y} {self.name}"


class Announcement(models.Model):
    """Störungsmeldung oder Hinweis, der allen als Banner angezeigt wird."""

    class Level(models.TextChoices):
        INFO = "info", "Hinweis"
        WARNING = "warning", "Störung"
        CRITICAL = "critical", "Schwere Störung"

    title = models.CharField("Überschrift", max_length=200)
    text = models.TextField("Text", blank=True)
    level = models.CharField(
        "Art", max_length=20, choices=Level.choices, default=Level.WARNING
    )
    organization = models.ForeignKey(
        Organization,
        verbose_name="Nur für Organisation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text="Leer lassen, damit alle die Meldung sehen.",
    )
    starts_at = models.DateTimeField("Anzeigen ab", default=timezone.now)
    ends_at = models.DateTimeField(
        "Anzeigen bis", null=True, blank=True, help_text="Leer = bis sie beendet wird."
    )
    active = models.BooleanField("Aktiv", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_at"]
        verbose_name = "Störungsmeldung"
        verbose_name_plural = "Störungsmeldungen"

    def __str__(self):
        return self.title

    @classmethod
    def current(cls):
        now = timezone.now()
        return cls.objects.filter(active=True, starts_at__lte=now).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now)
        )

    @property
    def is_current(self):
        now = timezone.now()
        return self.active and self.starts_at <= now and (self.ends_at is None or self.ends_at > now)
