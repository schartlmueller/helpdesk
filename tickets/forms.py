import re

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.utils import timezone

from core.antivirus import ScanError, scan

from .models import Comment, Ticket


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Dateifeld, das mehrere Dateien annimmt, Größe prüft und auf Viren scannt."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        kwargs.setdefault("required", False)
        kwargs.setdefault("label", "Anhänge")
        kwargs.setdefault(
            "help_text", f"Mehrere Dateien möglich, je höchstens {settings.MAX_UPLOAD_MB} MB."
        )
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            files = [single_clean(item, initial) for item in data]
        elif data:
            files = [single_clean(data, initial)]
        else:
            files = []
        files = [f for f in files if f]
        limit = settings.MAX_UPLOAD_MB * 1024 * 1024
        for f in files:
            if f.size > limit:
                raise forms.ValidationError(
                    f"„{f.name}“ ist größer als {settings.MAX_UPLOAD_MB} MB."
                )
            try:
                virus = scan(f)
            except ScanError:
                raise forms.ValidationError(
                    "Die Virenprüfung ist gerade nicht erreichbar. Bitte später erneut versuchen."
                )
            if virus:
                raise forms.ValidationError(
                    f"„{f.name}“ wurde abgelehnt: Virenfund ({virus})."
                )
        return files


class CameraField(MultipleFileField):
    """Öffnet am Handy direkt die Kamera; am Computer wählt man eine Bilddatei."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget",
            MultipleFileInput(attrs={"accept": "image/*", "capture": "environment"}),
        )
        kwargs.setdefault("label", "Foto aufnehmen")
        kwargs.setdefault(
            "help_text", "Am Handy öffnet sich die Kamera, z. B. für Fehlermeldung oder Typenschild."
        )
        super().__init__(*args, **kwargs)


def uploaded_files(cleaned_data):
    """Alle hochgeladenen Dateien eines Formulars: Anhänge und Fotos."""
    return list(cleaned_data.get("files") or []) + list(cleaned_data.get("photos") or [])


def clean_address_list(value):
    addresses = [a for a in re.split(r"[,;\s]+", value or "") if a]
    for address in addresses:
        validate_email(address)
    return ", ".join(dict.fromkeys(addresses))


def add_requester_fields(form):
    """Felder, mit denen Bearbeiter ein Ticket für jemand anderen erfassen,
    z. B. nach einem Anruf."""
    form.fields["requester"] = forms.ModelChoiceField(
        label="Im Namen von",
        queryset=get_user_model().objects.filter(is_active=True).order_by("username"),
        required=False,
        help_text="Leer lassen, wenn du das Ticket für dich selbst anlegst.",
    )
    form.fields["requester_email"] = forms.EmailField(
        label="oder neue E-Mail-Adresse",
        required=False,
        help_text="Für Personen ohne Konto. Das Konto wird automatisch angelegt.",
    )
    form.order_fields(["requester", "requester_email"])


class TicketCreateForm(forms.ModelForm):
    photos = CameraField()
    files = MultipleFileField()

    class Meta:
        model = Ticket
        fields = ["title", "description", "kind", "category", "priority", "cc"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 7}),
            "cc": forms.TextInput(),
        }

    def __init__(self, *args, staff=False, **kwargs):
        super().__init__(*args, **kwargs)
        if staff:
            add_requester_fields(self)

    def clean_cc(self):
        return clean_address_list(self.cleaned_data.get("cc"))


class TicketUpdateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = [
            "status",
            "kind",
            "priority",
            "assignee",
            "team",
            "category",
            "organization",
            "project",
            "cc",
            "follow_up_on",
            "planned_for",
            "estimated_minutes",
        ]
        widgets = {
            "planned_for": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "follow_up_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "cc": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = get_user_model().objects.filter(
            is_staff=True, is_active=True
        )
        # "Gelöst" wird nur über das Lösungsformular gesetzt, damit immer
        # eine Lösungsbeschreibung vorhanden ist.
        if self.instance.status != Ticket.Status.RESOLVED:
            self.fields["status"].choices = [
                c for c in Ticket.Status.choices if c[0] != Ticket.Status.RESOLVED
            ]

    def clean_cc(self):
        return clean_address_list(self.cleaned_data.get("cc"))


class CommentForm(forms.ModelForm):
    photos = CameraField()
    files = MultipleFileField()

    class Meta:
        model = Comment
        fields = ["body", "internal"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, staff=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not staff:
            del self.fields["internal"]


class ResolveForm(forms.Form):
    solution = forms.CharField(
        label="Lösung",
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="Wird dem Melder als Antwort geschickt und dient als Grundlage für den Wissensartikel.",
    )
    create_article = forms.BooleanField(
        label="Entwurf für die Wissensbasis anlegen",
        required=False,
        initial=True,
    )
    resolve_children = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, open_children=0, **kwargs):
        super().__init__(*args, **kwargs)
        if open_children:
            self.fields["resolve_children"].label = (
                f"Die {open_children} offenen Untertickets mit derselben Lösung lösen "
                "und deren Melder benachrichtigen"
            )
        else:
            del self.fields["resolve_children"]


class LinkForm(forms.Form):
    """Verknüpft dieses Ticket mit einem anderen."""

    target = forms.IntegerField(label="Ticket Nr.", min_value=1)
    relation = forms.ChoiceField(
        label="Beziehung",
        choices=[
            ("child", "ist Unterticket von diesem Ticket"),
            ("parent", "ist das Hauptticket zu diesem Ticket"),
            ("related", "hängt mit diesem Ticket zusammen"),
        ],
    )


class ManualTimeForm(forms.Form):
    """Zeit nachtragen, wenn die Uhr nicht lief."""

    date = forms.DateField(
        label="Datum",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    start = forms.TimeField(
        label="Beginn", widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
    )
    minutes = forms.IntegerField(label="Dauer (Minuten)", min_value=1, max_value=1440)
    note = forms.CharField(label="Notiz", max_length=200, required=False)


class ChecklistForm(forms.Form):
    """Einzelnen Punkt hinzufügen oder eine Vorlage einfügen."""

    text = forms.CharField(label="Neuer Punkt", max_length=300, required=False)
    template = forms.ModelChoiceField(
        label="oder Vorlage einfügen", queryset=None, required=False
    )

    def __init__(self, *args, **kwargs):
        from .models import ChecklistTemplate

        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = ChecklistTemplate.objects.all()


class MergeForm(forms.Form):
    target = forms.IntegerField(label="Zusammenführen in Ticket Nr.", min_value=1)
