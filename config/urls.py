from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core import views as core_views
from core.brands import brand_for
from core.forms import SetOrResetPasswordForm, ThrottledAuthenticationForm
from tickets.planner import calendar_feed

urlpatterns = [
    path("", core_views.dashboard, name="dashboard"),
    path(
        "login/",
        auth_views.LoginView.as_view(authentication_form=ThrottledAuthenticationForm),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Passwort ändern, erstmals setzen oder zurücksetzen
    path("passwort/aendern/", auth_views.PasswordChangeView.as_view(), name="password_change"),
    path("passwort/geaendert/", auth_views.PasswordChangeDoneView.as_view(), name="password_change_done"),
    path(
        "passwort/vergessen/",
        auth_views.PasswordResetView.as_view(
            form_class=SetOrResetPasswordForm,
            # E-Mails entstehen ohne Seitenaufruf-Kontext; hier gilt die Grundeinstellung.
            extra_email_context={"brand": brand_for()},
        ),
        name="password_reset",
    ),
    path("passwort/gesendet/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "passwort/neu/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("passwort/fertig/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    # Kalender-Feed für Outlook; der geheime Teil der Adresse ersetzt die Anmeldung
    path("kalender/<str:token>.ics", calendar_feed, name="calendar_feed"),
    path("meldungen/", core_views.announcement_list, name="announcements"),
    path("meldungen/neu/", core_views.announcement_edit, name="announcement_create"),
    path("meldungen/<int:pk>/", core_views.announcement_edit, name="announcement_edit"),
    path("meldungen/<int:pk>/beenden/", core_views.announcement_end, name="announcement_end"),
    path("organisationen/", core_views.organization_list, name="organizations"),
    path("organisationen/neu/", core_views.organization_edit, name="organization_create"),
    path("organisationen/<int:pk>/", core_views.organization_edit, name="organization_edit"),
    path("tickets/", include("tickets.urls")),
    path("wissen/", include("kb.urls")),
    path("projekte/", include("projects.urls")),
    path("api/", include("api.urls")),
    path("admin/", admin.site.urls),
]

if settings.SSO_ENABLED:
    urlpatterns.append(path("oidc/", include("mozilla_django_oidc.urls")))

admin.site.site_header = f"{brand_for()['name']} Verwaltung"
admin.site.site_title = brand_for()["name"]
