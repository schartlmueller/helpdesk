from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def duration(seconds):
    """Sekunden als Stunden:Minuten, z. B. 3900 -> "1:05 h"."""
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d} h"


@register.filter
def minutes(value):
    """Minuten als Stunden:Minuten, z. B. 90 -> "1:30 h"."""
    try:
        return duration(int(value or 0) * 60)
    except (TypeError, ValueError):
        return ""


@register.filter
def md(text):
    """Markdown als HTML. nh3 entfernt alles Gefährliche (Skripte usw.)."""
    import markdown
    import nh3

    rendered = markdown.markdown(
        text or "", extensions=["extra", "sane_lists", "nl2br"]
    )
    return mark_safe(nh3.clean(rendered))
