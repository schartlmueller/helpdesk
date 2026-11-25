from django.urls import path

from . import billing, planner, pool, stats, views

app_name = "tickets"

urlpatterns = [
    path("", views.ticket_list, name="list"),
    path("neu/", views.ticket_create, name="create"),
    path("neu/formular/<int:pk>/", views.request_form_create, name="request_form"),
    path("zeiten/", views.time_report, name="times"),
    path("statistik/", stats.statistics, name="stats"),
    path("leistungsnachweis/", billing.service_report, name="service_report"),
    path("pool/", pool.pool, name="pool"),
    path("pool/hinzufuegen/", pool.pool_add, name="pool_add"),
    path("pool/uebertragen/", pool.pool_carry, name="pool_carry"),
    path("pool/<int:pk>/uebernehmen/", pool.pool_take, name="pool_take"),
    path("pool/<int:pk>/zuordnen/", pool.pool_assign, name="pool_assign"),
    path("pool/<int:pk>/freigeben/", pool.pool_release, name="pool_release"),
    path("pool/<int:pk>/entfernen/", pool.pool_remove, name="pool_remove"),
    path("planung/", planner.planner, name="planner"),
    path("planung/verschieben/", planner.planner_move, name="planner_move"),
    path("planung/einstellungen/", planner.planner_settings, name="planner_settings"),
    path("planung/abwesenheit/", planner.absence_add, name="absence_add"),
    path("planung/abwesenheit/<int:pk>/loeschen/", planner.absence_delete, name="absence_delete"),
    path("wiederkehrend/", planner.recurring_list, name="recurring"),
    path("wiederkehrend/neu/", planner.recurring_edit, name="recurring_create"),
    path("wiederkehrend/<int:pk>/", planner.recurring_edit, name="recurring_edit"),
    path("anhang/<int:pk>/", views.attachment_download, name="attachment"),
    path("<int:pk>/", views.ticket_detail, name="detail"),
    path("<int:pk>/aendern/", views.ticket_update, name="update"),
    path("<int:pk>/kommentar/", views.ticket_comment, name="comment"),
    path("<int:pk>/start/", views.ticket_start, name="start"),
    path("<int:pk>/pause/", views.ticket_pause, name="pause"),
    path("<int:pk>/zeit/", views.ticket_time_add, name="time_add"),
    path("<int:pk>/zusammenfuehren/", views.ticket_merge, name="merge"),
    path("<int:pk>/loesen/", views.ticket_resolve, name="resolve"),
    path("<int:pk>/checkliste/", views.checklist_add, name="checklist_add"),
    path("<int:pk>/checkliste/<int:item_pk>/", views.checklist_change, name="checklist_change"),
    path("<int:pk>/verknuepfen/", views.ticket_link, name="link"),
    path("<int:pk>/verknuepfung/<int:other_pk>/loesen/", views.ticket_unlink, name="unlink"),
    path("<int:pk>/oeffnen/", views.ticket_reopen, name="reopen"),
]
