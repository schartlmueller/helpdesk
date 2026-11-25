"""Wochenpool: die für eine Woche ausgewählten Tickets, aus denen sich die
Bearbeiter selbst bedienen."""

from datetime import datetime, time, timedelta

from django.contrib import messages
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from django.contrib.auth import get_user_model

from core.decorators import staff_required

from . import notify
from .models import Ticket
from .services import log, search_tickets, start_timer, stop_timers

CLOSED_STATES = [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]

PRIORITY_RANK = Case(
    When(priority=Ticket.Priority.URGENT, then=Value(0)),
    When(priority=Ticket.Priority.HIGH, then=Value(1)),
    When(priority=Ticket.Priority.NORMAL, then=Value(2)),
    default=Value(3),
    output_field=IntegerField(),
)


def monday_of(day):
    return day - timedelta(days=day.weekday())


def _week_param(value):
    try:
        day = parse_date(value or "")
    except ValueError:
        day = None
    return monday_of(day or timezone.localdate())


def _name(user):
    return user.get_full_name() or user.username


def _staff():
    return get_user_model().objects.filter(is_staff=True, is_active=True)


def _back(request, monday=None):
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    url = reverse("tickets:pool")
    if monday is not None:
        url += f"?woche={monday.isoformat()}"
    return redirect(url)


def _week_label(monday):
    return f"KW {monday.isocalendar()[1]}"


@staff_required
def pool(request):
    today = timezone.localdate()
    monday = _week_param(request.GET.get("woche"))
    this_monday = monday_of(today)

    in_pool = list(
        Ticket.objects.filter(pool_week=monday, merged_into__isnull=True)
        .select_related("assignee", "requester", "category")
        .annotate(rank=PRIORITY_RANK)
        .order_by("rank", "due_at")
    )
    free = [t for t in in_pool if t.is_open and t.assignee_id is None]
    done = [t for t in in_pool if not t.is_open]

    # Ansicht: alle Bearbeiter oder nur die eigenen Tickets. Die Wahl wird
    # gemerkt, bis man sie wieder umstellt.
    view = request.GET.get("ansicht") or request.session.get("pool_view") or "alle"
    if view not in ("alle", "meine"):
        view = "alle"
    request.session["pool_view"] = view

    # Gruppen je Bearbeiter mit offenen und erledigten Tickets
    by_user = {}
    for ticket in in_pool:
        if ticket.assignee_id is None:
            continue
        group = by_user.setdefault(
            ticket.assignee_id, {"user": ticket.assignee, "open": [], "done": []}
        )
        group["open" if ticket.is_open else "done"].append(ticket)
    for group in by_user.values():
        group["minutes"] = sum(t.estimated_minutes or 0 for t in group["open"])
        group["mine"] = group["user"].id == request.user.id
    # Eigene Tickets zuerst, dann nach Namen
    groups = sorted(
        by_user.values(), key=lambda g: (not g["mine"], _name(g["user"]).lower())
    )
    taken_count = sum(len(g["open"]) for g in groups)
    if view == "meine":
        groups = [g for g in groups if g["mine"]]
    # Erledigte Tickets, die niemandem zugeordnet sind (selten, z. B. automatisch geschlossen)
    done_unassigned = [t for t in done if t.assignee_id is None]

    def minutes(tickets):
        return sum(t.estimated_minutes or 0 for t in tickets)

    # Was in dieser Woche nebenbei erledigt wurde, ohne im Pool zu sein
    week_start = timezone.make_aware(datetime.combine(monday, time.min))
    week_end = week_start + timedelta(days=7)
    unplanned_done = (
        Ticket.objects.filter(
            status__in=CLOSED_STATES,
            closed_at__gte=week_start,
            closed_at__lt=week_end,
            merged_into__isnull=True,
        )
        .exclude(pool_week=monday)
        .count()
    )

    open_tickets = Ticket.objects.exclude(status__in=CLOSED_STATES).filter(
        merged_into__isnull=True
    )
    leftovers = open_tickets.filter(pool_week__lt=monday).count()

    # Kandidaten für die Planung: offene Tickets, die noch nicht im Pool liegen
    query = request.GET.get("q", "").strip()
    kind = request.GET.get("art", "")
    candidates = open_tickets.exclude(pool_week=monday)
    if kind in Ticket.Kind.values:
        candidates = candidates.filter(kind=kind)
    elif kind == "none":
        candidates = candidates.filter(kind="")
    if query:
        candidates = search_tickets(candidates, query, staff=True)
    candidates = (
        candidates.select_related("assignee", "requester", "category")
        .annotate(rank=PRIORITY_RANK)
        .order_by("rank", "due_at")[:150]
    )

    total = len(in_pool)
    return render(
        request,
        "tickets/pool.html",
        {
            "monday": monday,
            "friday": monday + timedelta(days=4),
            "week_number": monday.isocalendar()[1],
            "previous": monday - timedelta(days=7),
            "following": monday + timedelta(days=7),
            "is_current": monday == this_monday,
            "view": view,
            "free": free,
            "groups": groups,
            "taken_count": taken_count,
            "done": done,
            "done_unassigned": done_unassigned,
            "staff_users": _staff().order_by("first_name", "last_name", "username"),
            "total": total,
            "percent_done": round(len(done) * 100 / total) if total else 0,
            "minutes_total": minutes(in_pool),
            "minutes_done": minutes(done),
            "unplanned_done": unplanned_done,
            "leftovers": leftovers,
            "candidates": candidates,
            "query": query,
            "kind": kind,
            "kind_choices": Ticket.Kind.choices,
        },
    )


@require_POST
@staff_required
def pool_add(request):
    """Ausgewählte Tickets in den Pool einer Woche legen."""
    monday = _week_param(request.POST.get("woche"))
    ids = [int(i) for i in request.POST.getlist("tickets") if i.isdigit()]
    tickets = Ticket.objects.exclude(status__in=CLOSED_STATES).filter(pk__in=ids)
    # Optional gleich einem Bearbeiter zuordnen
    assignee = _staff().filter(pk=request.POST.get("assignee") or 0).first()
    count = 0
    for ticket in tickets:
        changed = ticket.pool_week != monday
        newly_assigned = assignee is not None and ticket.assignee_id != assignee.id
        if not changed and not newly_assigned:
            continue
        ticket.pool_week = monday
        text = f"In den Wochenpool {_week_label(monday)} gelegt"
        if newly_assigned:
            ticket.assignee = assignee
            text += f", zugeordnet an {_name(assignee)}"
        ticket.save()
        log(ticket, request.user, text)
        if newly_assigned:
            notify.staff_assigned(ticket, request.user)
        count += 1
    if count:
        messages.success(request, f"{count} Tickets im Wochenpool {_week_label(monday)}.")
    else:
        messages.info(request, "Kein Ticket ausgewählt.")
    return _back(request, monday)


@require_POST
@staff_required
def pool_remove(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    monday = ticket.pool_week
    if monday is not None:
        ticket.pool_week = None
        ticket.save()
        log(ticket, request.user, "Aus dem Wochenpool genommen")
    return _back(request, monday)


@require_POST
@staff_required
def pool_take(request, pk):
    """Ein Ticket aus dem Pool übernehmen, auf Wunsch gleich mit der Arbeit beginnen."""
    ticket = get_object_or_404(Ticket.objects.select_related("assignee"), pk=pk)
    monday = ticket.pool_week
    if not ticket.is_open:
        messages.error(request, "Das Ticket ist bereits erledigt.")
        return _back(request, monday)
    if ticket.assignee_id and ticket.assignee_id != request.user.id:
        # Jemand war schneller.
        messages.error(request, f"Das Ticket hat inzwischen {_name(ticket.assignee)} übernommen.")
        return _back(request, monday)

    start = "start" in request.POST
    ticket.assignee = request.user
    if start:
        ticket.status = Ticket.Status.OPEN
    ticket.save()
    log(ticket, request.user, "Aus dem Wochenpool übernommen")
    if start:
        start_timer(request.user, ticket=ticket)
        return redirect(ticket)
    return _back(request, monday)


@require_POST
@staff_required
def pool_assign(request, pk):
    """Ein Pool-Ticket einem Bearbeiter zuordnen oder wieder freigeben."""
    ticket = get_object_or_404(Ticket.objects.select_related("assignee"), pk=pk)
    monday = ticket.pool_week
    if not ticket.is_open:
        return _back(request, monday)
    assignee = _staff().filter(pk=request.POST.get("user") or 0).first()
    if (assignee.id if assignee else None) == ticket.assignee_id:
        return _back(request, monday)

    if assignee is None:
        stop_timers(ticket=ticket)
        ticket.planned_for = None
        text = "Zuordnung aufgehoben, zurück in den Wochenpool"
    else:
        text = f"Im Wochenpool zugeordnet an {_name(assignee)}"
    ticket.assignee = assignee
    ticket.save()
    log(ticket, request.user, text)
    if assignee is not None:
        notify.staff_assigned(ticket, request.user)
    return _back(request, monday)


@require_POST
@staff_required
def pool_release(request, pk):
    """Übernommenes Ticket wieder für alle freigeben."""
    ticket = get_object_or_404(Ticket, pk=pk)
    monday = ticket.pool_week
    if ticket.is_open and ticket.assignee_id is not None:
        stop_timers(ticket=ticket)
        ticket.assignee = None
        ticket.planned_for = None
        ticket.save()
        log(ticket, request.user, "Zurück in den Wochenpool gegeben")
    return _back(request, monday)


@require_POST
@staff_required
def pool_carry(request):
    """Offene Tickets aus früheren Wochen in diese Woche übernehmen."""
    monday = _week_param(request.POST.get("woche"))
    old = Ticket.objects.exclude(status__in=CLOSED_STATES).filter(
        pool_week__lt=monday, merged_into__isnull=True
    )
    count = 0
    for ticket in old:
        ticket.pool_week = monday
        ticket.save()
        log(ticket, request.user, f"In den Wochenpool {_week_label(monday)} übernommen")
        count += 1
    messages.success(request, f"{count} offene Tickets aus früheren Wochen übernommen.")
    return _back(request, monday)
