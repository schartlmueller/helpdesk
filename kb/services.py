import re

from django.db import connection
from django.db.models import Q

from .models import Article

WORD = re.compile(r"\w{3,}")
STOPWORDS = {
    "aber", "alle", "auch", "auf", "aus", "bei", "bin", "bis", "bitte", "das",
    "dass", "dem", "den", "der", "des", "die", "doch", "ein", "eine", "einem",
    "einen", "einer", "für", "geht", "habe", "hat", "ich", "ihr", "ist", "kann",
    "kein", "keine", "mehr", "mein", "meine", "mit", "nach", "nicht", "noch",
    "nur", "oder", "sehr", "seit", "sich", "sie", "sind", "und", "uns", "von",
    "vor", "war", "was", "wenn", "wie", "wir", "wird", "zum", "zur", "the", "and",
}


def visible_articles(user):
    """Veröffentlichte Artikel, die dieser Benutzer lesen darf.

    Artikel ohne Organisation sind für alle da; Artikel einer Organisation
    sehen nur deren Mitglieder und die Bearbeiter.
    """
    from core.orgs import membership_of

    published = Article.objects.filter(status=Article.Status.PUBLISHED)
    if user.is_staff:
        return published
    membership = membership_of(user)
    if membership is None:
        return published.filter(organization__isnull=True)
    return published.filter(
        Q(organization__isnull=True) | Q(organization=membership.organization)
    )


def _tokens(text, limit=15):
    words = []
    for word in WORD.findall(text.lower()):
        if word not in STOPWORDS and word not in words:
            words.append(word)
    return words[:limit]


def _fulltext(queryset, words, limit):
    """Volltextsuche von PostgreSQL mit deutscher Wortstammbildung.

    Findet auch gebeugte Formen ("Drucker" findet "druckt", "Druckers") und
    gewichtet Treffer im Titel am höchsten.
    """
    from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

    vector = (
        SearchVector("title", weight="A", config="german")
        + SearchVector("problem", weight="B", config="german")
        + SearchVector("solution", weight="C", config="german")
    )
    query = SearchQuery(" OR ".join(words), search_type="websearch", config="german")
    return list(
        queryset.annotate(rank=SearchRank(vector, query))
        .filter(rank__gt=0)
        .select_related("category")
        .order_by("-rank", "-views")[:limit]
    )


def _keywords(queryset, words, limit):
    """Einfache Teilwortsuche. Findet auch Wortteile ("Toner" in "Tonerkartusche")."""
    condition = Q()
    for word in words:
        condition |= (
            Q(title__icontains=word)
            | Q(problem__icontains=word)
            | Q(solution__icontains=word)
        )
    scored = []
    for article in queryset.filter(condition).select_related("category")[:500]:
        title = article.title.lower()
        body = f"{article.problem} {article.solution}".lower()
        score = sum(3 for w in words if w in title) + sum(1 for w in words if w in body)
        scored.append((score, article))
    scored.sort(key=lambda item: (-item[0], -item[1].views))
    return [article for _, article in scored[:limit]]


def search_articles(text, limit=5, queryset=None, exclude_pk=None):
    """Sucht veröffentlichte Artikel, beste Treffer zuerst.

    Auf PostgreSQL kommt zuerst die Volltextsuche, danach ergänzt die
    Teilwortsuche weitere Treffer. Auf anderen Datenbanken nur die Teilwortsuche.
    """
    words = _tokens(text)
    if not words:
        return []
    if queryset is None:
        queryset = Article.objects.filter(status=Article.Status.PUBLISHED)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)

    results = []
    if connection.vendor == "postgresql":
        results = _fulltext(queryset, words, limit)
    seen = {article.pk for article in results}
    for article in _keywords(queryset, words, limit):
        if article.pk not in seen and len(results) < limit:
            results.append(article)
            seen.add(article.pk)
    return results


def create_draft_from_ticket(ticket, user):
    """Legt aus einem gelösten Ticket einen Artikel-Entwurf an.

    Gibt (artikel, neu_oder_aktualisiert) zurück. Ein bereits veröffentlichter
    Artikel zum selben Ticket wird nicht überschrieben.
    """
    article = Article.objects.filter(source_ticket=ticket).first()
    if article is None:
        article = Article.objects.create(
            title=ticket.title,
            problem=ticket.description,
            solution=ticket.solution,
            category=ticket.category,
            source_ticket=ticket,
            author=user,
        )
        return article, True
    if article.status == Article.Status.DRAFT:
        article.solution = ticket.solution
        article.save()
        return article, True
    return article, False
