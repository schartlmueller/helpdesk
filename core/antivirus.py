"""Virenprüfung über einen ClamAV-Dienst (clamd, INSTREAM-Protokoll)."""

import socket
import struct

from django.conf import settings


class ScanError(Exception):
    pass


def scan(fileobj):
    """Gibt den Namen des gefundenen Schädlings zurück oder None.

    Ohne CLAMAV_HOST findet keine Prüfung statt. Ist der Dienst eingerichtet,
    aber nicht erreichbar, wird ScanError ausgelöst (Upload wird abgelehnt).
    """
    if not settings.CLAMAV_HOST:
        return None
    try:
        with socket.create_connection(
            (settings.CLAMAV_HOST, settings.CLAMAV_PORT), timeout=60
        ) as conn:
            conn.sendall(b"zINSTREAM\0")
            fileobj.seek(0)
            while True:
                chunk = fileobj.read(8192)
                if not chunk:
                    break
                conn.sendall(struct.pack("!I", len(chunk)) + chunk)
            conn.sendall(struct.pack("!I", 0))
            reply = conn.recv(4096).decode("utf-8", "replace").strip("\0\n ")
    except OSError as exc:
        raise ScanError(str(exc)) from exc
    finally:
        fileobj.seek(0)
    if reply.endswith("FOUND"):
        return reply.split(":", 1)[-1].replace("FOUND", "").strip() or "unbekannt"
    if reply.endswith("OK"):
        return None
    raise ScanError(reply)
