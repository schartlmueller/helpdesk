from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage


def _ticket_url(ticket):
    return f"{settings.SITE_URL}{ticket.get_absolute_url()}"


def _send(recipients, subject, body, cc=None):
    recipients = [r for r in dict.fromkeys(recipients) if r]
    if not recipients:
        return
    message = EmailMessage(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        recipients,
        cc=[c for c in (cc or []) if c not in recipients],
        # Verhindert, dass Abwesenheitsnotizen und andere Automaten antworten.
        headers={"Auto-Submitted": "auto-generated"},
    )
    message.send(fail_silently=True)


def _reply_hint():
    if settings.IMAP_HOST:
        return "Sie können direkt auf diese E-Mail antworten.\n"
    return ""


# --- An Melder und Empfänger in Kopie -----------------------------------------

def _to_requester(ticket, subject, body):
    _send([ticket.requester.email], subject, body, cc=ticket.cc_list)


def ticket_created(ticket):
    hint = ""
    if not ticket.requester.has_usable_password() and not settings.SSO_ENABLED:
        hint = (
            "Um das Ticket im Browser zu verfolgen, setzen Sie sich hier ein Passwort:\n"
            f"{settings.SITE_URL}/passwort/vergessen/\n"
        )
    _to_requester(
        ticket,
        f"[Ticket #{ticket.pk}] Eingegangen: {ticket.title}",
        "Ihre Anfrage ist bei uns eingegangen und wird bearbeitet.\n\n"
        f"{_reply_hint()}"
        f"Zum Ticket: {_ticket_url(ticket)}\n{hint}",
    )


def ticket_resolved(ticket):
    _to_requester(
        ticket,
        f"[Ticket #{ticket.pk}] Gelöst: {ticket.title}",
        "Ihr Ticket wurde gelöst.\n\n"
        f"Lösung:\n{ticket.solution}\n\n"
        "Falls das Problem weiterhin besteht, können Sie das Ticket wieder öffnen:\n"
        f"{_ticket_url(ticket)}\n"
        f"{_reply_hint()}{_auto_close_hint()}",
    )


def _auto_close_hint():
    if settings.AUTO_CLOSE_DAYS > 0:
        return (
            f"Ohne Rückmeldung wird das Ticket in {settings.AUTO_CLOSE_DAYS} Tagen "
            "automatisch geschlossen.\n"
        )
    return ""


def waiting_reminder(ticket):
    _to_requester(
        ticket,
        f"[Ticket #{ticket.pk}] Wir warten auf Ihre Rückmeldung: {ticket.title}",
        "Zu Ihrem Ticket benötigen wir noch eine Rückmeldung von Ihnen.\n\n"
        f"{_reply_hint()}Zum Ticket: {_ticket_url(ticket)}\n",
    )


def closed_without_reply(ticket):
    _to_requester(
        ticket,
        f"[Ticket #{ticket.pk}] Geschlossen: {ticket.title}",
        "Wir haben keine Rückmeldung erhalten und das Ticket daher geschlossen.\n\n"
        "Falls das Anliegen noch besteht, können Sie es jederzeit wieder öffnen:\n"
        f"{_ticket_url(ticket)}\n{_reply_hint()}",
    )


def staff_follow_up(ticket):
    _send(
        _staff_recipients(ticket),
        f"[Ticket #{ticket.pk}] Wiedervorlage: {ticket.title}",
        "Die Wiedervorlage dieses Tickets ist heute fällig. Es steht wieder auf "
        "„In Bearbeitung“.\n\n"
        f"Zum Ticket: {_ticket_url(ticket)}\n",
    )


def ticket_reply(ticket, comment):
    _to_requester(
        ticket,
        f"[Ticket #{ticket.pk}] Neue Antwort: {ticket.title}",
        f"{comment.body}\n\n{_reply_hint()}Zum Ticket: {_ticket_url(ticket)}\n",
    )


# --- An Bearbeiter ------------------------------------------------------------

def _staff_recipients(ticket, exclude=None):
    """Zuständiger Bearbeiter, sonst das Team, sonst alle Bearbeiter."""
    if ticket.assignee_id and ticket.assignee.is_active:
        users = [ticket.assignee]
    elif ticket.team_id:
        users = list(ticket.team.members.filter(is_active=True, is_staff=True))
    else:
        users = []
    if not users:
        users = list(get_user_model().objects.filter(is_active=True, is_staff=True))
    exclude_id = getattr(exclude, "id", None)
    return [u.email for u in users if u.email and u.id != exclude_id]


def _name(user):
    return user.get_full_name() or user.username


def staff_new_ticket(ticket, actor=None):
    _send(
        _staff_recipients(ticket, exclude=actor),
        f"[Ticket #{ticket.pk}] Neu: {ticket.title}",
        f"Neues Ticket von {_name(ticket.requester)} "
        f"(Priorität {ticket.get_priority_display()}).\n\n"
        f"{ticket.description}\n\nZum Ticket: {_ticket_url(ticket)}\n",
    )


def staff_assigned(ticket, actor=None):
    assignee = ticket.assignee
    if assignee is None or not assignee.email or assignee.id == getattr(actor, "id", None):
        return
    _send(
        [assignee.email],
        f"[Ticket #{ticket.pk}] Dir zugewiesen: {ticket.title}",
        f"Das Ticket wurde dir zugewiesen.\n\nZum Ticket: {_ticket_url(ticket)}\n",
    )


def staff_requester_reply(ticket, comment):
    _send(
        _staff_recipients(ticket, exclude=comment.author),
        f"[Ticket #{ticket.pk}] Antwort vom Melder: {ticket.title}",
        f"{comment.body}\n\nZum Ticket: {_ticket_url(ticket)}\n",
    )


def staff_escalation(ticket):
    recipients = _staff_recipients(ticket)
    if ticket.team_id:
        recipients += [
            u.email for u in ticket.team.members.filter(is_active=True, is_staff=True)
        ]
    _send(
        recipients,
        f"[Ticket #{ticket.pk}] ÜBERFÄLLIG: {ticket.title}",
        "Die Zielzeit dieses Tickets ist überschritten.\n\n"
        f"Priorität: {ticket.get_priority_display()}\n"
        f"Zum Ticket: {_ticket_url(ticket)}\n",
    )


def staff_response_overdue(ticket):
    _send(
        _staff_recipients(ticket),
        f"[Ticket #{ticket.pk}] Noch keine Antwort: {ticket.title}",
        "Der Melder wartet länger als vorgesehen auf eine erste Antwort.\n\n"
        f"Priorität: {ticket.get_priority_display()}\n"
        f"Zum Ticket: {_ticket_url(ticket)}\n",
    )
