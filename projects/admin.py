from django.contrib import admin

from .models import Milestone, Project, Task


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    fields = ["title", "status", "priority", "assignee", "due_date"]


class MilestoneInline(admin.TabularInline):
    model = Milestone
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "owner", "due_date"]
    list_filter = ["status"]
    inlines = [MilestoneInline, TaskInline]
