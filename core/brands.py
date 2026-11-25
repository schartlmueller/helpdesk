"""Austauschbares Erscheinungsbild.

Jedes Design hat einen Namen, eine kleine Farbdatei unter static/css/ und
optional ein eigenes Logo. Welches Design gilt, entscheidet (in dieser
Reihenfolge): die Vorschau eines Bearbeiters, der Hostname der Anfrage
(BRAND_HOSTS), sonst die Grundeinstellung BRAND.

Ein Logo wird automatisch verwendet, wenn die Datei
static/brand/<schlüssel>/logo.svg oder logo.png vorhanden ist. Für das dunkle
Design kann daneben logo-dark.svg bzw. logo-dark.png liegen.
"""

from functools import lru_cache

from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

BRANDS = {
    "helpdesk": {"name": "Helpdesk", "strong": "Helpdesk", "light": ""},
    "ebner": {"name": "ebner.ticket", "strong": "ebner", "light": ".ticket"},
    "forstenlechner": {
        "name": "forstenlechner.ticket",
        "strong": "forstenlechner",
        "light": ".ticket",
    },
}


@lru_cache(maxsize=None)
def _logo(key, variant=""):
    for extension in ("svg", "png"):
        path = f"brand/{key}/logo{variant}.{extension}"
        if finders.find(path):
            return path
    return ""


def brand_key(request=None):
    if request is not None:
        session = getattr(request, "session", None)
        preview = session.get("brand_preview") if session is not None else None
        if preview in BRANDS:
            return preview
        try:
            host = request.get_host().split(":")[0].lower()
        except Exception:  # ungültiger Host-Kopf: Grundeinstellung verwenden
            host = ""
        mapped = settings.BRAND_HOSTS.get(host)
        if mapped in BRANDS:
            return mapped
    return settings.BRAND if settings.BRAND in BRANDS else "helpdesk"


def brand_for(request=None):
    key = brand_key(request)
    brand = dict(BRANDS[key], key=key)
    brand["css"] = "" if key == "helpdesk" else static(f"css/brand-{key}.css")
    logo, logo_dark = _logo(key), _logo(key, "-dark")
    brand["logo"] = static(logo) if logo else ""
    brand["logo_dark"] = static(logo_dark) if logo_dark else ""
    return brand
