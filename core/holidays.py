"""Gesetzliche Feiertage. Ohne Django, einzeln testbar."""

from datetime import date, timedelta


def easter_sunday(year):
    """Ostersonntag nach der Gaußschen Osterformel (gregorianischer Kalender)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def austrian_holidays(year):
    """Die 13 bundesweiten gesetzlichen Feiertage in Österreich."""
    easter = easter_sunday(year)
    return [
        (date(year, 1, 1), "Neujahr"),
        (date(year, 1, 6), "Heilige Drei Könige"),
        (easter + timedelta(days=1), "Ostermontag"),
        (date(year, 5, 1), "Staatsfeiertag"),
        (easter + timedelta(days=39), "Christi Himmelfahrt"),
        (easter + timedelta(days=50), "Pfingstmontag"),
        (easter + timedelta(days=60), "Fronleichnam"),
        (date(year, 8, 15), "Mariä Himmelfahrt"),
        (date(year, 10, 26), "Nationalfeiertag"),
        (date(year, 11, 1), "Allerheiligen"),
        (date(year, 12, 8), "Mariä Empfängnis"),
        (date(year, 12, 25), "Christtag"),
        (date(year, 12, 26), "Stefanitag"),
    ]


def german_holidays(year):
    """Die neun bundesweit einheitlichen Feiertage in Deutschland."""
    easter = easter_sunday(year)
    return [
        (date(year, 1, 1), "Neujahr"),
        (easter - timedelta(days=2), "Karfreitag"),
        (easter + timedelta(days=1), "Ostermontag"),
        (date(year, 5, 1), "Tag der Arbeit"),
        (easter + timedelta(days=39), "Christi Himmelfahrt"),
        (easter + timedelta(days=50), "Pfingstmontag"),
        (date(year, 10, 3), "Tag der Deutschen Einheit"),
        (date(year, 12, 25), "1. Weihnachtstag"),
        (date(year, 12, 26), "2. Weihnachtstag"),
    ]


COUNTRIES = {"AT": austrian_holidays, "DE": german_holidays}


def holidays_for(country, year):
    builder = COUNTRIES.get((country or "").upper())
    return builder(year) if builder else []
