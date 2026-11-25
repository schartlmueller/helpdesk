"""Leistungsnachweis: gebuchte Zeiten je Organisation für einen Zeitraum."""

from datetime import timedelta

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.decorators import staff_required
from core.models import Organization

from .models import TimeEntry
from .pdf import build_service_report


def _safe_date(value):
    try:
        return parse_date(value or "")
    except ValueError:
        return None


def collect(organization, start, end):
    """Abgeschlossene Zeiteinträge der Organisation, nach Ticket bzw. Aufgabe gruppiert."""
    entries = (
        TimeEntry.objects.filter(
            Q(ticket__organization=organization) | Q(task__project__organization=organization),
            ended_at__isnull=False,
            started_at__date__gte=start,
            started_at__date__lte=end,
        )
        .select_related("user", "ticket", "task__project")
        .order_by("started_at")
    )
    groups = {}
    for entry in entries:
        key = ("t", entry.ticket_id) if entry.ticket_id else ("a", entry.task_id)
        group = groups.setdefault(
            key,
            {
                "label": entry.target_label,
                "url": entry.target.get_absolute_url(),
                "seconds": 0,
                "lines": [],
            },
        )
        begin = timezone.localtime(entry.started_at)
        finish = timezone.localtime(entry.ended_at)
        group["seconds"] += entry.seconds
        group["lines"].append(
            {
                "date": begin.strftime("%d.%m.%Y"),
                "person": entry.user.get_full_name() or entry.user.username,
                "time": f"{begin:%H:%M}–{finish:%H:%M}",
                "seconds": entry.seconds,
                "note": entry.note,
            }
        )
    result = list(groups.values())
    return result, sum(g["seconds"] for g in result)


@staff_required
def service_report(request):
    today = timezone.localdate()
    # Standard: der vergangene Kalendermonat
    last_month_end = today.replace(day=1) - timedelta(days=1)
    start = _safe_date(request.GET.get("von")) or last_month_end.replace(day=1)
    end = _safe_date(request.GET.get("bis")) or last_month_end
    organizations = Organization.objects.all()
    org_id = request.GET.get("org", "")
    organization = organizations.filter(pk=org_id).first() if org_id.isdigit() else None

    groups, total = ([], 0)
    if organization is not None:
        groups, total = collect(organization, start, end)
        if request.GET.get("format") == "pdf":
            period = f"{start:%d.%m.%Y} bis {end:%d.%m.%Y}"
            data = build_service_report(
                "Leistungsnachweis",
                organization.name,
                period,
                groups,
                total,
                footer=f"Erstellt am {today:%d.%m.%Y}. Laufende, noch nicht beendete Zeiten sind nicht enthalten.",
            )
            response = HttpResponse(data, content_type="application/pdf")
            response["Content-Disposition"] = (
                f'attachment; filename="leistungsnachweis_{organization.pk}_{start}_{end}.pdf"'
            )
            return response

    return render(
        request,
        "tickets/service_report.html",
        {
            "organizations": organizations,
            "organization": organization,
            "org_id": org_id,
            "start": start,
            "end": end,
            "groups": groups,
            "total": total,
        },
    )
