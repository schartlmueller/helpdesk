"""Abruf des IMAP-Postfachs."""

import imaplib
import json
import traceback
import urllib.parse
import urllib.request

from django.conf import settings

from .mail_in import process_message


def _oauth_token():
    """Holt ein Zugriffstoken für Microsoft 365 (App-Anmeldung ohne Benutzer)."""
    url = (
        "https://login.microsoftonline.com/"
        f"{settings.IMAP_OAUTH_TENANT}/oauth2/v2.0/token"
    )
    data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": settings.IMAP_OAUTH_CLIENT_ID,
            "client_secret": settings.IMAP_OAUTH_CLIENT_SECRET,
            "scope": "https://outlook.office365.com/.default",
        }
    ).encode()
    with urllib.request.urlopen(url, data=data, timeout=30) as response:
        return json.load(response)["access_token"]


def _connect():
    if settings.IMAP_SSL:
        conn = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
    else:
        conn = imaplib.IMAP4(settings.IMAP_HOST, settings.IMAP_PORT)
    if settings.IMAP_OAUTH_CLIENT_ID:
        auth = f"user={settings.IMAP_USER}\x01auth=Bearer {_oauth_token()}\x01\x01"
        conn.authenticate("XOAUTH2", lambda _: auth.encode())
    else:
        conn.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
    return conn


def fetch_mail(write=print):
    """Verarbeitet alle ungelesenen E-Mails. Gibt die Anzahl der Tickets zurück."""
    conn = _connect()
    count = 0
    try:
        conn.select(settings.IMAP_FOLDER)
        # Fehlgeschlagene E-Mails werden markiert ("Flagged") und nicht
        # endlos erneut versucht; sie bleiben im Postfach zur Kontrolle.
        _, data = conn.search(None, "UNSEEN", "UNFLAGGED")
        for number in data[0].split():
            _, parts = conn.fetch(number, "(BODY.PEEK[])")
            raw = next(
                (p[1] for p in parts if isinstance(p, tuple) and len(p) > 1), None
            )
            if raw is None:
                continue
            try:
                ticket = process_message(raw)
            except Exception:
                write(traceback.format_exc())
                conn.store(number, "+FLAGS", "\\Flagged")
                continue
            conn.store(number, "+FLAGS", "\\Seen")
            if ticket is not None:
                count += 1
                write(f"E-Mail verarbeitet: Ticket #{ticket.pk}")
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return count
