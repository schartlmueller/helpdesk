"""Schlanke JSON-Schnittstelle für andere Systeme (z. B. Monitoring, Formulare).

Anmeldung über den Kopf  "Authorization: Token <Schlüssel>".
Schlüssel werden unter Verwaltung → API-Schlüssel angelegt und handeln mit
den Rechten ihres Benutzers: Bearbeiter sehen alle Tickets, andere nur eigene.
"""

import json
from functools import wraps

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from kb.services import search_articles, visible_articles
from tickets import notify
from tickets.models import Category, Comment, Ticket
from core.orgs import ticket_filter
from tickets.services import (
    after_ticket_created,
    mark_first_response,
    search_tickets,
    user_for_email,
)

from .models import ApiToken


def _error(message, status):
    return JsonResponse({"error": message}, status=status)


def api_view(*methods):
    def decorator(view):
        @csrf_exempt
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return _error("Methode nicht erlaubt", 405)
            scheme, _, key = request.headers.get("Authorization", "").partition(" ")
            token = None
            if scheme.lower() == "token" and key.strip():
                token = (
                    ApiToken.objects.select_related("user").filter(key=key.strip()).first()
                )
            if token is None or not token.user.is_active:
                return _error("Ungültiger oder fehlender API-Schlüssel", 401)
            ApiToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
            request.api_user = token.user
            request.data = {}
            if request.method == "POST":
                try:
                    request.data = json.loads(request.body or b"{}")
                except ValueError:
                    return _error("Ungültiges JSON", 400)
                if not isinstance(request.data, dict):
                    return _error("JSON-Objekt erwartet", 400)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def _iso(moment):
    return moment.isoformat() if moment else None


def _name(user):
    return (user.get_full_name() or user.username) if user else None


def _ticket_json(ticket, comments=None):
    data = {
        "id": ticket.pk,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
        "priority": ticket.priority,
        "kind": ticket.kind or None,
        "category": ticket.category.name if ticket.category else None,
        "organization": ticket.organization.name if ticket.organization else None,
        "requester": _name(ticket.requester),
        "requester_email": ticket.requester.email,
        "assignee": _name(ticket.assignee),
        "solution": ticket.solution,
        "created_at": _iso(ticket.created_at),
        "due_at": _iso(ticket.due_at),
        "response_due_at": _iso(ticket.response_due_at),
        "first_response_at": _iso(ticket.first_response_at),
        "resolved_at": _iso(ticket.resolved_at),
        "url": ticket.get_absolute_url(),
    }
    if comments is not None:
        data["comments"] = [
            {
                "author": _name(c.author),
                "body": c.body,
                "internal": c.internal,
                "is_solution": c.is_solution,
                "created_at": _iso(c.created_at),
            }
            for c in comments
        ]
    return data


def _tickets_for(user):
    qs = Ticket.objects.select_related("requester", "assignee", "category", "organization")
    return qs if user.is_staff else qs.filter(ticket_filter(user))


@api_view("GET", "POST")
def tickets(request):
    user = request.api_user
    if request.method == "GET":
        qs = _tickets_for(user)
        status = request.GET.get("status", "")
        if status in Ticket.Status.values:
            qs = qs.filter(status=status)
        query = request.GET.get("q", "").strip()
        if query:
            qs = search_tickets(qs, query, staff=user.is_staff)
        return JsonResponse({"tickets": [_ticket_json(t) for t in qs[:100]]})

    data = request.data
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    if not title or not description:
        return _error("title und description sind erforderlich", 400)
    priority = data.get("priority", Ticket.Priority.NORMAL)
    if priority not in Ticket.Priority.values:
        return _error("priority muss low, normal, high oder urgent sein", 400)

    kind = str(data.get("kind", "") or "")
    if kind and kind not in Ticket.Kind.values:
        return _error("kind muss bug, feature oder nice sein", 400)

    requester = user
    email = str(data.get("requester_email", "")).strip()
    if email:
        if not user.is_staff:
            return _error("requester_email dürfen nur Bearbeiter setzen", 403)
        if "@" not in email:
            return _error("requester_email ist keine E-Mail-Adresse", 400)
        requester = user_for_email(email, str(data.get("requester_name", "")))
    category = None
    if data.get("category"):
        category = Category.objects.filter(name__iexact=str(data["category"])).first()

    ticket = Ticket.objects.create(
        title=title[:200],
        description=description,
        priority=priority,
        kind=kind,
        category=category,
        requester=requester,
    )
    after_ticket_created(
        ticket, actor=user, source="Schnittstelle", confirm=requester.id != user.id
    )
    return JsonResponse(_ticket_json(ticket), status=201)


def _get_ticket(request, pk):
    return _tickets_for(request.api_user).filter(pk=pk).first()


@api_view("GET")
def ticket_detail(request, pk):
    ticket = _get_ticket(request, pk)
    if ticket is None:
        return _error("Ticket nicht gefunden", 404)
    comments = ticket.comments.select_related("author")
    if not request.api_user.is_staff:
        comments = comments.filter(internal=False)
    return JsonResponse(_ticket_json(ticket, comments))


@api_view("POST")
def ticket_comments(request, pk):
    user = request.api_user
    ticket = _get_ticket(request, pk)
    if ticket is None:
        return _error("Ticket nicht gefunden", 404)
    body = str(request.data.get("body", "")).strip()
    if not body:
        return _error("body ist erforderlich", 400)
    comment = Comment.objects.create(
        ticket=ticket,
        author=user,
        body=body,
        internal=bool(request.data.get("internal")) and user.is_staff,
    )
    if user.is_staff and not comment.internal and ticket.requester_id != user.id:
        mark_first_response(ticket)
        notify.ticket_reply(ticket, comment)
    elif not user.is_staff:
        notify.staff_requester_reply(ticket, comment)
    return JsonResponse({"ok": True, "ticket": ticket.pk}, status=201)


def _article_json(article, full=False):
    data = {
        "id": article.pk,
        "title": article.title,
        "category": article.category.name if article.category else None,
        "url": article.get_absolute_url(),
        "updated_at": _iso(article.updated_at),
    }
    if full:
        data["problem"] = article.problem
        data["solution"] = article.solution
    return data


@api_view("GET")
def articles(request):
    query = request.GET.get("q", "").strip()
    if query:
        found = search_articles(query, limit=20, queryset=visible_articles(request.api_user))
    else:
        found = visible_articles(request.api_user).select_related("category")[:50]
    return JsonResponse({"articles": [_article_json(a) for a in found]})


@api_view("GET")
def article_detail(request, pk):
    article = (
        visible_articles(request.api_user).filter(pk=pk).select_related("category").first()
    )
    if article is None:
        return _error("Artikel nicht gefunden", 404)
    return JsonResponse(_article_json(article, full=True))
