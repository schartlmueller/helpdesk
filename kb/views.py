from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import staff_required
from tickets.models import Category

from .forms import ArticleFileForm, ArticleForm
from .models import Article, ArticleFile, ArticleVote
from .services import search_articles, visible_articles


@login_required
def article_list(request):
    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("kategorie", "")
    published = visible_articles(request.user)
    if category_id.isdigit():
        published = published.filter(category_id=int(category_id))

    if query:
        articles = search_articles(query, limit=200, queryset=published)
    else:
        articles = published.select_related("category")
    page = Paginator(articles, 30).get_page(request.GET.get("seite"))
    params = request.GET.copy()
    params.pop("seite", None)

    return render(
        request,
        "kb/list.html",
        {
            "articles": page,
            "page": page,
            "params": params.urlencode(),
            "query": query,
            "category_id": category_id,
            "categories": Category.objects.all(),
        },
    )


def _may_read(user, article):
    if user.is_staff:
        return True
    return visible_articles(user).filter(pk=article.pk).exists()


@staff_required
def article_drafts(request):
    drafts = Article.objects.filter(status=Article.Status.DRAFT).select_related(
        "category", "source_ticket", "author"
    )
    return render(request, "kb/drafts.html", {"drafts": drafts})


@login_required
def article_detail(request, pk):
    article = get_object_or_404(
        Article.objects.select_related("category", "source_ticket"), pk=pk
    )
    if not _may_read(request.user, article):
        raise Http404
    if article.status == Article.Status.PUBLISHED:
        Article.objects.filter(pk=pk).update(views=F("views") + 1)
    context = {
        "article": article,
        "my_vote": ArticleVote.objects.filter(article=article, user=request.user).first(),
    }
    if request.user.is_staff:
        context["votes"] = article.votes.aggregate(
            yes=Count("id", filter=Q(helpful=True)),
            no=Count("id", filter=Q(helpful=False)),
        )
    return render(request, "kb/detail.html", context)


@require_POST
@login_required
def article_vote(request, pk):
    """Rückmeldung: Hat der Artikel geholfen?"""
    article = get_object_or_404(visible_articles(request.user), pk=pk)
    ArticleVote.objects.update_or_create(
        article=article,
        user=request.user,
        defaults={"helpful": request.POST.get("helpful") == "1"},
    )
    messages.success(request, "Danke für die Rückmeldung.")
    return redirect(article)


@staff_required
def article_create(request):
    form = ArticleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        article = form.save(commit=False)
        article.author = request.user
        article.save()
        messages.success(request, "Entwurf gespeichert. Bilder lassen sich jetzt hochladen.")
        return redirect("kb:edit", pk=article.pk)
    return render(request, "kb/form.html", {"form": form, "article": None})


@staff_required
def article_edit(request, pk):
    article = get_object_or_404(Article, pk=pk)
    form = ArticleForm(request.POST or None, instance=article)
    if request.method == "POST" and form.is_valid():
        form.save()
        if "publish" in request.POST:
            _publish(article, request.user)
            messages.success(request, "Artikel gespeichert und veröffentlicht.")
        else:
            messages.success(request, "Artikel gespeichert.")
        return redirect(article)

    similar = []
    if article.status == Article.Status.DRAFT:
        # Hinweis auf mögliche Dubletten, bevor der Entwurf freigegeben wird.
        similar = search_articles(
            f"{article.title} {article.problem[:300]}", limit=4, exclude_pk=article.pk
        )
    return render(
        request,
        "kb/form.html",
        {
            "form": form,
            "article": article,
            "similar": similar,
            "file_form": ArticleFileForm(),
            "files": article.files.all(),
        },
    )


def _publish(article, user):
    article.status = Article.Status.PUBLISHED
    article.reviewed_by = user
    article.published_at = timezone.now()
    article.save()


@require_POST
@staff_required
def article_publish(request, pk):
    article = get_object_or_404(Article, pk=pk)
    _publish(article, request.user)
    messages.success(request, "Artikel veröffentlicht.")
    return redirect(article)


@require_POST
@staff_required
def article_archive(request, pk):
    article = get_object_or_404(Article, pk=pk)
    article.status = Article.Status.ARCHIVED
    article.save()
    messages.info(request, "Artikel archiviert.")
    return redirect("kb:list")


@require_POST
@staff_required
def article_upload(request, pk):
    article = get_object_or_404(Article, pk=pk)
    form = ArticleFileForm(request.POST, request.FILES)
    if form.is_valid():
        for upload in form.cleaned_data["files"]:
            ArticleFile.objects.create(
                article=article,
                file=upload,
                name=(upload.name or "datei")[:255],
                uploaded_by=request.user,
            )
    else:
        errors = " ".join(e for errs in form.errors.values() for e in errs)
        messages.error(request, errors)
    return redirect("kb:edit", pk=pk)


@require_POST
@staff_required
def article_file_delete(request, pk):
    item = get_object_or_404(ArticleFile, pk=pk)
    article_pk = item.article_id
    item.delete()
    return redirect("kb:edit", pk=article_pk)


@login_required
def article_file(request, pk):
    """Liefert ein Bild oder eine Datei eines Artikels aus."""
    item = get_object_or_404(ArticleFile.objects.select_related("article"), pk=pk)
    if not _may_read(request.user, item.article):
        raise Http404
    try:
        handle = item.file.open("rb")
    except FileNotFoundError:
        raise Http404
    if item.image_type:
        # Nur echte Bildformate werden im Browser angezeigt.
        response = FileResponse(handle, content_type=item.image_type)
    else:
        response = FileResponse(handle, as_attachment=True, filename=item.name)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
def suggest(request):
    """Artikelvorschläge während der Ticket-Eingabe."""
    articles = search_articles(
        request.GET.get("q", ""), limit=5, queryset=visible_articles(request.user)
    )
    return JsonResponse(
        {
            "results": [
                {"title": a.title, "url": a.get_absolute_url()} for a in articles
            ]
        }
    )
