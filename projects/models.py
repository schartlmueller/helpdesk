from django.conf import settings
from django.db import models
from django.urls import reverse


class Project(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Geplant"
        ACTIVE = "active", "Aktiv"
        ON_HOLD = "on_hold", "Pausiert"
        DONE = "done", "Abgeschlossen"

    name = models.CharField("Name", max_length=200)
    description = models.TextField("Beschreibung", blank=True)
    status = models.CharField(
        "Status", max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Projektleitung",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_projects",
    )
    organization = models.ForeignKey(
        "core.Organization",
        verbose_name="Organisation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects",
        help_text="Gebuchte Zeiten erscheinen im Leistungsnachweis dieser Organisation.",
    )
    start_date = models.DateField("Start", null=True, blank=True)
    due_date = models.DateField("Fällig am", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Projekt"
        verbose_name_plural = "Projekte"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("projects:detail", args=[self.pk])


class Milestone(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="milestones"
    )
    name = models.CharField("Meilenstein", max_length=200)
    due_date = models.DateField("Termin", null=True, blank=True)
    done = models.BooleanField("Erreicht", default=False)

    class Meta:
        ordering = ["due_date", "id"]
        verbose_name = "Meilenstein"
        verbose_name_plural = "Meilensteine"

    def __str__(self):
        return self.name


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "Offen"
        DOING = "doing", "In Arbeit"
        REVIEW = "review", "Prüfung"
        DONE = "done", "Erledigt"

    class Priority(models.TextChoices):
        LOW = "low", "Niedrig"
        NORMAL = "normal", "Normal"
        HIGH = "high", "Hoch"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="tasks", verbose_name="Projekt"
    )
    milestone = models.ForeignKey(
        Milestone,
        verbose_name="Meilenstein",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    title = models.CharField("Titel", max_length=200)
    description = models.TextField("Beschreibung", blank=True)
    status = models.CharField(
        "Status", max_length=20, choices=Status.choices, default=Status.TODO
    )
    priority = models.CharField(
        "Priorität", max_length=20, choices=Priority.choices, default=Priority.NORMAL
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Zuständig",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    start_date = models.DateField("Beginn", null=True, blank=True)
    due_date = models.DateField("Fällig am", null=True, blank=True)
    planned_for = models.DateField(
        "Geplant für", null=True, blank=True, help_text="Tag in der Wochenplanung."
    )
    estimated_minutes = models.PositiveIntegerField(
        "Geplanter Aufwand (Minuten)", null=True, blank=True
    )
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Aufgabe"
        verbose_name_plural = "Aufgaben"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("projects:task_detail", args=[self.pk])


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="task_comments",
    )
    body = models.TextField("Kommentar")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Aufgabenkommentar"
        verbose_name_plural = "Aufgabenkommentare"

    def __str__(self):
        return f"Kommentar zu {self.task}"
