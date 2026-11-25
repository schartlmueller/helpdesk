from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import Announcement, Holiday, Membership, Organization


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    raw_id_fields = ["user"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "email_domains", "active"]
    inlines = [MembershipInline]


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ["date", "name"]
    date_hierarchy = "date"


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ["title", "level", "organization", "starts_at", "ends_at", "active"]
    list_filter = ["active", "level"]


class UserMembershipInline(admin.StackedInline):
    model = Membership
    can_delete = True
    extra = 0
    verbose_name = "Organisation"
    verbose_name_plural = "Organisation"


class HelpdeskUserAdmin(UserAdmin):
    """Benutzerverwaltung mit Zuordnung zur Organisation."""

    inlines = [UserMembershipInline]


User = get_user_model()
if admin.site.is_registered(User):
    admin.site.unregister(User)
admin.site.register(User, HelpdeskUserAdmin)
