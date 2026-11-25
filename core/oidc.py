"""Anmeldung per Single Sign-On (OpenID Connect).

Wird nur geladen, wenn OIDC_CLIENT_ID gesetzt ist. Benutzer werden über ihre
E-Mail-Adresse zugeordnet und beim ersten Login automatisch angelegt.
"""

from django.conf import settings
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


def generate_username(email, claims=None):
    return email.lower()[:150]


class HelpdeskOIDCBackend(OIDCAuthenticationBackend):
    def create_user(self, claims):
        return self._sync(super().create_user(claims), claims)

    def update_user(self, user, claims):
        return self._sync(user, claims)

    def _sync(self, user, claims):
        user.first_name = (claims.get("given_name") or user.first_name)[:150]
        user.last_name = (claims.get("family_name") or user.last_name)[:150]
        # Bearbeiter-Rolle aus der Gruppenzugehörigkeit, falls konfiguriert.
        if settings.OIDC_STAFF_GROUP and not user.is_superuser:
            groups = claims.get(settings.OIDC_GROUPS_CLAIM) or []
            if isinstance(groups, str):
                groups = [groups]
            user.is_staff = settings.OIDC_STAFF_GROUP in groups
        user.save()
        return user
