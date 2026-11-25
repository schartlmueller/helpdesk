"""Anfrage-Formulare: baut aus einer Vorlage ein Eingabeformular und daraus ein Ticket."""

from django import forms

from .forms import CameraField, MultipleFileField
from .models import RequestField


def _field_for(spec):
    common = {"label": spec.label, "required": spec.required, "help_text": spec.help_text}
    kind = spec.kind
    if kind == RequestField.Kind.TEXTAREA:
        return forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), **common)
    if kind == RequestField.Kind.SELECT:
        choices = [("", "– bitte wählen –")] + [(c, c) for c in spec.choice_list]
        return forms.ChoiceField(choices=choices, **common)
    if kind == RequestField.Kind.DATE:
        return forms.DateField(
            widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), **common
        )
    if kind == RequestField.Kind.NUMBER:
        return forms.DecimalField(**common)
    if kind == RequestField.Kind.CHECKBOX:
        return forms.BooleanField(**common)
    return forms.CharField(max_length=500, **common)


def build_form(request_form, data=None, files=None):
    """Gibt (Formular, Liste der Feld-Vorlagen) zurück."""
    specs = list(request_form.fields.all())
    fields = {f"f{spec.pk}": _field_for(spec) for spec in specs}
    fields["photos"] = CameraField()
    fields["files"] = MultipleFileField()
    form_class = type("DynamicRequestForm", (forms.Form,), fields)
    return form_class(data, files), specs


def _text(value):
    if value is True:
        return "Ja"
    if value is False:
        return "Nein"
    if value in (None, ""):
        return "–"
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y")
    return str(value)


def ticket_text(request_form, specs, cleaned):
    """Betreff und Beschreibung des Tickets aus den Eingaben."""
    lines, in_title = [], []
    for spec in specs:
        value = _text(cleaned.get(f"f{spec.pk}"))
        lines.append(f"{spec.label}: {value}")
        if spec.in_title and value != "–":
            in_title.append(value)
    title = request_form.name
    if in_title:
        title = f"{title}: {', '.join(in_title)}"
    return title[:200], "\n".join(lines) or request_form.name
