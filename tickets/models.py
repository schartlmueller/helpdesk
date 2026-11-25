import os
import re
import secrets
import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from .sla import due_for, response_due_for, shift_for_pause


class Team(models.Model):
    """Gruppe von Bearbeitern, an die Tickets geleitet werden."""

    name = models.CharField("Name", max_length=100, unique=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name="Mitglieder",
        blank=True,
        related_name="helpdesk_teams",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Team"
        verbose_name_plural = "Teams"

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField("Name", max_length=100, unique=True)
    team = models.ForeignKey(
        Team,
        verbose_name="Zuständiges Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="categories",
        help_text="Neue Tickets dieser Kategorie gehen automatisch an dieses Team.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Kategorie"
        verbose_name_plural = "Kategorien"

    def __str__(self):
        return self.name


class CannedResponse(models.Model):
    title = models.CharField("Titel", max_length=100)
    body = models.TextField("Text")

    class Meta:
        ordering = ["title"]
        verbose_name = "Textbaustein"
        verbose_name_plural = "Textbausteine"

    def __str__(self):
        return self.title


class Ticket(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Neu"
        OPEN = "open", "In Bearbeitung"
        WAITING = "waiting", "Wartet auf Rückmeldung"
        ON_HOLD = "on_hold", "Wartet auf Dritte"
        RESOLVED = "resolved", "Gelöst"
        CLOSED = "closed", "Geschlossen"

    class Priority(models.TextChoices):
        LOW = "low", "Niedrig"
        NORMAL = "normal", "Normal"
        HIGH = "high", "Hoch"
        URGENT = "urgent", "Dringend"

    class Kind(models.TextChoices):
        BUG = "bug", "Fehler"
        FEATURE = "feature", "Erweiterung"
        NICE = "nice", "Nice to have"

    title = models.CharField("Betreff", max_length=200)
    description = models.TextField("Problembeschreibung")
    kind = models.CharField(
        "Art",
        max_length=20,
        choices=Kind.choices,
        blank=True,
        help_text="Fehler, Erweiterung oder Nice to have. Leer = noch nicht eingestuft.",
    )
    status = models.CharField(
        "Status", max_length=20, choices=Status.choices, default=Status.NEW
    )
    priority = models.CharField(
        "Priorität", max_length=20, choices=Priority.choices, default=Priority.NORMAL
    )
    category = models.ForeignKey(
        Category,
        verbose_name="Kategorie",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets",
    )
    team = models.ForeignKey(
        Team,
        verbose_name="Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Gemeldet von",
        on_delete=models.CASCADE,
        related_name="requested_tickets",
    )
    organization = models.ForeignKey(
        "core.Organization",
        verbose_name="Organisation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Bearbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_tickets",
    )
    parent = models.ForeignKey(
        "self",
        verbose_name="Hauptticket",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    related = models.ManyToManyField("self", verbose_name="Hängt zusammen mit", blank=True)
    cc = models.TextField(
        "In Kopie",
        blank=True,
        help_text="Weitere E-Mail-Adressen, durch Komma getrennt. Sie erhalten alle Antworten.",
    )
    project = models.ForeignKey(
        "projects.Project",
        verbose_name="Projekt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets",
    )
    merged_into = models.ForeignKey(
        "self",
        verbose_name="Zusammengeführt in",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merged_tickets",
    )
    solution = models.TextField("Lösung", blank=True)
    estimated_minutes = models.PositiveIntegerField(
        "Geplanter Aufwand (Minuten)", null=True, blank=True
    )
    planned_for = models.DateField("Geplant für", null=True, blank=True)
    # Montag der Woche, in deren Pool das Ticket liegt. Aus dem Pool nehmen
    # sich die Bearbeiter ihre Tickets selbst.
    pool_week = models.DateField("Wochenpool", null=True, blank=True)
    due_at = models.DateTimeField("Fällig bis", null=True, blank=True)
    # Gesetzt, solange das Ticket wartet; die Zielzeit läuft dann nicht.
    sla_paused_at = models.DateTimeField("Zielzeit pausiert seit", null=True, blank=True)
    follow_up_on = models.DateField(
        "Wiedervorlage am",
        null=True,
        blank=True,
        help_text="An diesem Tag wird der Bearbeiter erinnert und das Ticket wieder in Bearbeitung gesetzt.",
    )
    waiting_reminded_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField("Eskaliert am", null=True, blank=True)
    response_due_at = models.DateTimeField("Erste Antwort bis", null=True, blank=True)
    first_response_at = models.DateTimeField("Erste Antwort am", null=True, blank=True)
    response_escalated_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField("Gelöst am", null=True, blank=True)
    # Zeitpunkt, seit dem das Ticket erledigt ist (gelöst oder geschlossen);
    # Grundlage für den Bestandsverlauf in der Übersicht.
    closed_at = models.DateTimeField("Erledigt seit", null=True, blank=True)
    created_at = models.DateTimeField("Erstellt", auto_now_add=True)
    updated_at = models.DateTimeField("Geändert", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Ticket"
        verbose_name_plural = "Tickets"

    def __str__(self):
        return f"#{self.pk} {self.title}"

    def get_absolute_url(self):
        return reverse("tickets:detail", args=[self.pk])

    # In diesen Status wartet das Ticket auf jemand anderen; die Zielzeit pausiert.
    PAUSED_STATES = ("waiting", "on_hold")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Über __dict__, damit ein nicht geladenes Feld keine Abfrage auslöst.
        self._original_status = self.__dict__.get("status")

    def refresh_from_db(self, *args, **kwargs):
        super().refresh_from_db(*args, **kwargs)
        self._original_status = self.__dict__.get("status")

    def _apply_pause(self):
        """Hält die Zielzeit an bzw. verschiebt sie beim Weiterarbeiten um die Wartezeit."""
        now = timezone.now()
        if self.status in self.PAUSED_STATES:
            if self.sla_paused_at is None:
                self.sla_paused_at = now
        elif self.sla_paused_at is not None:
            if self.due_at is not None:
                self.due_at = shift_for_pause(self.due_at, self.sla_paused_at, now)
            self.sla_paused_at = None
            self.waiting_reminded_at = None

    def save(self, *args, **kwargs):
        if self.pk is None or self.status != self._original_status:
            self._apply_pause()
            if self.is_open:
                self.closed_at = None
            elif self.closed_at is None:
                self.closed_at = timezone.now()
        if self.pk is None:
            now = timezone.now()
            if self.due_at is None:
                self.due_at = due_for(self.priority, now)
            if self.response_due_at is None:
                self.response_due_at = response_due_for(self.priority, now)
            if self.team_id is None and self.category_id is not None:
                self.team_id = self.category.team_id
            if self.organization_id is None:
                # Das Ticket gehört zur Organisation des Melders.
                from core.orgs import organization_for

                organization = organization_for(self.requester)
                if organization is not None:
                    self.organization = organization
        super().save(*args, **kwargs)
        self._original_status = self.status

    @property
    def is_open(self):
        return self.status not in (self.Status.RESOLVED, self.Status.CLOSED)

    @property
    def sla_paused(self):
        return self.sla_paused_at is not None

    @property
    def is_overdue(self):
        return (
            self.is_open
            and not self.sla_paused
            and self.due_at is not None
            and self.due_at < timezone.now()
        )

    @property
    def response_overdue(self):
        return (
            self.is_open
            and self.first_response_at is None
            and self.response_due_at is not None
            and self.response_due_at < timezone.now()
        )

    @property
    def cc_list(self):
        return [a for a in re.split(r"[,;\s]+", self.cc) if "@" in a]


class Comment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="ticket_comments",
    )
    body = models.TextField("Nachricht")
    internal = models.BooleanField(
        "Interne Notiz (für den Melder nicht sichtbar)", default=False
    )
    is_solution = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Kommentar"
        verbose_name_plural = "Kommentare"

    def __str__(self):
        return f"Kommentar zu Ticket #{self.ticket_id}"


class TicketEvent(models.Model):
    """Änderungsverlauf: wer hat wann was am Ticket geändert."""

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="events")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_events",
    )
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Verlaufseintrag"
        verbose_name_plural = "Verlaufseinträge"

    def __str__(self):
        return self.text


def attachment_path(instance, filename):
    # Zufälliger Dateiname, damit hochgeladene Namen nie im Dateisystem landen.
    ext = os.path.splitext(filename)[1].lower()[:10]
    if instance.ticket_id:
        folder = f"tickets/{instance.ticket_id}"
    else:
        folder = f"tasks/{instance.task_id}"
    return f"{folder}/{uuid.uuid4().hex}{ext}"


class Attachment(models.Model):
    """Datei an einem Ticket (optional an einer Antwort) oder an einer Projektaufgabe."""

    ticket = models.ForeignKey(
        Ticket, null=True, blank=True, on_delete=models.CASCADE, related_name="attachments"
    )
    comment = models.ForeignKey(
        Comment,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    task = models.ForeignKey(
        "projects.Task",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField("Datei", upload_to=attachment_path)
    name = models.CharField("Dateiname", max_length=255)
    size = models.PositiveIntegerField("Größe", default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_attachments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Anhang"
        verbose_name_plural = "Anhänge"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("tickets:attachment", args=[self.pk])


@receiver(post_delete, sender=Attachment)
def _delete_attachment_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)


class TimeEntry(models.Model):
    """Ein zusammenhängender Arbeitsabschnitt an einem Ticket oder einer Aufgabe.

    Solange ``ended_at`` leer ist, läuft die Uhr. Eine Pause beendet den
    Abschnitt, Fortsetzen legt einen neuen an.
    """

    ticket = models.ForeignKey(
        Ticket, null=True, blank=True, on_delete=models.CASCADE, related_name="time_entries"
    )
    task = models.ForeignKey(
        "projects.Task",
        verbose_name="Aufgabe",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="time_entries",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Bearbeiter",
        on_delete=models.CASCADE,
        related_name="time_entries",
    )
    started_at = models.DateTimeField("Beginn", default=timezone.now)
    ended_at = models.DateTimeField("Ende", null=True, blank=True)
    note = models.CharField("Notiz", max_length=200, blank=True)

    class Meta:
        ordering = ["started_at", "id"]
        verbose_name = "Zeiteintrag"
        verbose_name_plural = "Zeiteinträge"

    def __str__(self):
        return f"{self.target_label}, {self.user}"

    @property
    def running(self):
        return self.ended_at is None

    @property
    def seconds(self):
        end = self.ended_at or timezone.now()
        return max(0, int((end - self.started_at).total_seconds()))

    @property
    def target(self):
        return self.ticket if self.ticket_id else self.task

    @property
    def target_label(self):
        if self.ticket_id:
            return f"#{self.ticket_id} {self.ticket.title}"
        if self.task_id:
            return f"{self.task.project.name}: {self.task.title}"
        return "–"


# --- Planung ------------------------------------------------------------------

def generate_calendar_token():
    return secrets.token_urlsafe(24)


class PlannerProfile(models.Model):
    """Planungs-Einstellungen eines Bearbeiters."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Bearbeiter",
        on_delete=models.CASCADE,
        related_name="planner_profile",
    )
    daily_hours = models.DecimalField(
        "Verplanbare Stunden pro Tag", max_digits=4, decimal_places=2, default=8
    )
    calendar_token = models.CharField(
        max_length=64, unique=True, default=generate_calendar_token, editable=False
    )

    class Meta:
        verbose_name = "Planungsprofil"
        verbose_name_plural = "Planungsprofile"

    def __str__(self):
        return f"Planung {self.user}"

    @property
    def daily_minutes(self):
        return int(self.daily_hours * 60)


class Absence(models.Model):
    """Urlaub, Krankheit, Schulung: An diesen Tagen wird niemand verplant."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Bearbeiter",
        on_delete=models.CASCADE,
        related_name="absences",
    )
    start_date = models.DateField("Von")
    end_date = models.DateField("Bis")
    reason = models.CharField("Grund", max_length=100, blank=True)

    class Meta:
        ordering = ["start_date"]
        verbose_name = "Abwesenheit"
        verbose_name_plural = "Abwesenheiten"

    def __str__(self):
        return f"{self.user}: {self.start_date:%d.%m.}–{self.end_date:%d.%m.%Y}"


class RecurringTicket(models.Model):
    """Vorlage, aus der regelmäßig automatisch ein Ticket entsteht."""

    class Interval(models.TextChoices):
        DAILY = "daily", "Jeden Arbeitstag"
        WEEKLY = "weekly", "Wöchentlich"
        BIWEEKLY = "biweekly", "Alle zwei Wochen"
        MONTHLY = "monthly", "Monatlich"
        QUARTERLY = "quarterly", "Vierteljährlich"
        HALFYEARLY = "halfyearly", "Halbjährlich"
        YEARLY = "yearly", "Jährlich"

    title = models.CharField("Betreff", max_length=200)
    description = models.TextField("Beschreibung")
    category = models.ForeignKey(
        Category, verbose_name="Kategorie", null=True, blank=True, on_delete=models.SET_NULL
    )
    priority = models.CharField(
        "Priorität",
        max_length=20,
        choices=Ticket.Priority.choices,
        default=Ticket.Priority.NORMAL,
    )
    team = models.ForeignKey(
        Team, verbose_name="Team", null=True, blank=True, on_delete=models.SET_NULL
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Bearbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recurring_assigned",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Gemeldet von",
        on_delete=models.CASCADE,
        related_name="recurring_requested",
    )
    estimated_minutes = models.PositiveIntegerField(
        "Geplanter Aufwand (Minuten)", null=True, blank=True
    )
    interval = models.CharField(
        "Wiederholung", max_length=20, choices=Interval.choices, default=Interval.MONTHLY
    )
    next_run = models.DateField(
        "Nächster Termin", help_text="An diesem Tag ist das nächste Ticket eingeplant."
    )
    lead_days = models.PositiveSmallIntegerField(
        "Vorlauf (Tage)",
        default=0,
        help_text="Das Ticket wird so viele Tage vor dem Termin angelegt.",
    )
    checklist = models.ForeignKey(
        "tickets.ChecklistTemplate",
        verbose_name="Checkliste",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Diese Punkte werden jedem angelegten Ticket angehängt.",
    )
    anchor_day = models.PositiveSmallIntegerField(null=True, blank=True, editable=False)
    active = models.BooleanField("Aktiv", default=True)
    last_created_at = models.DateTimeField("Zuletzt angelegt", null=True, blank=True)

    class Meta:
        ordering = ["next_run", "title"]
        verbose_name = "Wiederkehrendes Ticket"
        verbose_name_plural = "Wiederkehrende Tickets"

    def __str__(self):
        return self.title


# --- Checklisten --------------------------------------------------------------

class ChecklistTemplate(models.Model):
    """Wiederverwendbare Liste von Punkten, z. B. für den Eintritt eines Mitarbeiters."""

    name = models.CharField("Name", max_length=150)
    items = models.TextField("Punkte", help_text="Ein Punkt pro Zeile.")

    class Meta:
        ordering = ["name"]
        verbose_name = "Checklisten-Vorlage"
        verbose_name_plural = "Checklisten-Vorlagen"

    def __str__(self):
        return self.name

    @property
    def item_list(self):
        return [line.strip() for line in self.items.splitlines() if line.strip()]


class ChecklistItem(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="checklist")
    text = models.CharField("Punkt", max_length=300)
    done = models.BooleanField("Erledigt", default=False)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checked_items",
    )
    done_at = models.DateTimeField(null=True, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Checklisten-Punkt"
        verbose_name_plural = "Checklisten-Punkte"

    def __str__(self):
        return self.text


# --- Anfrage-Formulare --------------------------------------------------------

class RequestForm(models.Model):
    """Vorlage für eine häufige Anfrage mit festen Feldern statt Freitext."""

    name = models.CharField("Name", max_length=150, help_text="z. B. Neuer Mitarbeiter")
    description = models.TextField(
        "Erklärung", blank=True, help_text="Wird dem Melder über dem Formular angezeigt."
    )
    category = models.ForeignKey(
        Category, verbose_name="Kategorie", null=True, blank=True, on_delete=models.SET_NULL
    )
    team = models.ForeignKey(
        Team, verbose_name="Team", null=True, blank=True, on_delete=models.SET_NULL
    )
    priority = models.CharField(
        "Priorität",
        max_length=20,
        choices=Ticket.Priority.choices,
        default=Ticket.Priority.NORMAL,
    )
    estimated_minutes = models.PositiveIntegerField(
        "Geplanter Aufwand (Minuten)", null=True, blank=True
    )
    checklist = models.ForeignKey(
        ChecklistTemplate,
        verbose_name="Checkliste",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Diese Punkte werden dem Ticket automatisch angehängt.",
    )
    staff_only = models.BooleanField(
        "Nur für Bearbeiter", default=False, help_text="Melder sehen dieses Formular nicht."
    )
    active = models.BooleanField("Aktiv", default=True)
    position = models.PositiveIntegerField("Reihenfolge", default=0)

    class Meta:
        ordering = ["position", "name"]
        verbose_name = "Anfrage-Formular"
        verbose_name_plural = "Anfrage-Formulare"

    def __str__(self):
        return self.name


class RequestField(models.Model):
    class Kind(models.TextChoices):
        TEXT = "text", "Kurzer Text"
        TEXTAREA = "textarea", "Langer Text"
        SELECT = "select", "Auswahl"
        DATE = "date", "Datum"
        NUMBER = "number", "Zahl"
        CHECKBOX = "checkbox", "Ja/Nein"

    form = models.ForeignKey(RequestForm, on_delete=models.CASCADE, related_name="fields")
    label = models.CharField("Bezeichnung", max_length=150)
    kind = models.CharField("Art", max_length=20, choices=Kind.choices, default=Kind.TEXT)
    required = models.BooleanField("Pflichtfeld", default=True)
    choices = models.TextField(
        "Auswahlmöglichkeiten", blank=True, help_text="Nur für Auswahl: eine pro Zeile."
    )
    help_text = models.CharField("Hinweis", max_length=200, blank=True)
    in_title = models.BooleanField(
        "Im Betreff anzeigen",
        default=False,
        help_text="Der Wert wird an den Betreff des Tickets angehängt.",
    )
    position = models.PositiveIntegerField("Reihenfolge", default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Formularfeld"
        verbose_name_plural = "Formularfelder"

    def __str__(self):
        return self.label

    @property
    def choice_list(self):
        return [line.strip() for line in self.choices.splitlines() if line.strip()]
