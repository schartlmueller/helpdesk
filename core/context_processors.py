from django.conf import settings
from django.db.models import Q

from kb.models import Article
from tickets.models import TimeEntry

from .models import Announcement
from .orgs import membership_of


def nav(request):
    context = {"sso_enabled": settings.SSO_ENABLED}
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return context

    # Störungsmeldungen: allgemeine für alle, gezielte nur für die Organisation
    announcements = Announcement.current()
    if not user.is_staff:
        membership = membership_of(user)
        if membership is None:
            announcements = announcements.filter(organization__isnull=True)
        else:
            announcements = announcements.filter(
                Q(organization__isnull=True) | Q(organization=membership.organization)
            )
    context["announcements"] = list(announcements.select_related("organization")[:5])

    if user.is_staff:
        context["kb_draft_count"] = Article.objects.filter(
            status=Article.Status.DRAFT
        ).count()
        # Laufende Uhr des Bearbeiters, wird in der Kopfzeile angezeigt.
        context["running_entry"] = (
            TimeEntry.objects.filter(user=user, ended_at__isnull=True)
            .select_related("ticket", "task__project")
            .first()
        )
    return context
