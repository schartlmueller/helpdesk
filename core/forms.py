import hashlib

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.core.cache import cache
from django.core.exceptions import ValidationError


class ThrottledAuthenticationForm(AuthenticationForm):
    """Sperrt die Anmeldung für einen Benutzernamen nach mehreren Fehlversuchen."""

    def clean(self):
        username = (self.cleaned_data.get("username") or "").strip().lower()
        key = "login-fail:" + hashlib.sha256(username.encode()).hexdigest()
        if username and cache.get(key, 0) >= settings.LOGIN_MAX_ATTEMPTS:
            raise ValidationError(
                f"Zu viele Fehlversuche. Bitte in {settings.LOGIN_LOCK_MINUTES} "
                "Minuten erneut versuchen."
            )
        try:
            cleaned = super().clean()
        except ValidationError:
            if username:
                cache.set(key, cache.get(key, 0) + 1, settings.LOGIN_LOCK_MINUTES * 60)
            raise
        cache.delete(key)
        return cleaned


class SetOrResetPasswordForm(PasswordResetForm):
    """Wie das Standardformular, aber auch für Konten ohne Passwort.

    Wer sein erstes Ticket per E-Mail geschickt hat, besitzt ein Konto ohne
    Passwort und kann sich hierüber erstmals eines setzen.
    """

    def get_users(self, email):
        return get_user_model().objects.filter(email__iexact=email, is_active=True)
