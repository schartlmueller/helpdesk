"""Erzeugt einen Kalender im iCalendar-Format (RFC 5545) mit Ganztagesterminen.

Outlook, Google Kalender und Apple Kalender können so einen Kalender über
seine Adresse abonnieren. Ohne Django, einzeln testbar.
"""

from datetime import timedelta


def _escape(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\n")
        .replace("\n", "\\n")
    )


def _fold(line):
    """Zeilen dürfen höchstens 75 Bytes lang sein; Fortsetzungen beginnen mit Leerzeichen."""
    parts, current, size = [], "", 0
    for char in line:
        width = len(char.encode("utf-8"))
        limit = 75 if not parts else 74
        if size + width > limit:
            parts.append(current)
            current, size = "", 0
        current += char
        size += width
    parts.append(current)
    return "\r\n ".join(parts)


def build_calendar(name, events, stamp):
    """``events``: Liste von dicts mit uid, date, summary, description, url.
    ``stamp``: Zeitpunkt der Erzeugung (UTC)."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Helpdesk//Planung//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        "X-PUBLISHED-TTL:PT1H",
    ]
    stamp_text = stamp.strftime("%Y%m%dT%H%M%SZ")
    for event in events:
        day = event["date"]
        lines += [
            "BEGIN:VEVENT",
            f"UID:{event['uid']}",
            f"DTSTAMP:{stamp_text}",
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_escape(event['summary'])}",
            f"DESCRIPTION:{_escape(event.get('description', ''))}",
        ]
        if event.get("url"):
            lines.append(f"URL:{event['url']}")
        # Ganztagestermine sollen den Kalender nicht als "beschäftigt" blockieren.
        lines += ["TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
