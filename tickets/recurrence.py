"""Terminberechnung für wiederkehrende Tickets. Ohne Django, einzeln testbar."""

import calendar
from datetime import date, timedelta

MONTHS = {"monthly": 1, "quarterly": 3, "halfyearly": 6, "yearly": 12}
DAYS = {"weekly": 7, "biweekly": 14}


def add_months(day, months, anchor_day=None):
    """Verschiebt um ganze Monate. ``anchor_day`` hält z. B. den 31. fest,
    damit der Termin nach einem kurzen Monat nicht dauerhaft auf den 28. rutscht."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    wanted = anchor_day or day.day
    return date(year, month, min(wanted, calendar.monthrange(year, month)[1]))


def next_date(current, interval, weekdays, anchor_day=None, holidays=()):
    """Nächster Termin nach ``current`` für das Intervall.

    "Jeden Arbeitstag" überspringt Wochenenden und Feiertage; die übrigen
    Intervalle behalten ihren Kalendertag.
    """
    if interval == "daily":
        following = current + timedelta(days=1)
        for _ in range(400):
            if following.weekday() in weekdays and following not in holidays:
                break
            following += timedelta(days=1)
        return following
    if interval in DAYS:
        return current + timedelta(days=DAYS[interval])
    return add_months(current, MONTHS.get(interval, 1), anchor_day)
