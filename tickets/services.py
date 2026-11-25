from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from . import notify
from .models import Attachment, ChecklistItem, Comment, Ticket, TicketEvent, TimeEntry
from .sla import due_for, response_due_for


# --- Benutzer -----------------------------------------------------------------

def user_for_email(address, name=""):
    """Findet den Benutzer zu einer E-Mail-Adresse oder legt ihn ohne Passwort an."""
    User = get_user_model()
    user = (
        User.objects.filter(Q(email__iexact=address) | Q(username__iexact=address))
        .order_by("-is_active", "id")
        .first()
    )
    if user is not None:
        return user
    first, _, last = name.strip().partition(" ")
    user = User(
        username=address[:150],
        email=address,
        first_name=first[:150],
        last_name=last[:150],
    )
    user.set_unusable_password()
    user.save()
    return user


# --- Verlauf ------------------------------------------------------------------

def log(ticket, user, text):
    TicketEvent.objects.create(ticket=ticket, user=user, text=text[:500])


# --- Dateianhänge -------------------------------------------------------------

def save_attachments(files, user, ticket=None, comment=None, task=None):
    for upload in files or []:
        Attachment.objects.create(
            ticket=ticket,
            comment=comment,
            task=task,
            file=upload,
            name=(upload.name or "anhang")[:255],
            size=upload.size or 0,
            uploaded_by=user,
        )


# --- Zeiterfassung ------------------------------------------------------------

def _target(ticket, task):
    return {"ticket": ticket} if ticket is not None else {"task": task}


def start_timer(user, ticket=None, task=None):
    """Startet die Uhr dieses Bearbeiters auf einem Ticket oder einer Aufgabe.

    Pro Bearbeiter läuft immer nur eine Uhr: Läuft sie noch woanders, wird
    sie dort angehalten.
    """
    now = timezone.now()
    target = _target(ticket, task)
    TimeEntry.objects.filter(user=user, ended_at__isnull=True).exclude(**target).update(
        ended_at=now
    )
    if not TimeEntry.objects.filter(user=user, ended_at__isnull=True, **target).exists():
        TimeEntry.objects.create(user=user, started_at=now, **target)


def stop_timers(ticket=None, task=None, user=None):
    """Hält die Uhr an: nur für einen Bearbeiter (Pause) oder für alle."""
    running = TimeEntry.objects.filter(ended_at__isnull=True, **_target(ticket, task))
    if user is not None:
        running = running.filter(user=user)
    return running.update(ended_at=timezone.now())


def booked_seconds(obj):
    return sum(entry.seconds for entry in obj.time_entries.all())


# --- Tickets ------------------------------------------------------------------

def after_ticket_created(ticket, actor=None, source="Web", confirm=False):
    """Gemeinsame Schritte nach dem Anlegen, egal ob Web, E-Mail oder Schnittstelle."""
    log(ticket, actor, f"Ticket angelegt ({source})")
    if confirm:
        notify.ticket_created(ticket)
    notify.staff_new_ticket(ticket, actor)


def recalc_due(ticket):
    """Zielzeiten nach einer Prioritätsänderung neu berechnen."""
    ticket.due_at = due_for(ticket.priority, ticket.created_at)
    ticket.escalated_at = None
    if ticket.first_response_at is None:
        ticket.response_due_at = response_due_for(ticket.priority, ticket.created_at)
        ticket.response_escalated_at = None


def mark_first_response(ticket):
    """Hält den Zeitpunkt der ersten Antwort eines Bearbeiters an den Melder fest."""
    if ticket.first_response_at is None:
        ticket.first_response_at = timezone.now()
        Ticket.objects.filter(pk=ticket.pk).update(first_response_at=ticket.first_response_at)


def resolve_ticket(ticket, user, solution, create_article=False):
    """Löst ein Ticket: Lösung speichern, Uhr stoppen, Melder benachrichtigen.

    Gibt zurück, ob ein Entwurf für die Wissensbasis angelegt wurde.
    """
    from kb.services import create_draft_from_ticket

    draft_created = False
    with transaction.atomic():
        ticket.solution = solution
        ticket.status = Ticket.Status.RESOLVED
        ticket.resolved_at = timezone.now()
        if ticket.assignee_id is None:
            ticket.assignee = user
        if ticket.first_response_at is None:
            ticket.first_response_at = ticket.resolved_at
        ticket.save()
        stop_timers(ticket=ticket)
        Comment.objects.create(ticket=ticket, author=user, body=solution, is_solution=True)
        log(ticket, user, "Ticket gelöst")
        if create_article:
            _, draft_created = create_draft_from_ticket(ticket, user)
    notify.ticket_resolved(ticket)
    return draft_created


def resolve_children(parent, user, solution):
    """Löst alle offenen Untertickets mit der Lösung des Haupttickets."""
    count = 0
    for child in parent.children.exclude(
        status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED]
    ).select_related("requester"):
        resolve_ticket(
            child, user, f"{solution}\n\n(Gelöst über Hauptticket #{parent.pk}.)"
        )
        count += 1
    return count


@transaction.atomic
def merge_tickets(source, target, user):
    """Führt ``source`` in ``target`` zusammen und schließt ``source``."""
    same_requester = source.requester_id == target.requester_id
    Comment.objects.create(
        ticket=target,
        author=user,
        body=(
            f"Zusammengeführt aus Ticket #{source.pk}: {source.title}\n\n"
            f"{source.description}"
        ),
        # Bei unterschiedlichen Meldern bleibt der fremde Text intern.
        internal=not same_requester,
    )
    stop_timers(ticket=source)
    source.comments.update(ticket=target)
    source.attachments.update(ticket=target)
    source.time_entries.update(ticket=target)

    cc = set(target.cc_list) | set(source.cc_list)
    if not same_requester and source.requester.email:
        cc.add(source.requester.email)
    target.cc = ", ".join(sorted(cc))
    target.save()

    source.status = Ticket.Status.CLOSED
    source.merged_into = target
    source.save()
    log(source, user, f"Zusammengeführt in Ticket #{target.pk}")
    log(target, user, f"Ticket #{source.pk} hierher zusammengeführt")


# --- Checklisten --------------------------------------------------------------

def add_checklist_items(ticket, texts):
    start = ticket.checklist.count()
    ChecklistItem.objects.bulk_create(
        ChecklistItem(ticket=ticket, text=text[:300], position=start + index)
        for index, text in enumerate(texts)
    )


def apply_checklist(ticket, template):
    if template is not None:
        add_checklist_items(ticket, template.item_list)


# --- Suche --------------------------------------------------------------------

def search_tickets(queryset, query, staff):
    """Volltextsuche: Jedes Suchwort muss in Betreff, Beschreibung, Lösung,
    einer Antwort oder einem Dateinamen vorkommen. Eine Zahl findet auch die
    Ticketnummer. Interne Notizen durchsuchen nur Bearbeiter."""
    words = query.split()[:8]
    if not words:
        return queryset
    number = query.strip().lstrip("#")
    by_number = Q(pk=int(number)) if number.isdigit() else Q()

    condition = Q()
    for word in words:
        comments = Comment.objects.filter(ticket=OuterRef("pk"), body__icontains=word)
        if not staff:
            comments = comments.filter(internal=False)
        files = Attachment.objects.filter(ticket=OuterRef("pk"), name__icontains=word)
        if not staff:
            files = files.filter(Q(comment__isnull=True) | Q(comment__internal=False))
        condition &= (
            Q(title__icontains=word)
            | Q(description__icontains=word)
            | Q(solution__icontains=word)
            | Exists(comments)
            | Exists(files)
        )
    return queryset.filter(condition | by_number) if by_number else queryset.filter(condition)
