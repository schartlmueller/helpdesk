"""Regelmäßige Aufgaben des Hintergrunddienstes."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.holidays import holidays_for
from core.models import Holiday

from . import notify
from .models import RecurringTicket, Ticket, TimeEntry
from .recurrence import next_date
from .services import after_ticket_created, apply_checklist, log

CLOSED_STATES = [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]


def escalate_overdue():
    """Meldet jedes überfällige Ticket einmal an Bearbeiter und Team."""
    now = timezone.now()
    overdue = (
        Ticket.objects.exclude(status__in=CLOSED_STATES)
        # Wartende Tickets sind pausiert und gelten nicht als überfällig.
        .filter(due_at__lt=now, escalated_at__isnull=True, sla_paused_at__isnull=True)
        .select_related("assignee", "team", "requester")
    )
    count = 0
    for ticket in overdue:
        Ticket.objects.filter(pk=ticket.pk).update(escalated_at=now)
        log(ticket, None, "Zielzeit überschritten, Eskalation verschickt")
        notify.staff_escalation(ticket)
        count += 1

    # Zweite Zielzeit: Der Melder hat noch keine erste Antwort bekommen.
    unanswered = (
        Ticket.objects.exclude(status__in=CLOSED_STATES)
        .filter(
            first_response_at__isnull=True,
            response_due_at__lt=now,
            response_escalated_at__isnull=True,
        )
        .select_related("assignee", "team", "requester")
    )
    for ticket in unanswered:
        Ticket.objects.filter(pk=ticket.pk).update(response_escalated_at=now)
        log(ticket, None, "Reaktionszeit überschritten, Hinweis verschickt")
        notify.staff_response_overdue(ticket)
        count += 1
    return count


def stop_stale_timers():
    """Stoppt Uhren, die länger als TIMER_MAX_HOURS ohne Pause laufen."""
    limit = timedelta(hours=settings.TIMER_MAX_HOURS)
    stale = TimeEntry.objects.filter(
        ended_at__isnull=True, started_at__lt=timezone.now() - limit
    ).select_related("ticket", "user")
    count = 0
    for entry in stale:
        entry.ended_at = entry.started_at + limit
        entry.note = (entry.note + " automatisch gestoppt").strip()[:200]
        entry.save()
        if entry.ticket_id:
            log(entry.ticket, None, f"Uhr von {entry.user} automatisch gestoppt")
        count += 1
    return count


def purge_old_tickets():
    """Löscht abgeschlossene Tickets samt Anhängen nach der Aufbewahrungsfrist."""
    if settings.RETENTION_DAYS <= 0:
        return 0
    cutoff = timezone.now() - timedelta(days=settings.RETENTION_DAYS)
    old = Ticket.objects.filter(status__in=CLOSED_STATES, updated_at__lt=cutoff)
    count = 0
    for ticket in old.iterator():
        ticket.delete()
        count += 1
    return count


def create_recurring_tickets(today=None):
    """Legt fällige wiederkehrende Tickets an und setzt den nächsten Termin."""
    today = today or timezone.localdate()
    holidays = set(Holiday.objects.filter(date__gte=today).values_list("date", flat=True))
    due = RecurringTicket.objects.filter(active=True).select_related(
        "category", "team", "assignee", "requester", "checklist"
    )
    count = 0
    for item in due:
        if item.next_run - timedelta(days=item.lead_days) > today:
            continue
        ticket = Ticket.objects.create(
            title=item.title,
            description=item.description,
            category=item.category,
            priority=item.priority,
            team=item.team,
            assignee=item.assignee,
            requester=item.requester,
            estimated_minutes=item.estimated_minutes,
            # Ein verpasster Termin wird auf heute gelegt statt in die Vergangenheit.
            planned_for=max(item.next_run, today),
        )
        apply_checklist(ticket, item.checklist)
        after_ticket_created(ticket, actor=None, source="wiederkehrend")
        # Nächsten Termin suchen; ausgefallene Termine werden nicht nachgeholt.
        following = item.next_run
        for _ in range(1000):
            following = next_date(
                following, item.interval, settings.BUSINESS_DAYS, item.anchor_day, holidays
            )
            if following - timedelta(days=item.lead_days) > today:
                break
        item.next_run = following
        item.last_created_at = timezone.now()
        item.save()
        count += 1
    return count


def ensure_holidays(today=None):
    """Trägt die gesetzlichen Feiertage für dieses und nächstes Jahr ein.

    Ein Jahr wird nur befüllt, solange es noch gar keine Einträge hat. Wer
    einen Feiertag löscht oder eigene ergänzt, behält also seine Änderungen.
    """
    if not settings.HOLIDAY_COUNTRY:
        return 0
    today = today or timezone.localdate()
    count = 0
    for year in (today.year, today.year + 1):
        if Holiday.objects.filter(date__year=year).exists():
            continue
        for day, name in holidays_for(settings.HOLIDAY_COUNTRY, year):
            Holiday.objects.create(date=day, name=name)
            count += 1
    return count


def process_follow_ups(today=None):
    """Wiedervorlage fällig: Bearbeiter erinnern und Ticket wieder in Bearbeitung setzen."""
    today = today or timezone.localdate()
    due = (
        Ticket.objects.exclude(status__in=CLOSED_STATES)
        .filter(follow_up_on__lte=today)
        .select_related("assignee", "team", "requester")
    )
    count = 0
    for ticket in due:
        ticket.follow_up_on = None
        if ticket.status in Ticket.PAUSED_STATES:
            ticket.status = Ticket.Status.OPEN
        ticket.save()
        log(ticket, None, "Wiedervorlage fällig, Ticket wieder in Bearbeitung")
        notify.staff_follow_up(ticket)
        count += 1
    return count


def remind_and_close():
    """Erinnert wartende Melder und schließt Tickets, auf die niemand mehr antwortet."""
    now = timezone.now()
    count = 0

    waiting = Ticket.objects.filter(
        status=Ticket.Status.WAITING, sla_paused_at__isnull=False
    ).select_related("requester")
    if settings.WAITING_CLOSE_DAYS > 0:
        limit = now - timedelta(days=settings.WAITING_CLOSE_DAYS)
        for ticket in waiting.filter(sla_paused_at__lt=limit):
            ticket.status = Ticket.Status.CLOSED
            ticket.save()
            log(ticket, None, "Automatisch geschlossen: keine Rückmeldung des Melders")
            notify.closed_without_reply(ticket)
            count += 1
    if settings.WAITING_REMINDER_DAYS > 0:
        limit = now - timedelta(days=settings.WAITING_REMINDER_DAYS)
        for ticket in waiting.filter(sla_paused_at__lt=limit, waiting_reminded_at__isnull=True):
            Ticket.objects.filter(pk=ticket.pk).update(waiting_reminded_at=now)
            log(ticket, None, "Melder an ausstehende Rückmeldung erinnert")
            notify.waiting_reminder(ticket)
            count += 1

    if settings.AUTO_CLOSE_DAYS > 0:
        limit = now - timedelta(days=settings.AUTO_CLOSE_DAYS)
        resolved = Ticket.objects.filter(status=Ticket.Status.RESOLVED, resolved_at__lt=limit)
        for ticket in resolved:
            ticket.status = Ticket.Status.CLOSED
            ticket.save()
            log(ticket, None, "Automatisch geschlossen nach Lösung ohne Einwand")
            count += 1
    return count
