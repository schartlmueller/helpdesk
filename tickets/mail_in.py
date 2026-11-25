"""Verarbeitet eingehende E-Mails zu Tickets und Antworten.

Regeln:
- Steht im Betreff "[Ticket #123]" und stammt die E-Mail vom Melder dieses
  Tickets, einem Ansprechpartner seiner Organisation, einer Adresse in Kopie
  oder von einem Bearbeiter, wird sie als
  Antwort an das Ticket gehängt. Zitierter Verlauf wird abgeschnitten.
- Jede andere E-Mail erzeugt ein neues Ticket.
- Automatische E-Mails (Abwesenheitsnotizen, Newsletter, Unzustellbarkeits-
  meldungen) werden übersprungen, damit keine Endlosschleifen entstehen.
"""

import email
import re
from email import policy
from email.utils import getaddresses, parseaddr

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from core.antivirus import ScanError, scan
from core.orgs import can_view_ticket

from . import notify
from .models import Attachment, Comment, Ticket
from .services import after_ticket_created, log, mark_first_response, user_for_email
from .textutils import html_to_text, strip_quoted_reply

TICKET_REF = re.compile(r"\[Ticket #(\d+)\]")
SYSTEM_SENDERS = ("mailer-daemon", "postmaster", "noreply", "no-reply")


def _is_automatic(message):
    auto = str(message.get("Auto-Submitted", "no")).strip().lower()
    if auto and auto != "no":
        return True
    precedence = str(message.get("Precedence", "")).strip().lower()
    return precedence in ("bulk", "junk", "list", "auto_reply")


def _own_addresses():
    own = {parseaddr(settings.DEFAULT_FROM_EMAIL)[1].lower()}
    if settings.IMAP_USER and "@" in settings.IMAP_USER:
        own.add(settings.IMAP_USER.lower())
    return own


def _sender_allowed(address):
    local, _, domain = address.partition("@")
    if not domain or local.lower().startswith(SYSTEM_SENDERS):
        return False
    if address.lower() in _own_addresses():
        return False
    allowed = settings.MAIL_ALLOWED_DOMAINS
    return not allowed or domain.lower() in allowed


def _body_of(message):
    """Gibt (Text, Original-HTML oder None) zurück."""
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return "", None
    try:
        text = part.get_content()
    except (LookupError, UnicodeError):
        text = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
    if part.get_content_type() == "text/html":
        return html_to_text(text), text
    return text.replace("\r\n", "\n").strip(), None


def _cc_addresses(message):
    own = _own_addresses()
    found = []
    for _, address in getaddresses([str(v) for v in message.get_all("Cc", [])]):
        address = address.strip().lower()
        if "@" in address and address not in own and address not in found:
            found.append(address)
    return found[:20]


def _store(ticket, user, comment, name, content):
    Attachment.objects.create(
        ticket=ticket,
        comment=comment,
        file=ContentFile(content, name=name),
        name=name,
        size=len(content),
        uploaded_by=user,
    )


def _save_attachments(message, ticket, user, comment, original_html):
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    skipped = []
    for part in message.iter_attachments():
        content = part.get_payload(decode=True)
        if not content:
            continue
        name = (part.get_filename() or "anhang")[:255]
        if len(content) > limit:
            skipped.append(f"{name} (zu groß)")
            continue
        try:
            if scan(ContentFile(content)):
                skipped.append(f"{name} (Virenfund)")
                continue
        except ScanError:
            skipped.append(f"{name} (Virenprüfung nicht erreichbar)")
            continue
        _store(ticket, user, comment, name, content)
    if original_html:
        # Die formatierte Fassung bleibt als Datei erhalten.
        _store(ticket, user, comment, "nachricht.html", original_html.encode("utf-8"))
    if skipped:
        log(ticket, None, "Anhänge nicht übernommen: " + ", ".join(skipped))


def process_message(raw):
    """Verarbeitet eine rohe E-Mail. Gibt das Ticket zurück oder None."""
    message = email.message_from_bytes(raw, policy=policy.default)
    if _is_automatic(message):
        return None
    name, address = parseaddr(str(message.get("From", "")))
    address = address.strip()
    if not _sender_allowed(address):
        return None

    user = user_for_email(address, name)
    if not user.is_active:
        return None

    subject = " ".join(str(message.get("Subject", "")).split()) or "(ohne Betreff)"
    body, original_html = _body_of(message)

    ticket = None
    match = TICKET_REF.search(subject)
    if match:
        candidate = (
            Ticket.objects.filter(pk=int(match.group(1)))
            .select_related("requester", "assignee", "team", "merged_into")
            .first()
        )
        # Antworten auf ein zusammengeführtes Ticket landen im Zielticket.
        if candidate is not None and candidate.merged_into_id:
            candidate = candidate.merged_into
        # Antworten dürfen: Bearbeiter, der Melder, Ansprechpartner der
        # Organisation und Adressen in Kopie.
        if candidate is not None and (
            can_view_ticket(user, candidate)
            or address.lower() in [a.lower() for a in candidate.cc_list]
        ):
            ticket = candidate

    with transaction.atomic():
        if ticket is None:
            ticket = Ticket.objects.create(
                title=subject[:200],
                description=body or "(kein Text)",
                requester=user,
                cc=", ".join(_cc_addresses(message)),
            )
            _save_attachments(message, ticket, user, None, original_html)
            created, comment = True, None
        else:
            comment = Comment.objects.create(
                ticket=ticket,
                author=user,
                body=strip_quoted_reply(body) or "(kein Text)",
            )
            _save_attachments(message, ticket, user, comment, original_html)
            created = False
            reopen = (Ticket.Status.WAITING, Ticket.Status.RESOLVED, Ticket.Status.CLOSED)
            if not user.is_staff and ticket.status in reopen:
                # Antwort des Melders: Ticket wieder in Bearbeitung nehmen.
                if not ticket.is_open:
                    log(ticket, user, "Durch E-Mail-Antwort wieder geöffnet")
                ticket.status = Ticket.Status.OPEN
                ticket.resolved_at = None
                ticket.save()

    if created:
        after_ticket_created(ticket, actor=None, source="E-Mail", confirm=True)
    elif user.is_staff and ticket.requester_id != user.id:
        mark_first_response(ticket)
        notify.ticket_reply(ticket, comment)
    else:
        notify.staff_requester_reply(ticket, comment)
    return ticket
