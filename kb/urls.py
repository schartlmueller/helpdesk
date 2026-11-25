from django.urls import path

from . import views

app_name = "kb"

urlpatterns = [
    path("", views.article_list, name="list"),
    path("entwuerfe/", views.article_drafts, name="drafts"),
    path("vorschlaege/", views.suggest, name="suggest"),
    path("neu/", views.article_create, name="create"),
    path("datei/<int:pk>/", views.article_file, name="file"),
    path("datei/<int:pk>/loeschen/", views.article_file_delete, name="file_delete"),
    path("<int:pk>/", views.article_detail, name="detail"),
    path("<int:pk>/bearbeiten/", views.article_edit, name="edit"),
    path("<int:pk>/hochladen/", views.article_upload, name="upload"),
    path("<int:pk>/bewertung/", views.article_vote, name="vote"),
    path("<int:pk>/freigeben/", views.article_publish, name="publish"),
    path("<int:pk>/archivieren/", views.article_archive, name="archive"),
]
