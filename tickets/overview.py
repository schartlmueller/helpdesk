"""Zahlen und Diagramme für die Übersicht: Zugang, Abgang und Bestand an Tickets."""

from datetime import datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .charts import bar_chart, line_chart
from .models import Ticket

CLOSED_STATES = [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]
PERIODS = (14, 30, 90)


def _local_day(moment):
    return timezone.localtime(moment).date()


def build(days=30, kind=""):
    """Bestandsverlauf der letzten ``days`` Tage, optional nur für eine Art."""
    if days not in PERIODS:
        days = 30
    today = timezone.localdate()
    first = today - timedelta(days=days - 1)
    start = timezone.make_aware(datetime.combine(first, time.min))

    tickets = Ticket.objects.filter(merged_into__isnull=True)
    if kind in Ticket.Kind.values:
        tickets = tickets.filter(kind=kind)
    elif kind == "none":
        tickets = tickets.filter(kind="")

    # Bestand zu Beginn: vorher angelegt und zu Beginn noch nicht erledigt
    opening = tickets.filter(created_at__lt=start).filter(
        Q(status__in=CLOSED_STATES, closed_at__gte=start) | ~Q(status__in=CLOSED_STATES)
    ).count()

    day_list = [first + timedelta(days=i) for i in range(days)]
    created = dict.fromkeys(day_list, 0)
    closed = dict.fromkeys(day_list, 0)
    for created_at in tickets.filter(created_at__gte=start).values_list("created_at", flat=True):
        created[_local_day(created_at)] = created.get(_local_day(created_at), 0) + 1
    done = tickets.filter(status__in=CLOSED_STATES, closed_at__gte=start)
    for closed_at in done.values_list("closed_at", flat=True):
        day = _local_day(closed_at)
        if day in closed:
            closed[day] += 1

    stock, current = [], opening
    for day in day_list:
        current = max(0, current + created[day] - closed[day])
        stock.append(current)

    labels = [day.strftime("%d.%m.") for day in day_list]
    line_tips = [
        f"{label} · {value} offen" for label, value in zip(labels, stock)
    ]
    rows = [
        {"date": day, "created": created[day], "closed": closed[day], "open": value}
        for day, value in zip(day_list, stock)
    ]

    # Säulen: bei 90 Tagen je Kalenderwoche, sonst je Tag
    if days > 31:
        weeks = {}
        for day in day_list:
            year, week, _ = day.isocalendar()
            entry = weeks.setdefault((year, week), [0, 0])
            entry[0] += created[day]
            entry[1] += closed[day]
        bar_labels = [f"KW {week}" for _, week in weeks]
        new_values = [v[0] for v in weeks.values()]
        done_values = [v[1] for v in weeks.values()]
        bar_unit = "je Kalenderwoche"
    else:
        bar_labels = labels
        new_values = [created[day] for day in day_list]
        done_values = [closed[day] for day in day_list]
        bar_unit = "je Tag"
    bar_tips = [
        f"{label} · {a} neu · {b} erledigt"
        for label, a, b in zip(bar_labels, new_values, done_values)
    ]

    total_created = sum(created.values())
    total_closed = sum(closed.values())
    open_now = tickets.exclude(status__in=CLOSED_STATES)
    kind_names = dict(Ticket.Kind.choices)
    by_kind = [
        {
            "key": row["kind"] or "none",
            "name": kind_names.get(row["kind"], "Nicht eingestuft"),
            "count": row["n"],
        }
        for row in open_now.values("kind").annotate(n=Count("id")).order_by("-n")
    ]

    return {
        "days": days,
        "periods": PERIODS,
        "kind": kind,
        "kind_choices": Ticket.Kind.choices,
        "first": first,
        "today": today,
        "new_today": created[today],
        "total_created": total_created,
        "total_closed": total_closed,
        "open_count": stock[-1],
        "opening": opening,
        "change": stock[-1] - opening,
        "by_kind": by_kind,
        "rows": rows,
        "bar_unit": bar_unit,
        "line_svg": line_chart(
            labels, stock, line_tips, f"Offene Tickets der letzten {days} Tage"
        ),
        "bar_svg": bar_chart(
            bar_labels, new_values, done_values, bar_tips,
            f"Neue und erledigte Tickets {bar_unit}",
        ),
        "newest": tickets.select_related("requester").order_by("-created_at")[:8],
    }
