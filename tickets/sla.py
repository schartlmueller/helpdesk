"""Zielzeiten (SLA), wahlweise nur innerhalb der Geschäftszeiten gerechnet."""

from datetime import timedelta


def add_business_time(start, hours, opens, closes, weekdays, holidays=()):
    """Addiert ``hours`` Arbeitsstunden auf ``start``.

    ``start`` ist ein Zeitpunkt in Ortszeit, ``opens``/``closes`` sind
    Uhrzeiten, ``weekdays`` die Arbeitstage (0 = Montag), ``holidays`` eine
    Menge freier Tage (Feiertage, Betriebsurlaub).
    """
    remaining = timedelta(hours=hours)
    current = start
    for _ in range(3700):  # Sicherheitsgrenze, rund zehn Jahre
        if current.weekday() in weekdays and current.date() not in holidays:
            day_open = current.replace(
                hour=opens.hour, minute=opens.minute, second=0, microsecond=0
            )
            day_close = current.replace(
                hour=closes.hour, minute=closes.minute, second=0, microsecond=0
            )
            if current < day_open:
                current = day_open
            if current < day_close:
                available = day_close - current
                if remaining <= available:
                    return current + remaining
                remaining -= available
        current = (current + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    return current


def business_seconds_between(start, end, opens, closes, weekdays, holidays=()):
    """Arbeitszeit in Sekunden zwischen zwei Zeitpunkten (beide in Ortszeit)."""
    total = 0.0
    current = start
    for _ in range(3700):
        if current >= end:
            break
        if current.weekday() in weekdays and current.date() not in holidays:
            day_open = current.replace(
                hour=opens.hour, minute=opens.minute, second=0, microsecond=0
            )
            day_close = current.replace(
                hour=closes.hour, minute=closes.minute, second=0, microsecond=0
            )
            begin, finish = max(current, day_open), min(end, day_close)
            if finish > begin:
                total += (finish - begin).total_seconds()
        current = (current + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    return total


def shift_for_pause(deadline, paused_at, resumed_at):
    """Verschiebt eine Zielzeit um die Dauer einer Pause.

    Solange ein Ticket auf Rückmeldung oder auf Dritte wartet, läuft die Uhr
    nicht. Gezählt wird nur die Arbeitszeit innerhalb der Pause.
    """
    from django.conf import settings
    from django.utils import timezone

    from core.models import Holiday

    if resumed_at <= paused_at:
        return deadline
    if not settings.SLA_BUSINESS_HOURS:
        return deadline + (resumed_at - paused_at)
    start, end = timezone.localtime(paused_at), timezone.localtime(resumed_at)
    holidays = set(
        Holiday.objects.filter(date__gte=start.date()).values_list("date", flat=True)
    )
    args = (settings.BUSINESS_OPEN, settings.BUSINESS_CLOSE, settings.BUSINESS_DAYS, holidays)
    paused_hours = business_seconds_between(start, end, *args) / 3600
    return add_business_time(timezone.localtime(deadline), paused_hours, *args)


def _deadline(hours, start):
    from django.conf import settings
    from django.utils import timezone

    from core.models import Holiday

    if not settings.SLA_BUSINESS_HOURS:
        return start + timedelta(hours=hours)
    local = timezone.localtime(start)
    holidays = set(
        Holiday.objects.filter(date__gte=local.date()).values_list("date", flat=True)
    )
    return add_business_time(
        local,
        hours,
        settings.BUSINESS_OPEN,
        settings.BUSINESS_CLOSE,
        settings.BUSINESS_DAYS,
        holidays,
    )


def due_for(priority, start):
    """Zielzeit bis zur Lösung."""
    from django.conf import settings

    return _deadline(settings.SLA_HOURS.get(priority, settings.SLA_HOURS["normal"]), start)


def response_due_for(priority, start):
    """Zielzeit bis zur ersten Antwort an den Melder."""
    from django.conf import settings

    table = settings.SLA_RESPONSE_HOURS
    return _deadline(table.get(priority, table["normal"]), start)
