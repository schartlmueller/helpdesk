from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("neu/", views.project_create, name="create"),
    path("<int:pk>/", views.project_detail, name="detail"),
    path("<int:pk>/bearbeiten/", views.project_edit, name="edit"),
    path("<int:pk>/aufgabe/", views.task_create, name="task_create"),
    path("<int:pk>/meilenstein/", views.milestone_add, name="milestone_add"),
    path("<int:pk>/reihenfolge/", views.board_reorder, name="reorder"),
    path("meilenstein/<int:pk>/", views.milestone_change, name="milestone_change"),
    path("aufgabe/<int:pk>/", views.task_detail, name="task_detail"),
    path("aufgabe/<int:pk>/kommentar/", views.task_comment, name="task_comment"),
    path("aufgabe/<int:pk>/uhr/", views.task_timer, name="task_timer"),
    path("aufgabe/<int:pk>/zeit/", views.task_time_add, name="task_time_add"),
]
