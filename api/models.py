import secrets

from django.conf import settings
from django.db import models


def generate_key():
    return secrets.token_hex(24)


class ApiToken(models.Model):
    """Zugangsschlüssel für die Schnittstelle. Handelt mit den Rechten des Benutzers."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Benutzer",
        on_delete=models.CASCADE,
        related_name="api_tokens",
    )
    name = models.CharField("Verwendung", max_length=100, help_text="z. B. Monitoring")
    key = models.CharField("Schlüssel", max_length=64, unique=True, default=generate_key)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField("Zuletzt verwendet", null=True, blank=True)

    class Meta:
        verbose_name = "API-Schlüssel"
        verbose_name_plural = "API-Schlüssel"

    def __str__(self):
        return f"{self.name} ({self.user})"
