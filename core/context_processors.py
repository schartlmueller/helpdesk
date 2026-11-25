from django.conf import settings
from django.db.models import Q

from kb.models import Article
from tickets.models import TimeEntry

from .brands import BRANDS, brand_for
from .models import Announcement
from .orgs import membership_of


# Welcher Eintrag der Seitenleiste zur aufgerufenen Seite gehört.
# Reihenfolge zählt: der erste passende Anfang gewinnt.
NAV_SECTIONS = [
    ("dashboard", "dashboard"),
    ("tickets:pool", "pool"),
    ("tickets:planner", "planner"),
    ("tickets:absence", "planner"),
    ("tickets:recurring", "recurring"),
    ("tickets:times", "times"),
    ("tickets:stats", "stats"),
    ("tickets:service_report", "report"),
    ("tickets:", "tickets"),
    ("kb:drafts", "drafts"),
    ("kb:", "kb"),
    ("projects:", "projects"),
    ("announcement", "announcements"),
    ("organization", "organizations"),
]


def _active_section(request):
    match = getattr(request, "resolver_match", None)
    name = match.view_name if match else ""
    for prefix, section in NAV_SECTIONS:
        if name.startswith(prefix):
            return section
    return ""


def nav(request):
    user = getattr(request, "user", None)
    # Bearbeiter können ein Design mit ?design=... ansehen, ohne es umzustellen;
    # ?design=aus beendet die Vorschau.
    wanted = request.GET.get("design")
    if wanted and user is not None and user.is_authenticated and user.is_staff:
        if wanted in BRANDS:
            request.session["brand_preview"] = wanted
        else:
            request.session.pop("brand_preview", None)

    context = {
        "sso_enabled": settings.SSO_ENABLED,
        "nav_active": _active_section(request),
        "brand": brand_for(request),
    }
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
