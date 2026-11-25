from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("tickets/", views.tickets, name="tickets"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("tickets/<int:pk>/comments/", views.ticket_comments, name="ticket_comments"),
    path("articles/", views.articles, name="articles"),
    path("articles/<int:pk>/", views.article_detail, name="article_detail"),
]
