"""Wochenplanung, Abwesenheiten, wiederkehrende Tickets und Kalender-Feed."""

import json
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.decorators import staff_required
from core.models import Holiday
from projects.models import Task

from . import notify
from .ical import build_calendar
from .models import (
    Absence,
    PlannerProfile,
    RecurringTicket,
    Team,
    Ticket,
    TimeEntry,
    generate_calendar_token,
)
from .services import log

CLOSED_STATES = [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]


def _staff():
    return get_user_model().objects.filter(is_staff=True, is_active=True)


def _name(user):
    return user.get_full_name() or user.username


def _date_input():
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def _safe_date(value):
    try:
        return parse_date(value or "")
    except ValueError:
        return None


def _back(request):
    """Zurück zur angezeigten Woche, aber nur zu Adressen dieser Anwendung."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect("tickets:planner")


def profile_for(user):
    profile, _ = PlannerProfile.objects.get_or_create(user=user)
    return profile


# --- Formulare ----------------------------------------------------------------

class AbsenceForm(forms.ModelForm):
    class Meta:
        model = Absence
        fields = ["user", "start_date", "end_date", "reason"]
        widgets = {"start_date": _date_input(), "end_date": _date_input()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = _staff()
        self.fields["user"].label_from_instance = _name

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("Das Ende liegt vor dem Beginn.")
        return cleaned


class ProfileForm(forms.ModelForm):
    class Meta:
        model = PlannerProfile
        fields = ["daily_hours"]


class RecurringForm(forms.ModelForm):
    class Meta:
        model = RecurringTicket
        fields = [
            "title",
            "description",
            "category",
            "priority",
            "team",
            "assignee",
            "estimated_minutes",
            "interval",
            "next_run",
            "lead_days",
            "checklist",
            "active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "next_run": _date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = _staff()
        self.fields["assignee"].label_from_instance = _name


# --- Wochenplanung ------------------------------------------------------------

def _ticket_item(ticket, day=None):
    late = False
    if day is not None and ticket.due_at is not None and ticket.is_open:
        late = day > timezone.localtime(ticket.due_at).date()
    return {
        "kind": "ticket",
        "id": ticket.pk,
        "assignee_name": _name(ticket.assignee) if ticket.assignee_id else "",
        "ref": f"#{ticket.pk}",
        "title": ticket.title,
        "url": ticket.get_absolute_url(),
        "minutes": ticket.estimated_minutes,
        "done": not ticket.is_open,
        "priority": ticket.priority,
        "after_due": late,
    }


def _task_item(task):
    return {
        "kind": "task",
        "id": task.pk,
        "ref": task.project.name,
        "title": task.title,
        "url": task.get_absolute_url(),
        "minutes": task.estimated_minutes,
        "done": task.status == Task.Status.DONE,
        "priority": task.priority,
        "after_due": False,
    }


@staff_required
def planner(request):
    today = timezone.localdate()
    monday = _safe_date(request.GET.get("woche")) or today
    monday -= timedelta(days=monday.weekday())
    days = [
        monday + timedelta(days=i)
        for i in range(7)
        if (monday + timedelta(days=i)).weekday() in settings.BUSINESS_DAYS
    ]
    first, last = days[0], days[-1]

    team_id = request.GET.get("team", "")
    users = _staff().order_by("first_name", "last_name", "username")
    if team_id.isdigit():
        users = users.filter(helpdesk_teams__id=int(team_id))
    users = list(users)
    user_ids = {u.id for u in users}
    profiles = {p.user_id: p for p in PlannerProfile.objects.filter(user__in=users)}

    holidays = dict(
        Holiday.objects.filter(date__gte=first, date__lte=last).values_list("date", "name")
    )
    absent = {}
    week_absences = list(
        Absence.objects.filter(
            user__in=users, start_date__lte=last, end_date__gte=first
        ).select_related("user")
    )
    for absence in week_absences:
        for day in days:
            if absence.start_date <= day <= absence.end_date:
                absent[(absence.user_id, day)] = absence.reason or "abwesend"

    # Einträge je (Bearbeiter, Tag); Bearbeiter None = noch nicht zugewiesen
    grid = {}
    tickets = Ticket.objects.filter(
        planned_for__gte=first, planned_for__lte=last, merged_into__isnull=True
    ).select_related("assignee")
    for ticket in tickets:
        owner = ticket.assignee_id
        if owner is not None and owner not in user_ids:
            continue
        grid.setdefault((owner, ticket.planned_for), []).append(
            _ticket_item(ticket, ticket.planned_for)
        )
    tasks = Task.objects.filter(
        planned_for__gte=first, planned_for__lte=last
    ).select_related("project", "assignee")
    for task in tasks:
        owner = task.assignee_id
        if owner is not None and owner not in user_ids:
            continue
        grid.setdefault((owner, task.planned_for), []).append(_task_item(task))

    booked = {}
    for entry in TimeEntry.objects.filter(
        user__in=users, started_at__date__gte=first, started_at__date__lte=last
    ):
        key = (entry.user_id, timezone.localtime(entry.started_at).date())
        booked[key] = booked.get(key, 0) + entry.seconds

    def cell(user, day):
        user_id = user.id if user else None
        items = grid.get((user_id, day), [])
        planned = sum(i["minutes"] or 0 for i in items if not i["done"])
        # Feiertage gelten für alle, Abwesenheiten für einzelne Bearbeiter.
        reason = holidays.get(day) or absent.get((user_id, day))
        capacity = 0
        if user is not None and not reason:
            profile = profiles.get(user_id)
            capacity = profile.daily_minutes if profile else 8 * 60
        return {
            "date": day,
            "items": items,
            "planned": planned,
            "capacity": capacity,
            "over": user is not None and planned > capacity,
            "absent": reason,
            "booked": booked.get((user_id, day), 0),
            "missing_estimate": any(not i["minutes"] and not i["done"] for i in items),
        }

    rows = []
    for user in users:
        cells = [cell(user, day) for day in days]
        rows.append(
            {
                "user": user,
                "cells": cells,
                "planned": sum(c["planned"] for c in cells),
                "capacity": sum(c["capacity"] for c in cells),
            }
        )
    unassigned = [cell(None, day) for day in days]

    open_tickets = Ticket.objects.exclude(status__in=CLOSED_STATES).filter(
        merged_into__isnull=True
    )
    # Wochenpool: für diese Woche ausgewählt, aber noch keinem Tag zugeordnet
    pool = open_tickets.filter(pool_week=monday, planned_for__isnull=True).select_related(
        "assignee"
    )
    backlog = (
        open_tickets.filter(planned_for__isnull=True)
        .exclude(pool_week=monday)
        .select_related("assignee")
    )
    missed = open_tickets.filter(planned_for__lt=min(today, first)).select_related("assignee")

    return render(
        request,
        "tickets/planner.html",
        {
            "days": [{"date": day, "holiday": holidays.get(day)} for day in days],
            "first_day": first,
            "last_day": last,
            "today": today,
            "monday": monday,
            "previous": monday - timedelta(days=7),
            "following": monday + timedelta(days=7),
            "week_number": monday.isocalendar()[1],
            "rows": rows,
            "unassigned": unassigned,
            "show_unassigned": any(c["items"] for c in unassigned),
            "pool": [(_ticket_item(t), t) for t in pool.order_by("assignee_id", "due_at")[:120]],
            "backlog": [(_ticket_item(t), t) for t in backlog.order_by("due_at")[:80]],
            "missed": [(_ticket_item(t), t) for t in missed.order_by("planned_for")[:40]],
            "absences": week_absences,
            "absence_form": AbsenceForm(initial={"user": request.user, "start_date": first}),
            "teams": Team.objects.all(),
            "team_id": team_id,
        },
    )


@require_POST
@staff_required
def planner_move(request):
    """Karte auf einen anderen Tag oder Bearbeiter ziehen."""
    try:
        data = json.loads(request.body)
        kind, pk = data["kind"], int(data["id"])
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"ok": False}, status=400)
    day = _safe_date(data.get("date"))
    keep_user = bool(data.get("keep_user"))

    assignee = None
    if not keep_user and data.get("user"):
        assignee = _staff().filter(pk=data["user"]).first()
        if assignee is None:
            return JsonResponse({"ok": False}, status=400)

    if kind == "ticket":
        ticket = get_object_or_404(Ticket, pk=pk)
        old_day, old_assignee, old_pool = ticket.planned_for, ticket.assignee_id, ticket.pool_week
        ticket.planned_for = day
        if not keep_user:
            ticket.assignee = assignee
        # Ablegen im Wochenpool bzw. zurück zu den ungeplanten Tickets
        pool_day = _safe_date(data.get("pool"))
        if pool_day is not None:
            ticket.pool_week = pool_day - timedelta(days=pool_day.weekday())
        elif data.get("unpool"):
            ticket.pool_week = None
        ticket.save()
        before = old_day.strftime("%d.%m.%Y") if old_day else "ungeplant"
        after = day.strftime("%d.%m.%Y") if day else "ungeplant"
        text = f"Planung: {before} → {after}"
        if ticket.pool_week != old_pool:
            if ticket.pool_week:
                text += f"; in den Wochenpool KW {ticket.pool_week.isocalendar()[1]}"
            else:
                text += "; aus dem Wochenpool genommen"
        if ticket.assignee_id != old_assignee:
            text += f"; Bearbeiter: {_name(ticket.assignee) if ticket.assignee else '–'}"
            if ticket.assignee_id:
                notify.staff_assigned(ticket, request.user)
        log(ticket, request.user, text)
    elif kind == "task":
        task = get_object_or_404(Task, pk=pk)
        task.planned_for = day
        if not keep_user:
            task.assignee = assignee
        task.save()
    else:
        return JsonResponse({"ok": False}, status=400)
    return JsonResponse({"ok": True})


@require_POST
@staff_required
def absence_add(request):
    form = AbsenceForm(request.POST)
    if form.is_valid():
        form.save()
    else:
        errors = " ".join(e for errs in form.errors.values() for e in errs)
        messages.error(request, f"Abwesenheit nicht gespeichert. {errors}")
    return _back(request)


@require_POST
@staff_required
def absence_delete(request, pk):
    get_object_or_404(Absence, pk=pk).delete()
    return _back(request)


@staff_required
def planner_settings(request):
    """Eigene Tageskapazität und die Adresse des Kalender-Feeds."""
    profile = profile_for(request.user)
    if request.method == "POST" and "new_token" in request.POST:
        profile.calendar_token = generate_calendar_token()
        profile.save()
        messages.success(request, "Neue Kalender-Adresse erzeugt. Die alte gilt nicht mehr.")
        return redirect("tickets:planner_settings")
    form = ProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Gespeichert.")
        return redirect("tickets:planner_settings")
    feed = settings.SITE_URL + reverse("calendar_feed", args=[profile.calendar_token])
    return render(
        request, "tickets/planner_settings.html", {"form": form, "feed_url": feed}
    )


# --- Kalender-Feed für Outlook & Co. -------------------------------------------

def calendar_feed(request, token):
    """Geplante Tickets und Aufgaben eines Bearbeiters als abonnierbarer Kalender.

    Kalenderprogramme können sich nicht anmelden; der geheime Teil der Adresse
    ist der Zugangsschutz.
    """
    profile = PlannerProfile.objects.select_related("user").filter(calendar_token=token).first()
    if profile is None or not profile.user.is_active:
        raise Http404
    user = profile.user
    since = timezone.localdate() - timedelta(days=60)
    host = request.get_host().split(":")[0]

    def hours(minutes):
        return f" ({minutes // 60}:{minutes % 60:02d} h)" if minutes else ""

    events = []
    tickets = Ticket.objects.filter(
        assignee=user, planned_for__gte=since, merged_into__isnull=True
    )
    for ticket in tickets:
        done = "✓ " if not ticket.is_open else ""
        events.append(
            {
                "uid": f"ticket-{ticket.pk}@{host}",
                "date": ticket.planned_for,
                "summary": f"{done}#{ticket.pk} {ticket.title}{hours(ticket.estimated_minutes)}",
                "description": (
                    f"Status: {ticket.get_status_display()}\n"
                    f"Priorität: {ticket.get_priority_display()}\n"
                    f"{settings.SITE_URL}{ticket.get_absolute_url()}"
                ),
                "url": f"{settings.SITE_URL}{ticket.get_absolute_url()}",
            }
        )
    tasks = Task.objects.filter(assignee=user, planned_for__gte=since).select_related("project")
    for task in tasks:
        done = "✓ " if task.status == Task.Status.DONE else ""
        events.append(
            {
                "uid": f"task-{task.pk}@{host}",
                "date": task.planned_for,
                "summary": f"{done}{task.project.name}: {task.title}{hours(task.estimated_minutes)}",
                "description": f"{settings.SITE_URL}{task.get_absolute_url()}",
                "url": f"{settings.SITE_URL}{task.get_absolute_url()}",
            }
        )
    body = build_calendar(f"Helpdesk {_name(user)}", events, timezone.now())
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response


# --- Wiederkehrende Tickets ---------------------------------------------------

@staff_required
def recurring_list(request):
    items = RecurringTicket.objects.select_related("assignee", "team", "category")
    return render(request, "tickets/recurring_list.html", {"items": items})


@staff_required
def recurring_edit(request, pk=None):
    item = get_object_or_404(RecurringTicket, pk=pk) if pk else None
    if item and request.method == "POST" and "delete" in request.POST:
        item.delete()
        messages.info(request, "Wiederkehrendes Ticket gelöscht.")
        return redirect("tickets:recurring")
    form = RecurringForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        if item is None:
            saved.requester = request.user
        if "next_run" in form.changed_data or saved.anchor_day is None:
            # Merkt sich den Monatstag, damit z. B. "am 31." erhalten bleibt.
            saved.anchor_day = saved.next_run.day
        saved.save()
        messages.success(request, "Gespeichert.")
        return redirect("tickets:recurring")
    return render(request, "tickets/recurring_form.html", {"form": form, "item": item})
