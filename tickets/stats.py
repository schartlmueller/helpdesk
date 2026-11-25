from datetime import datetime

from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone

from core.decorators import staff_required
from kb.models import Article

from .models import Ticket, TimeEntry


def _month_key(moment):
    local = timezone.localtime(moment)
    return (local.year, local.month)


@staff_required
def statistics(request):
    """Entwicklung der letzten zwölf Monate."""
    today = timezone.localdate()
    year, month = today.year, today.month
    keys = []
    for _ in range(12):
        keys.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    keys.reverse()
    start = timezone.make_aware(datetime(keys[0][0], keys[0][1], 1))

    months = {
        key: {
            "label": f"{key[1]:02d}/{key[0]}",
            "created": 0,
            "resolved": 0,
            "resolve_seconds": 0,
            "sla_total": 0,
            "sla_met": 0,
            "response_total": 0,
            "response_met": 0,
            "response_seconds": 0,
            "booked": 0,
        }
        for key in keys
    }

    recent = Ticket.objects.filter(created_at__gte=start)
    created = recent.values_list("created_at", "first_response_at", "response_due_at")
    for created_at, first_response_at, response_due_at in created:
        row = months.get(_month_key(created_at))
        if not row:
            continue
        row["created"] += 1
        # Reaktionszeit: Zeit bis zur ersten Antwort eines Bearbeiters
        if first_response_at is not None and response_due_at is not None:
            row["response_total"] += 1
            row["response_met"] += first_response_at <= response_due_at
            row["response_seconds"] += max(0, (first_response_at - created_at).total_seconds())

    resolved = Ticket.objects.filter(resolved_at__gte=start).values_list(
        "created_at", "resolved_at", "due_at"
    )
    for created_at, resolved_at, due_at in resolved:
        row = months.get(_month_key(resolved_at))
        if not row:
            continue
        row["resolved"] += 1
        row["resolve_seconds"] += max(0, (resolved_at - created_at).total_seconds())
        if due_at is not None:
            row["sla_total"] += 1
            row["sla_met"] += resolved_at <= due_at

    for entry in TimeEntry.objects.filter(started_at__gte=start):
        row = months.get(_month_key(entry.started_at))
        if row:
            row["booked"] += entry.seconds

    rows = list(months.values())
    peak = max([r["created"] for r in rows] + [r["resolved"] for r in rows] + [1])
    for row in rows:
        row["created_bar"] = round(row["created"] * 100 / peak)
        row["resolved_bar"] = round(row["resolved"] * 100 / peak)
        row["avg_hours"] = (
            round(row["resolve_seconds"] / row["resolved"] / 3600, 1)
            if row["resolved"]
            else None
        )
        row["sla_percent"] = (
            round(row["sla_met"] * 100 / row["sla_total"]) if row["sla_total"] else None
        )
        row["response_percent"] = (
            round(row["response_met"] * 100 / row["response_total"])
            if row["response_total"]
            else None
        )
        row["response_hours"] = (
            round(row["response_seconds"] / row["response_total"] / 3600, 1)
            if row["response_total"]
            else None
        )

    by_category = (
        recent.values("category__name").annotate(n=Count("id")).order_by("-n")[:15]
    )
    by_organization = (
        recent.values("organization__name").annotate(n=Count("id")).order_by("-n")[:15]
    )
    kind_names = dict(Ticket.Kind.choices)
    by_kind = [
        {"name": kind_names.get(row["kind"], "Nicht eingestuft"), "n": row["n"]}
        for row in recent.values("kind").annotate(n=Count("id")).order_by("-n")
    ]
    by_priority = recent.values("priority").annotate(n=Count("id")).order_by("-n")
    priority_names = dict(Ticket.Priority.choices)
    by_assignee = (
        Ticket.objects.filter(resolved_at__gte=start, assignee__isnull=False)
        .values("assignee__username", "assignee__first_name", "assignee__last_name")
        .annotate(n=Count("id"))
        .order_by("-n")[:15]
    )
    top_articles = (
        Article.objects.filter(status=Article.Status.PUBLISHED)
        .annotate(
            yes=Count("votes", filter=Q(votes__helpful=True)),
            no=Count("votes", filter=Q(votes__helpful=False)),
        )
        .order_by("-views")[:10]
    )

    return render(
        request,
        "tickets/stats.html",
        {
            "rows": rows,
            "total_created": sum(r["created"] for r in rows),
            "total_resolved": sum(r["resolved"] for r in rows),
            "by_category": by_category,
            "by_kind": by_kind,
            "by_organization": by_organization,
            "by_priority": [
                {"name": priority_names.get(p["priority"], p["priority"]), "n": p["n"]}
                for p in by_priority
            ],
            "by_assignee": [
                {
                    "name": f"{a['assignee__first_name']} {a['assignee__last_name']}".strip()
                    or a["assignee__username"],
                    "n": a["n"],
                }
                for a in by_assignee
            ],
            "top_articles": top_articles,
        },
    )
