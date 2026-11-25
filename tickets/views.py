import csv
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import F
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from core.decorators import staff_required
from core.models import Organization
from core.orgs import can_view_ticket, ticket_filter
from kb.models import Article
from kb.services import create_draft_from_ticket, search_articles

from . import notify
from .forms import (
    ChecklistForm,
    CommentForm,
    LinkForm,
    ManualTimeForm,
    MergeForm,
    ResolveForm,
    TicketCreateForm,
    TicketUpdateForm,
    add_requester_fields,
    uploaded_files,
)
from .models import (
    Attachment,
    CannedResponse,
    ChecklistItem,
    Comment,
    RequestForm,
    Team,
    Ticket,
    TimeEntry,
)
from .request_forms import build_form, ticket_text
from .services import (
    add_checklist_items,
    after_ticket_created,
    apply_checklist,
    booked_seconds,
    log,
    mark_first_response,
    merge_tickets,
    recalc_due,
    resolve_children,
    resolve_ticket,
    save_attachments,
    search_tickets,
    start_timer,
    stop_timers,
    user_for_email,
)

CLOSED_STATES = [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]


def _visible_tickets(user):
    qs = Ticket.objects.select_related(
        "requester", "assignee", "category", "team", "organization"
    )
    if user.is_staff:
        return qs
    # Melder sehen ihre eigenen Tickets, Ansprechpartner alle ihrer Organisation.
    return qs.filter(ticket_filter(user))


def paginate(request, items, per_page=50):
    """Gibt (Seite, Abfrage-Parameter ohne Seitenzahl) zurück."""
    page = Paginator(items, per_page).get_page(request.GET.get("seite"))
    params = request.GET.copy()
    params.pop("seite", None)
    return page, params.urlencode()


def _get_ticket(request, pk):
    ticket = get_object_or_404(
        Ticket.objects.select_related(
            "requester", "assignee", "category", "project", "team", "merged_into",
            "organization", "parent",
        ),
        pk=pk,
    )
    if not can_view_ticket(request.user, ticket):
        raise PermissionDenied
    return ticket


def _display(ticket, field):
    """Lesbarer Wert eines Feldes für den Änderungsverlauf."""
    getter = getattr(ticket, f"get_{field}_display", None)
    if getter is not None:
        return getter()
    value = getattr(ticket, field)
    if value in (None, ""):
        return "–"
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value)


@login_required
def ticket_list(request):
    tickets = _visible_tickets(request.user)
    status = request.GET.get("status", "active")
    scope = request.GET.get("scope", "")
    team = request.GET.get("team", "")
    organization = request.GET.get("org", "")
    kind = request.GET.get("art", "")
    query = request.GET.get("q", "").strip()

    if status == "active":
        tickets = tickets.exclude(status__in=CLOSED_STATES)
    elif status in Ticket.Status.values:
        tickets = tickets.filter(status=status)
    if request.user.is_staff:
        if scope == "mine":
            tickets = tickets.filter(assignee=request.user)
        elif scope == "unassigned":
            tickets = tickets.filter(assignee__isnull=True)
        elif scope == "overdue":
            tickets = tickets.exclude(status__in=CLOSED_STATES).filter(
                due_at__lt=timezone.now()
            )
        elif scope == "pool":
            today = timezone.localdate()
            tickets = tickets.filter(pool_week=today - timedelta(days=today.weekday()))
        elif scope == "followup":
            tickets = tickets.filter(follow_up_on__isnull=False).order_by("follow_up_on")
        elif scope == "unanswered":
            tickets = tickets.exclude(status__in=CLOSED_STATES).filter(
                first_response_at__isnull=True, response_due_at__lt=timezone.now()
            )
        if team.isdigit():
            tickets = tickets.filter(team_id=int(team))
        if organization.isdigit():
            tickets = tickets.filter(organization_id=int(organization))
    if kind in Ticket.Kind.values:
        tickets = tickets.filter(kind=kind)
    elif kind == "none":
        tickets = tickets.filter(kind="")
    if query:
        tickets = search_tickets(tickets, query, staff=request.user.is_staff)

    page, params = paginate(request, tickets)
    return render(
        request,
        "tickets/list.html",
        {
            "tickets": page,
            "page": page,
            "params": params,
            "status": status,
            "scope": scope,
            "kind": kind,
            "kind_choices": Ticket.Kind.choices,
            "team": team,
            "teams": Team.objects.all() if request.user.is_staff else [],
            "organization": organization,
            "organizations": (
                Organization.objects.filter(active=True) if request.user.is_staff else []
            ),
            "query": query,
            "status_choices": Ticket.Status.choices,
        },
    )


def _requester_from(request, form):
    """Wer als Melder eingetragen wird: der Angemeldete oder, bei Bearbeitern,
    die im Formular gewählte Person."""
    if request.user.is_staff:
        if form.cleaned_data.get("requester_email"):
            return user_for_email(form.cleaned_data["requester_email"])
        if form.cleaned_data.get("requester"):
            return form.cleaned_data["requester"]
    return request.user


def _finish_creation(request, ticket, files, source="Web"):
    save_attachments(files, request.user, ticket=ticket)
    on_behalf = ticket.requester_id != request.user.id
    after_ticket_created(
        ticket,
        actor=request.user,
        source=f"{source}, für {ticket.requester}" if on_behalf else source,
        confirm=on_behalf,
    )
    messages.success(request, f"Ticket #{ticket.pk} wurde angelegt.")
    return redirect(ticket)


def _request_forms(user):
    forms = RequestForm.objects.filter(active=True)
    return forms if user.is_staff else forms.filter(staff_only=False)


@login_required
def ticket_create(request):
    staff = request.user.is_staff
    form = TicketCreateForm(request.POST or None, request.FILES or None, staff=staff)
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        ticket.requester = _requester_from(request, form)
        ticket.save()
        return _finish_creation(request, ticket, uploaded_files(form.cleaned_data))
    return render(
        request,
        "tickets/create.html",
        {"form": form, "request_forms": _request_forms(request.user)},
    )


@login_required
def request_form_create(request, pk):
    """Ticket über ein Anfrage-Formular mit festen Feldern anlegen."""
    template = get_object_or_404(_request_forms(request.user), pk=pk)
    data = request.POST if request.method == "POST" else None
    files = request.FILES if request.method == "POST" else None
    form, specs = build_form(template, data, files)
    if request.user.is_staff:
        add_requester_fields(form)
    if request.method == "POST" and form.is_valid():
        title, description = ticket_text(template, specs, form.cleaned_data)
        ticket = Ticket.objects.create(
            title=title,
            description=description,
            category=template.category,
            team=template.team,
            priority=template.priority,
            estimated_minutes=template.estimated_minutes,
            requester=_requester_from(request, form),
        )
        apply_checklist(ticket, template.checklist)
        return _finish_creation(
            request, ticket, uploaded_files(form.cleaned_data), source=f"Formular „{template.name}“"
        )
    return render(request, "tickets/request_form.html", {"form": form, "template": template})


@login_required
def ticket_detail(request, pk):
    ticket = _get_ticket(request, pk)
    staff = request.user.is_staff
    comments = ticket.comments.select_related("author").prefetch_related("attachments")
    if not staff:
        comments = comments.filter(internal=False)

    context = {
        "ticket": ticket,
        "comments": comments,
        "ticket_attachments": ticket.attachments.filter(comment__isnull=True),
        "comment_form": CommentForm(staff=staff),
        "article": Article.objects.filter(source_ticket=ticket).first(),
    }
    if staff:
        entries = list(ticket.time_entries.select_related("user"))
        checklist = list(ticket.checklist.select_related("done_by"))
        context.update(
            {
                "update_form": TicketUpdateForm(instance=ticket),
                "time_entries": entries,
                "total_seconds": sum(e.seconds for e in entries),
                "timer_running": any(e.running for e in entries),
                "my_timer_running": any(
                    e.running and e.user_id == request.user.id for e in entries
                ),
                "my_timer_used": any(e.user_id == request.user.id for e in entries),
                "manual_time_form": ManualTimeForm(),
                "events": ticket.events.select_related("user"),
                "canned": CannedResponse.objects.all(),
                "children": ticket.children.select_related("requester"),
                "related_tickets": ticket.related.all(),
                "link_form": LinkForm(),
                "this_monday": timezone.localdate()
                - timedelta(days=timezone.localdate().weekday()),
                "checklist": checklist,
                "checklist_done": len([i for i in checklist if i.done]),
                "checklist_form": ChecklistForm(),
            }
        )
        if ticket.is_open:
            open_children = ticket.children.exclude(status__in=CLOSED_STATES).count()
            context["resolve_form"] = ResolveForm(open_children=open_children)
            context["merge_form"] = MergeForm()
            context["suggestions"] = search_articles(
                f"{ticket.title} {ticket.description[:300]}", limit=4
            )
    return render(request, "tickets/detail.html", context)


@login_required
def attachment_download(request, pk):
    attachment = get_object_or_404(
        Attachment.objects.select_related("ticket", "comment"), pk=pk
    )
    if not request.user.is_staff:
        # Anhänge an Projektaufgaben und internen Notizen sehen nur Bearbeiter.
        if attachment.ticket is None or not can_view_ticket(request.user, attachment.ticket):
            raise PermissionDenied
        if attachment.comment is not None and attachment.comment.internal:
            raise PermissionDenied
    try:
        handle = attachment.file.open("rb")
    except FileNotFoundError:
        raise Http404
    # Immer als Download ausliefern, nie im Browser darstellen.
    return FileResponse(handle, as_attachment=True, filename=attachment.name)


@require_POST
@staff_required
def ticket_update(request, pk):
    ticket = _get_ticket(request, pk)
    fields = TicketUpdateForm.Meta.fields
    before = {f: _display(ticket, f) for f in fields}
    old_status, old_assignee = ticket.status, ticket.assignee_id

    form = TicketUpdateForm(request.POST, instance=ticket)
    if not form.is_valid():
        errors = " ".join(e for errs in form.errors.values() for e in errs)
        messages.error(request, f"Die Änderung konnte nicht gespeichert werden. {errors}")
        return redirect("tickets:detail", pk=pk)

    ticket = form.save(commit=False)
    if old_status == Ticket.Status.RESOLVED and ticket.is_open:
        ticket.resolved_at = None
    if "priority" in form.changed_data and ticket.is_open:
        recalc_due(ticket)
    ticket.save()

    changes = [
        f"{form.fields[f].label}: {before[f]} → {_display(ticket, f)}"
        for f in form.changed_data
        if f in before
    ]
    if changes:
        log(ticket, request.user, "; ".join(changes))
    if ticket.status != old_status:
        if ticket.status == Ticket.Status.OPEN:
            start_timer(request.user, ticket=ticket)
        elif ticket.status != Ticket.Status.NEW:
            stop_timers(ticket=ticket)
    if ticket.assignee_id and ticket.assignee_id != old_assignee:
        notify.staff_assigned(ticket, request.user)
    messages.success(request, "Ticket aktualisiert.")
    return redirect(ticket)


@require_POST
@login_required
def ticket_comment(request, pk):
    ticket = _get_ticket(request, pk)
    staff = request.user.is_staff
    form = CommentForm(request.POST, request.FILES, staff=staff)
    if not form.is_valid():
        errors = " ".join(e for errs in form.errors.values() for e in errs)
        messages.error(request, errors or "Bitte eine Nachricht eingeben.")
        return redirect(ticket)

    comment = form.save(commit=False)
    comment.ticket = ticket
    comment.author = request.user
    comment.save()
    save_attachments(uploaded_files(form.cleaned_data), request.user, ticket=ticket, comment=comment)

    if staff and not comment.internal:
        if ticket.status == Ticket.Status.NEW:
            ticket.status = Ticket.Status.OPEN
            if ticket.assignee_id is None:
                ticket.assignee = request.user
            ticket.save()
            log(ticket, request.user, "Status: Neu → In Bearbeitung (erste Antwort)")
            start_timer(request.user, ticket=ticket)
        mark_first_response(ticket)
        if ticket.requester_id != request.user.id:
            notify.ticket_reply(ticket, comment)
    elif not staff:
        if ticket.status == Ticket.Status.WAITING:
            ticket.status = Ticket.Status.OPEN
            ticket.save()
            log(ticket, request.user, "Status: Wartet auf Rückmeldung → In Bearbeitung")
        notify.staff_requester_reply(ticket, comment)
    return redirect(ticket)


@require_POST
@staff_required
def ticket_start(request, pk):
    """Bearbeitung beginnen oder nach einer Pause fortsetzen."""
    ticket = _get_ticket(request, pk)
    if not ticket.is_open:
        messages.error(request, "Das Ticket ist bereits abgeschlossen.")
        return redirect(ticket)
    if ticket.status != Ticket.Status.OPEN or ticket.assignee_id is None:
        old = ticket.get_status_display()
        ticket.status = Ticket.Status.OPEN
        if ticket.assignee_id is None:
            ticket.assignee = request.user
        ticket.save()
        log(ticket, request.user, f"Bearbeitung begonnen (vorher: {old})")
    start_timer(request.user, ticket=ticket)
    return redirect(ticket)


@require_POST
@staff_required
def ticket_pause(request, pk):
    ticket = _get_ticket(request, pk)
    stop_timers(ticket=ticket, user=request.user)
    return redirect(ticket)


@require_POST
@staff_required
def ticket_time_add(request, pk):
    """Zeit nachtragen."""
    ticket = _get_ticket(request, pk)
    form = ManualTimeForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte Datum, Beginn und Dauer angeben.")
        return redirect(ticket)
    start = timezone.make_aware(
        datetime.combine(form.cleaned_data["date"], form.cleaned_data["start"])
    )
    TimeEntry.objects.create(
        ticket=ticket,
        user=request.user,
        started_at=start,
        ended_at=start + timedelta(minutes=form.cleaned_data["minutes"]),
        note=form.cleaned_data["note"] or "nachgetragen",
    )
    log(ticket, request.user, f"{form.cleaned_data['minutes']} Minuten nachgetragen")
    return redirect(ticket)


@require_POST
@staff_required
def ticket_merge(request, pk):
    ticket = _get_ticket(request, pk)
    form = MergeForm(request.POST)
    target = None
    if form.is_valid():
        target = Ticket.objects.filter(pk=form.cleaned_data["target"]).first()
    if target is None or target.pk == ticket.pk or target.merged_into_id:
        messages.error(request, "Bitte die Nummer eines anderen, bestehenden Tickets angeben.")
        return redirect(ticket)
    merge_tickets(ticket, target, request.user)
    messages.success(request, f"Ticket #{ticket.pk} wurde in dieses Ticket zusammengeführt.")
    return redirect(target)


@require_POST
@staff_required
def ticket_resolve(request, pk):
    ticket = _get_ticket(request, pk)
    open_children = ticket.children.exclude(status__in=CLOSED_STATES).count()
    form = ResolveForm(request.POST, open_children=open_children)
    if not form.is_valid():
        messages.error(request, "Bitte eine Lösung beschreiben.")
        return redirect(ticket)

    solution = form.cleaned_data["solution"].strip()
    draft_created = resolve_ticket(
        ticket, request.user, solution, create_article=form.cleaned_data["create_article"]
    )
    text = "Ticket gelöst."
    if form.cleaned_data.get("resolve_children"):
        count = resolve_children(ticket, request.user, solution)
        text = f"Ticket und {count} Untertickets gelöst."
    if draft_created:
        text += " Ein Entwurf für die Wissensbasis wartet auf Freigabe."
    messages.success(request, text)
    return redirect(ticket)


@require_POST
@staff_required
def checklist_add(request, pk):
    """Einzelnen Punkt oder eine ganze Vorlage an die Checkliste hängen."""
    ticket = _get_ticket(request, pk)
    form = ChecklistForm(request.POST)
    if form.is_valid():
        text = form.cleaned_data["text"].strip()
        if text:
            add_checklist_items(ticket, [text])
        template = form.cleaned_data["template"]
        if template is not None:
            apply_checklist(ticket, template)
            log(ticket, request.user, f"Checkliste „{template.name}“ eingefügt")
    return redirect(ticket)


@require_POST
@staff_required
def checklist_change(request, pk, item_pk):
    """Punkt abhaken, wieder öffnen oder löschen."""
    ticket = _get_ticket(request, pk)
    item = get_object_or_404(ChecklistItem, pk=item_pk, ticket=ticket)
    if "delete" in request.POST:
        item.delete()
    else:
        item.done = not item.done
        item.done_by = request.user if item.done else None
        item.done_at = timezone.now() if item.done else None
        item.save()
    return redirect(ticket)


@require_POST
@staff_required
def ticket_link(request, pk):
    """Haupt-/Unterticket oder „hängt zusammen mit“ setzen."""
    ticket = _get_ticket(request, pk)
    form = LinkForm(request.POST)
    other = None
    if form.is_valid():
        other = Ticket.objects.filter(pk=form.cleaned_data["target"]).first()
    if other is None or other.pk == ticket.pk:
        messages.error(request, "Bitte die Nummer eines anderen, bestehenden Tickets angeben.")
        return redirect(ticket)

    relation = form.cleaned_data["relation"]
    if relation == "related":
        ticket.related.add(other)
        log(ticket, request.user, f"Verknüpft mit Ticket #{other.pk}")
        log(other, request.user, f"Verknüpft mit Ticket #{ticket.pk}")
        return redirect(ticket)

    child, parent = (other, ticket) if relation == "child" else (ticket, other)
    # Nur eine Ebene: Ein Unterticket kann nicht selbst Hauptticket sein.
    if parent.parent_id is not None or child.children.exists():
        messages.error(
            request,
            "Nicht möglich: Ein Unterticket kann nicht gleichzeitig Hauptticket sein.",
        )
        return redirect(ticket)
    child.parent = parent
    child.save()
    log(child, request.user, f"Unterticket von #{parent.pk}")
    log(parent, request.user, f"Ticket #{child.pk} als Unterticket hinzugefügt")
    return redirect(ticket)


@require_POST
@staff_required
def ticket_unlink(request, pk, other_pk):
    ticket = _get_ticket(request, pk)
    other = get_object_or_404(Ticket, pk=other_pk)
    if ticket.parent_id == other.pk:
        ticket.parent = None
        ticket.save()
    elif other.parent_id == ticket.pk:
        other.parent = None
        other.save()
    ticket.related.remove(other)
    log(ticket, request.user, f"Verknüpfung mit Ticket #{other.pk} gelöst")
    return redirect(ticket)


@require_POST
@login_required
def ticket_reopen(request, pk):
    ticket = _get_ticket(request, pk)
    if not ticket.is_open and ticket.merged_into_id is None:
        ticket.status = Ticket.Status.OPEN
        ticket.resolved_at = None
        ticket.save()
        comment = Comment.objects.create(
            ticket=ticket,
            author=request.user,
            body="Ticket wurde wieder geöffnet.",
        )
        log(ticket, request.user, "Ticket wieder geöffnet")
        if not request.user.is_staff:
            notify.staff_requester_reply(ticket, comment)
        messages.info(request, "Ticket wieder geöffnet.")
    return redirect(ticket)


def _date_param(request, name):
    try:
        return parse_date(request.GET.get(name, ""))
    except ValueError:
        return None


def _entry_target(entry):
    """(Schlüssel, Bezeichnung, Adresse) des Tickets bzw. der Aufgabe eines Zeiteintrags."""
    if entry.ticket_id:
        return ("t", entry.ticket_id), entry.target_label, entry.ticket.get_absolute_url()
    if entry.task_id:
        return ("a", entry.task_id), entry.target_label, entry.task.get_absolute_url()
    return ("x", 0), "–", ""


@staff_required
def time_report(request):
    """Gebuchte Zeiten im Zeitraum und Planung der offenen Tickets."""
    today = timezone.localdate()
    start = _date_param(request, "von") or today - timedelta(days=today.weekday())
    end = _date_param(request, "bis") or start + timedelta(days=6)

    entries = TimeEntry.objects.filter(
        started_at__date__gte=start, started_at__date__lte=end
    ).select_related("user", "ticket", "task__project")

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="zeiten_{start}_{end}.csv"'
        response.write("﻿")  # damit Excel die Umlaute richtig liest
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["Datum", "Bearbeiter", "Ticket/Aufgabe", "Beginn", "Ende", "Minuten", "Notiz"])
        for entry in entries:
            begin = timezone.localtime(entry.started_at)
            finish = timezone.localtime(entry.ended_at) if entry.ended_at else None
            writer.writerow(
                [
                    begin.strftime("%d.%m.%Y"),
                    entry.user.get_full_name() or entry.user.username,
                    entry.target_label,
                    begin.strftime("%H:%M"),
                    finish.strftime("%H:%M") if finish else "läuft",
                    round(entry.seconds / 60),
                    entry.note,
                ]
            )
        return response

    per_user = {}
    for entry in entries:
        row = per_user.setdefault(
            entry.user_id, {"user": entry.user, "seconds": 0, "targets": {}}
        )
        row["seconds"] += entry.seconds
        key, label, url = _entry_target(entry)
        item = row["targets"].setdefault(key, {"label": label, "url": url, "seconds": 0})
        item["seconds"] += entry.seconds
    report = sorted(per_user.values(), key=lambda r: r["user"].username)
    for row in report:
        row["targets"] = sorted(row["targets"].values(), key=lambda i: -i["seconds"])

    planned = list(
        Ticket.objects.exclude(status__in=CLOSED_STATES)
        .select_related("assignee")
        .prefetch_related("time_entries")
        .order_by(F("planned_for").asc(nulls_last=True), "due_at")[:300]
    )
    for ticket in planned:
        ticket.booked = booked_seconds(ticket)
        ticket.over_plan = bool(
            ticket.estimated_minutes and ticket.booked > ticket.estimated_minutes * 60
        )

    return render(
        request,
        "tickets/times.html",
        {
            "start": start,
            "end": end,
            "report": report,
            "total_seconds": sum(r["seconds"] for r in report),
            "planned": planned,
            "today": today,
        },
    )
