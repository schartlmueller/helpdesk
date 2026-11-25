from django.contrib import admin

from .models import (
    Absence,
    Attachment,
    CannedResponse,
    Category,
    ChecklistTemplate,
    Comment,
    PlannerProfile,
    RecurringTicket,
    RequestField,
    RequestForm,
    Team,
    Ticket,
    TicketEvent,
    TimeEntry,
)


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0


class TimeEntryInline(admin.TabularInline):
    model = TimeEntry
    extra = 0
    fields = ["user", "started_at", "ended_at", "note"]


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "status", "priority", "team", "requester", "assignee", "created_at"]
    list_filter = ["status", "kind", "priority", "team", "category", "organization"]
    search_fields = ["title", "description"]
    raw_id_fields = ["merged_into", "parent", "related"]
    inlines = [CommentInline, TimeEntryInline]


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    """Hier lassen sich Zeiten nachträglich korrigieren."""

    list_display = ["__str__", "user", "started_at", "ended_at", "note"]
    list_filter = ["user"]
    date_hierarchy = "started_at"
    raw_id_fields = ["ticket", "task"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    filter_horizontal = ["members"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "team"]


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ["name", "ticket", "task", "size", "uploaded_by", "created_at"]
    raw_id_fields = ["ticket", "comment", "task"]


@admin.register(TicketEvent)
class TicketEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "ticket", "user", "text"]
    raw_id_fields = ["ticket"]


admin.site.register(CannedResponse)
admin.site.register(ChecklistTemplate)


@admin.register(PlannerProfile)
class PlannerProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "daily_hours"]


@admin.register(Absence)
class AbsenceAdmin(admin.ModelAdmin):
    list_display = ["user", "start_date", "end_date", "reason"]
    list_filter = ["user"]


@admin.register(RecurringTicket)
class RecurringTicketAdmin(admin.ModelAdmin):
    list_display = ["title", "interval", "next_run", "assignee", "active"]
    list_filter = ["active", "interval"]


class RequestFieldInline(admin.TabularInline):
    model = RequestField
    extra = 1
    fields = ["position", "label", "kind", "required", "choices", "help_text", "in_title"]


@admin.register(RequestForm)
class RequestFormAdmin(admin.ModelAdmin):
    """Anfrage-Formulare: Vorlage samt Feldern in einem Schritt pflegen."""

    list_display = ["name", "category", "team", "priority", "staff_only", "active", "position"]
    list_filter = ["active", "staff_only"]
    inlines = [RequestFieldInline]
