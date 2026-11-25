from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from kb.models import Article
from projects.models import Task
from tickets import overview
from tickets.models import Ticket

from .decorators import staff_required
from .models import Announcement, Membership, Organization
from .orgs import contact_organization, ticket_filter

CLOSED_STATES = [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]


@login_required
def dashboard(request):
    user = request.user
    open_tickets = Ticket.objects.exclude(status__in=CLOSED_STATES)
    if user.is_staff:
        now = timezone.now()
        context = {
            "open_count": open_tickets.count(),
            "unassigned_count": open_tickets.filter(assignee__isnull=True).count(),
            "overdue_count": open_tickets.filter(due_at__lt=now).count(),
            "unanswered_count": open_tickets.filter(
                first_response_at__isnull=True, response_due_at__lt=now
            ).count(),
            "pool_free_count": open_tickets.filter(
                pool_week=timezone.localdate()
                - timedelta(days=timezone.localdate().weekday()),
                assignee__isnull=True,
            ).count(),
            "draft_count": Article.objects.filter(status=Article.Status.DRAFT).count(),
            "assigned": open_tickets.filter(assignee=user).select_related(
                "requester"
            )[:10],
            "my_tasks": Task.objects.filter(assignee=user)
            .exclude(status=Task.Status.DONE)
            .select_related("project")[:10],
        }
        period = request.GET.get("tage", "")
        context["overview"] = overview.build(
            days=int(period) if period.isdigit() else 30,
            kind=request.GET.get("art", ""),
        )
    else:
        context = {
            "my_tickets": Ticket.objects.filter(ticket_filter(user)).select_related(
                "requester"
            )[:20],
            "contact_organization": contact_organization(user),
        }
    return render(request, "dashboard.html", context)


# --- Störungsmeldungen --------------------------------------------------------

def _datetime_input():
    return forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "text", "level", "organization", "starts_at", "ends_at", "active"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3}),
            "starts_at": _datetime_input(),
            "ends_at": _datetime_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]


@staff_required
def announcement_list(request):
    return render(
        request,
        "core/announcements.html",
        {"items": Announcement.objects.select_related("organization", "created_by")[:100]},
    )


@staff_required
def announcement_edit(request, pk=None):
    item = get_object_or_404(Announcement, pk=pk) if pk else None
    if item and request.method == "POST" and "delete" in request.POST:
        item.delete()
        return redirect("announcements")
    form = AnnouncementForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        if item is None:
            saved.created_by = request.user
        saved.save()
        messages.success(request, "Meldung gespeichert.")
        return redirect("announcements")
    return render(request, "core/announcement_form.html", {"form": form, "item": item})


@require_POST
@staff_required
def announcement_end(request, pk):
    """Störung behoben: Meldung sofort ausblenden."""
    item = get_object_or_404(Announcement, pk=pk)
    item.active = False
    item.ends_at = timezone.now()
    item.save()
    messages.success(request, "Meldung beendet.")
    return redirect("announcements")


# --- Organisationen -----------------------------------------------------------

class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["name", "email_domains", "notes", "active"]
        widgets = {
            "email_domains": forms.TextInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


@staff_required
def organization_list(request):
    organizations = Organization.objects.annotate(
        member_count=Count("memberships", distinct=True),
        open_tickets=Count(
            "tickets", filter=~Q(tickets__status__in=CLOSED_STATES), distinct=True
        ),
    )
    return render(request, "core/organizations.html", {"organizations": organizations})


@staff_required
def organization_edit(request, pk=None):
    """Organisation anlegen oder bearbeiten und ihre Mitglieder verwalten."""
    organization = get_object_or_404(Organization, pk=pk) if pk else None
    User = get_user_model()

    if organization and request.method == "POST" and "member_action" in request.POST:
        action = request.POST["member_action"]
        user = User.objects.filter(pk=request.POST.get("user") or 0).first()
        if user is not None:
            if action == "add":
                Membership.objects.update_or_create(
                    user=user, defaults={"organization": organization, "is_contact": False}
                )
            else:
                membership = Membership.objects.filter(user=user, organization=organization)
                if action == "remove":
                    membership.delete()
                elif action == "toggle_contact":
                    for item in membership:
                        item.is_contact = not item.is_contact
                        item.save()
        return redirect("organization_edit", pk=organization.pk)

    form = OrganizationForm(request.POST or None, instance=organization)
    if request.method == "POST" and form.is_valid():
        organization = form.save()
        messages.success(request, "Organisation gespeichert.")
        return redirect("organization_edit", pk=organization.pk)

    context = {"form": form, "organization": organization}
    if organization:
        context["members"] = organization.memberships.select_related("user").order_by(
            "user__username"
        )
        # Melder ohne Organisation können hinzugefügt werden.
        context["candidates"] = User.objects.filter(
            is_active=True, membership__isnull=True
        ).order_by("username")[:500]
    return render(request, "core/organization_form.html", context)
