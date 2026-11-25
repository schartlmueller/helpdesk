"""Texthilfen für eingehende E-Mails. Bewusst ohne Django, damit einzeln testbar."""

import html
import re

_WROTE = re.compile(r"^\s*(Am|On)\s.{5,200}\s(schrieb|wrote)\b.*:\s*$", re.I)
_ORIGINAL = re.compile(
    r"^\s*-{2,}\s*(Ursprüngliche Nachricht|Original Message|Weitergeleitete Nachricht|Forwarded message)\s*-{2,}\s*$",
    re.I,
)
_RULE = re.compile(r"^\s*_{10,}\s*$")
_HEADER_FROM = re.compile(r"^\s*(Von|From):\s.+$", re.I)
_HEADER_NEXT = re.compile(r"^\s*(Gesendet|Sent|Datum|Date|An|To):\s", re.I)


def _is_quote_start(lines, i):
    line = lines[i]
    if _WROTE.match(line) or _ORIGINAL.match(line) or _RULE.match(line):
        return True
    # "Am ... schrieb ...:" wird von manchen Programmen auf zwei Zeilen umbrochen.
    if i + 1 < len(lines) and _WROTE.match(f"{line} {lines[i + 1]}"):
        return True
    # Outlook: Kopfzeilenblock "Von: ... / Gesendet: ..."
    if _HEADER_FROM.match(line):
        return any(_HEADER_NEXT.match(nxt) for nxt in lines[i + 1 : i + 4])
    return False


def strip_quoted_reply(text):
    """Schneidet den zitierten Verlauf am Ende einer Antwort-E-Mail ab."""
    lines = text.replace("\r\n", "\n").split("\n")
    cut = len(lines)
    for i in range(len(lines)):
        if _is_quote_start(lines, i):
            cut = i
            break
    kept = lines[:cut]
    while kept and (kept[-1].lstrip().startswith(">") or not kept[-1].strip()):
        kept.pop()
    result = "\n".join(kept).strip()
    # Lieber alles behalten als eine leere Nachricht speichern.
    return result or text.strip()


def html_to_text(markup):
    """Wandelt eine HTML-E-Mail in lesbaren Text mit Absätzen um."""
    markup = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", markup)
    markup = re.sub(r"(?i)<br\s*/?>", "\n", markup)
    markup = re.sub(r"(?i)</(p|div|tr|li|h[1-6]|blockquote)>", "\n", markup)
    text = re.sub(r"(?s)<[^>]+>", "", markup)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
