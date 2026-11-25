import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from api.models import ApiToken
from kb.models import Article, ArticleVote
from projects.models import Milestone, Project, Task
from tickets import maintenance
from tickets.models import Comment, Team, Ticket, TicketEvent, TimeEntry
from tickets.sla import due_for


class Base(TestCase):
    def setUp(self):
        User = get_user_model()
        self.agent = User.objects.create_user(
            "agent", email="agent@example.com", password="pw", is_staff=True
        )
        self.second = User.objects.create_user(
            "zweiter", email="zweiter@example.com", password="pw", is_staff=True
        )
        self.user = User.objects.create_user("anna", email="anna@example.com", password="pw")
        self.ticket = Ticket.objects.create(
            title="Monitor flackert", description="Seit heute.", requester=self.user
        )
        mail.outbox.clear()


class TicketWorkflowTests(Base):
    def test_staff_is_notified_about_new_ticket_and_requester_reply(self):
        self.client.login(username="anna", password="pw")
        self.client.post(
            reverse("tickets:create"),
            {"title": "Neu", "description": "Text", "priority": "normal"},
        )
        recipients = {r for m in mail.outbox for r in m.to}
        self.assertEqual(recipients, {"agent@example.com", "zweiter@example.com"})

        mail.outbox.clear()
        self.ticket.assignee = self.agent
        self.ticket.save()
        self.client.post(reverse("tickets:comment", args=[self.ticket.pk]), {"body": "Hallo?"})
        self.assertEqual([m.to for m in mail.outbox], [["agent@example.com"]])

    def test_staff_creates_ticket_on_behalf_of_new_person(self):
        self.client.login(username="agent", password="pw")
        self.client.post(
            reverse("tickets:create"),
            {
                "title": "Anruf: Maus defekt",
                "description": "Per Telefon gemeldet.",
                "priority": "high",
                "requester_email": "neu@example.com",
            },
        )
        ticket = Ticket.objects.get(title="Anruf: Maus defekt")
        self.assertEqual(ticket.requester.email, "neu@example.com")
        self.assertFalse(ticket.requester.has_usable_password())
        self.assertIn(["neu@example.com"], [m.to for m in mail.outbox])

    def test_update_writes_history_and_notifies_new_assignee(self):
        self.client.login(username="agent", password="pw")
        self.client.post(
            reverse("tickets:update", args=[self.ticket.pk]),
            {"status": "open", "priority": "urgent", "assignee": self.second.pk, "cc": "chef@example.com"},
        )
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.second)
        text = " ".join(TicketEvent.objects.filter(ticket=self.ticket).values_list("text", flat=True))
        self.assertIn("Neu → In Bearbeitung", text)
        self.assertIn("Normal → Dringend", text)
        self.assertIn(["zweiter@example.com"], [m.to for m in mail.outbox])
        # Statuswechsel auf "In Bearbeitung" startet die Uhr des Handelnden
        self.assertTrue(TimeEntry.objects.filter(ticket=self.ticket, user=self.agent).exists())

    def test_cc_receives_replies(self):
        self.ticket.cc = "chef@example.com"
        self.ticket.save()
        self.client.login(username="agent", password="pw")
        self.client.post(reverse("tickets:comment", args=[self.ticket.pk]), {"body": "Wir sind dran."})
        self.assertEqual(mail.outbox[0].to, ["anna@example.com"])
        self.assertEqual(mail.outbox[0].cc, ["chef@example.com"])

    def test_merge_moves_everything_and_closes_source(self):
        other = Ticket.objects.create(title="Monitor kaputt", description="Doppelt.", requester=self.user)
        Comment.objects.create(ticket=other, author=self.user, body="Noch immer.")
        self.client.login(username="agent", password="pw")
        self.client.post(reverse("tickets:merge", args=[other.pk]), {"target": self.ticket.pk})
        other.refresh_from_db()
        self.assertEqual(other.status, Ticket.Status.CLOSED)
        self.assertEqual(other.merged_into, self.ticket)
        self.assertEqual(self.ticket.comments.count(), 2)
        self.assertEqual(self.client.get(reverse("tickets:detail", args=[other.pk])).status_code, 200)

    def test_manual_time_and_csv_export(self):
        self.client.login(username="agent", password="pw")
        today = timezone.localdate()
        self.client.post(
            reverse("tickets:time_add", args=[self.ticket.pk]),
            {"date": today.isoformat(), "start": "09:00", "minutes": "45", "note": "vor Ort"},
        )
        entry = TimeEntry.objects.get()
        self.assertEqual(entry.seconds, 45 * 60)
        response = self.client.get(reverse("tickets:times"), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("vor Ort", response.content.decode())

    def test_category_routes_to_team(self):
        from tickets.models import Category

        team = Team.objects.create(name="Netzwerk-Team")
        team.members.add(self.second)
        category = Category.objects.create(name="Netz", team=team)
        ticket = Ticket.objects.create(
            title="WLAN", description="x", requester=self.user, category=category
        )
        self.assertEqual(ticket.team, team)


class MaintenanceTests(Base):
    def test_overdue_ticket_is_escalated_once(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(
            due_at=timezone.now() - timedelta(hours=1)
        )
        self.assertEqual(maintenance.escalate_overdue(), 1)
        self.assertEqual(maintenance.escalate_overdue(), 0)
        self.assertIn("ÜBERFÄLLIG", mail.outbox[0].subject)

    @override_settings(TIMER_MAX_HOURS=10)
    def test_forgotten_timer_is_stopped(self):
        entry = TimeEntry.objects.create(
            ticket=self.ticket, user=self.agent, started_at=timezone.now() - timedelta(hours=30)
        )
        self.assertEqual(maintenance.stop_stale_timers(), 1)
        entry.refresh_from_db()
        self.assertEqual(entry.seconds, 10 * 3600)

    @override_settings(RETENTION_DAYS=30)
    def test_old_closed_tickets_are_purged(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(
            status=Ticket.Status.CLOSED, updated_at=timezone.now() - timedelta(days=40)
        )
        self.assertEqual(maintenance.purge_old_tickets(), 1)
        self.assertFalse(Ticket.objects.exists())

    @override_settings(SLA_BUSINESS_HOURS=True, SLA_HOURS={"urgent": 4, "high": 8, "normal": 24, "low": 56})
    def test_due_date_respects_business_hours(self):
        import datetime as dt
        from zoneinfo import ZoneInfo

        friday_afternoon = dt.datetime(2026, 11, 27, 16, 0, tzinfo=ZoneInfo("Europe/Vienna"))
        due = timezone.localtime(due_for("high", friday_afternoon))
        self.assertEqual((due.weekday(), due.hour), (0, 15))  # Montag 15 Uhr


class AccountTests(Base):
    def test_login_is_locked_after_repeated_failures(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "anna", "password": "falsch"})
        response = self.client.post(reverse("login"), {"username": "anna", "password": "pw"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Zu viele Fehlversuche")

    def test_user_without_password_can_set_one(self):
        User = get_user_model()
        user = User(username="mail@example.com", email="mail@example.com")
        user.set_unusable_password()
        user.save()
        self.client.post(reverse("password_reset"), {"email": "mail@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/passwort/neu/", mail.outbox[0].body)


class KnowledgeBaseTests(Base):
    def setUp(self):
        super().setUp()
        self.article = Article.objects.create(
            title="Monitor flackert nach Update",
            problem="Der Bildschirm **flackert**.\n\n<script>alert(1)</script>",
            solution="1. Treiber neu installieren\n2. Neustart",
            status=Article.Status.PUBLISHED,
        )

    def test_markdown_is_rendered_and_scripts_are_removed(self):
        self.client.login(username="anna", password="pw")
        response = self.client.get(reverse("kb:detail", args=[self.article.pk]))
        self.assertContains(response, "<strong>flackert</strong>", html=False)
        self.assertNotContains(response, "<script>alert(1)</script>", html=False)
        self.assertContains(response, "<li>Treiber neu installieren</li>", html=False)

    def test_vote_is_stored_once_per_user(self):
        self.client.login(username="anna", password="pw")
        url = reverse("kb:vote", args=[self.article.pk])
        self.client.post(url, {"helpful": "1"})
        self.client.post(url, {"helpful": "0"})
        vote = ArticleVote.objects.get()
        self.assertFalse(vote.helpful)

    def test_draft_edit_page_warns_about_similar_article(self):
        draft = Article.objects.create(
            title="Monitor flackert", problem="Bildschirm flackert", solution="x"
        )
        self.client.login(username="agent", password="pw")
        response = self.client.get(reverse("kb:edit", args=[draft.pk]))
        self.assertContains(response, "Gibt es diesen Artikel schon?")


class ProjectTests(Base):
    def test_board_task_page_timer_and_timeline(self):
        self.client.login(username="agent", password="pw")
        project = Project.objects.create(name="Umzug Serverraum")
        milestone = Milestone.objects.create(
            project=project, name="Racks stehen", due_date=timezone.localdate() + timedelta(days=10)
        )
        task = Task.objects.create(
            project=project, title="Kabel ziehen", milestone=milestone,
            due_date=timezone.localdate() + timedelta(days=5),
        )
        self.assertEqual(self.client.get(reverse("projects:detail", args=[project.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("projects:task_detail", args=[task.pk])).status_code, 200)

        self.client.post(reverse("projects:task_timer", args=[task.pk]), {"action": "start"})
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.DOING)
        self.assertEqual(TimeEntry.objects.filter(task=task, ended_at__isnull=True).count(), 1)

        self.client.post(reverse("projects:task_comment", args=[task.pk]), {"body": "Erledigt bis Rack 3."})
        self.assertEqual(task.comments.count(), 1)

        self.client.post(reverse("projects:milestone_change", args=[milestone.pk]))
        milestone.refresh_from_db()
        self.assertTrue(milestone.done)
        self.assertEqual(self.client.get(reverse("tickets:times")).status_code, 200)


class ApiTests(Base):
    def setUp(self):
        super().setUp()
        self.token = ApiToken.objects.create(user=self.agent, name="Test")
        self.auth = {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def test_requires_token(self):
        self.assertEqual(self.client.get("/api/tickets/").status_code, 401)

    def test_create_list_and_comment(self):
        response = self.client.post(
            "/api/tickets/",
            data=json.dumps(
                {"title": "Platte voll", "description": "Server01 bei 95 %", "priority": "urgent",
                 "requester_email": "monitoring@example.com"}
            ),
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        ticket_id = response.json()["id"]

        listing = self.client.get("/api/tickets/", {"q": "Platte"}, **self.auth).json()
        self.assertEqual([t["id"] for t in listing["tickets"]], [ticket_id])

        response = self.client.post(
            f"/api/tickets/{ticket_id}/comments/",
            data=json.dumps({"body": "Wird bereinigt.", "internal": True}),
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        detail = self.client.get(f"/api/tickets/{ticket_id}/", **self.auth).json()
        self.assertTrue(detail["comments"][0]["internal"])


class PlanningTests(Base):
    def setUp(self):
        super().setUp()
        self.client.login(username="agent", password="pw")
        today = timezone.localdate()
        self.monday = today + timedelta(days=7 - today.weekday())  # nächster Montag

    def move(self, **payload):
        return self.client.post(
            reverse("tickets:planner_move"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_drag_plans_ticket_and_assigns_it(self):
        self.assertEqual(self.client.get(reverse("tickets:planner")).status_code, 200)
        response = self.move(
            kind="ticket", id=self.ticket.pk, date=self.monday.isoformat(), user=self.second.pk
        )
        self.assertEqual(response.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.planned_for, self.monday)
        self.assertEqual(self.ticket.assignee, self.second)
        self.assertIn(["zweiter@example.com"], [m.to for m in mail.outbox])

        page = self.client.get(reverse("tickets:planner"), {"woche": self.monday.isoformat()})
        self.assertContains(page, "Monitor flackert")

        # Zurück in "Noch nicht geplant": Termin weg, Bearbeiter bleibt
        self.move(kind="ticket", id=self.ticket.pk, date=None, keep_user=True)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.planned_for)
        self.assertEqual(self.ticket.assignee, self.second)

    def test_tasks_and_absences_show_in_week(self):
        from tickets.models import Absence

        project = Project.objects.create(name="Umzug")
        Task.objects.create(
            project=project, title="Switch tauschen", assignee=self.agent,
            planned_for=self.monday, estimated_minutes=600,
        )
        self.client.post(
            reverse("tickets:absence_add"),
            {
                "user": self.second.pk,
                "start_date": self.monday.isoformat(),
                "end_date": (self.monday + timedelta(days=2)).isoformat(),
                "reason": "Urlaub",
            },
        )
        self.assertEqual(Absence.objects.count(), 1)
        page = self.client.get(reverse("tickets:planner"), {"woche": self.monday.isoformat()})
        self.assertContains(page, "Switch tauschen")
        self.assertContains(page, "Urlaub")
        self.assertContains(page, "10:00 h / 8:00 h")  # überbucht: 10 von 8 Stunden

    def test_recurring_ticket_is_created_once_and_rescheduled(self):
        from tickets.models import RecurringTicket

        today = timezone.localdate()
        item = RecurringTicket.objects.create(
            title="Backups prüfen", description="Rücksicherung testen.",
            requester=self.agent, assignee=self.second,
            interval="monthly", next_run=today, anchor_day=today.day, estimated_minutes=30,
        )
        self.assertEqual(maintenance.create_recurring_tickets(), 1)
        self.assertEqual(maintenance.create_recurring_tickets(), 0)
        ticket = Ticket.objects.get(title="Backups prüfen")
        self.assertEqual(ticket.planned_for, today)
        self.assertEqual(ticket.assignee, self.second)
        item.refresh_from_db()
        self.assertGreater(item.next_run, today)

    def test_recurring_form_and_list(self):
        from tickets.models import RecurringTicket

        response = self.client.post(
            reverse("tickets:recurring_create"),
            {
                "title": "USV testen", "description": "Batterietest.", "priority": "normal",
                "interval": "quarterly", "next_run": self.monday.isoformat(),
                "lead_days": "3", "active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        item = RecurringTicket.objects.get()
        self.assertEqual(item.requester, self.agent)
        self.assertEqual(item.anchor_day, self.monday.day)
        self.assertContains(self.client.get(reverse("tickets:recurring")), "USV testen")
        self.assertEqual(
            self.client.get(reverse("tickets:recurring_edit", args=[item.pk])).status_code, 200
        )

    def test_calendar_feed_works_without_login(self):
        from tickets.planner import profile_for

        self.ticket.assignee = self.agent
        self.ticket.planned_for = timezone.localdate()
        self.ticket.estimated_minutes = 90
        self.ticket.save()
        self.assertEqual(self.client.get(reverse("tickets:planner_settings")).status_code, 200)
        token = profile_for(self.agent).calendar_token

        self.client.logout()
        response = self.client.get(f"/kalender/{token}.ics")
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertIn(f"#{self.ticket.pk} Monitor flackert (1:30 h)", text)
        self.assertEqual(self.client.get("/kalender/falsch.ics").status_code, 404)


from core.models import Announcement, Holiday, Membership, Organization
from tickets.models import RequestField, RequestForm


class OrganizationTests(Base):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.org = Organization.objects.create(name="Kunde A", email_domains="kunde-a.at")
        self.other_org = Organization.objects.create(name="Kunde B")
        self.chef = User.objects.create_user("chef", email="chef@kunde-a.at", password="pw")
        self.kollege = User.objects.create_user("kollege", email="k@kunde-a.at", password="pw")
        self.fremd = User.objects.create_user("fremd", email="f@kunde-b.at", password="pw")
        Membership.objects.create(user=self.user, organization=self.org)
        Membership.objects.create(user=self.chef, organization=self.org, is_contact=True)
        Membership.objects.create(user=self.kollege, organization=self.org)
        Membership.objects.create(user=self.fremd, organization=self.other_org, is_contact=True)
        self.org_ticket = Ticket.objects.create(
            title="Beamer defekt", description="Kein Bild.", requester=self.user
        )

    def test_ticket_belongs_to_organization_of_requester(self):
        self.assertEqual(self.org_ticket.organization, self.org)

    def test_contact_sees_all_tickets_of_own_organization_only(self):
        url = reverse("tickets:detail", args=[self.org_ticket.pk])
        self.client.login(username="chef", password="pw")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(reverse("tickets:list")), "Beamer defekt")
        self.assertContains(self.client.get(reverse("dashboard")), "Beamer defekt")
        self.client.post(reverse("tickets:comment", args=[self.org_ticket.pk]), {"body": "Dringend!"})
        self.assertEqual(self.org_ticket.comments.count(), 1)

        self.client.login(username="kollege", password="pw")  # Mitglied, kein Ansprechpartner
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.login(username="fremd", password="pw")  # Ansprechpartner von Kunde B
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertNotContains(self.client.get(reverse("tickets:list")), "Beamer defekt")

    def test_new_requester_is_assigned_by_email_domain(self):
        from tickets.services import user_for_email

        person = user_for_email("neu@kunde-a.at", "Nina Neu")
        ticket = Ticket.objects.create(title="x", description="y", requester=person)
        self.assertEqual(ticket.organization, self.org)
        self.assertEqual(Membership.objects.get(user=person).organization, self.org)

    def test_article_of_organization_is_hidden_from_others(self):
        article = Article.objects.create(
            title="VPN bei Kunde B", problem="p", solution="s",
            status=Article.Status.PUBLISHED, organization=self.other_org,
        )
        url = reverse("kb:detail", args=[article.pk])
        self.client.login(username="anna", password="pw")
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertNotContains(self.client.get(reverse("kb:list")), "VPN bei Kunde B")
        self.client.login(username="fremd", password="pw")
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_staff_manages_organizations_and_members(self):
        self.client.login(username="agent", password="pw")
        self.assertContains(self.client.get(reverse("organizations")), "Kunde A")
        url = reverse("organization_edit", args=[self.other_org.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {"member_action": "add", "user": self.second.pk})
        self.client.post(url, {"member_action": "toggle_contact", "user": self.second.pk})
        membership = Membership.objects.get(user=self.second)
        self.assertEqual(membership.organization, self.other_org)
        self.assertTrue(membership.is_contact)
        self.client.post(
            reverse("organization_create"), {"name": "Abteilung Lager", "active": "on"}
        )
        self.assertTrue(Organization.objects.filter(name="Abteilung Lager").exists())

    def test_service_report_as_page_and_pdf(self):
        begin = timezone.now() - timedelta(days=1, hours=2)
        TimeEntry.objects.create(
            ticket=self.org_ticket, user=self.agent, started_at=begin,
            ended_at=begin + timedelta(minutes=90), note="Lampe getauscht",
        )
        self.client.login(username="agent", password="pw")
        params = {
            "org": self.org.pk,
            "von": (timezone.localdate() - timedelta(days=7)).isoformat(),
            "bis": timezone.localdate().isoformat(),
        }
        page = self.client.get(reverse("tickets:service_report"), params)
        self.assertContains(page, "Lampe getauscht")
        self.assertContains(page, "1:30 h")
        pdf = self.client.get(reverse("tickets:service_report"), {**params, "format": "pdf"})
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))


class HolidayAndResponseTests(Base):
    @override_settings(HOLIDAY_COUNTRY="AT")
    def test_public_holidays_are_seeded_once(self):
        self.assertEqual(maintenance.ensure_holidays(), 26)
        self.assertEqual(maintenance.ensure_holidays(), 0)

    @override_settings(SLA_BUSINESS_HOURS=True, SLA_HOURS={"urgent": 4, "high": 8, "normal": 24, "low": 56})
    def test_due_date_skips_holiday(self):
        import datetime as dt
        from zoneinfo import ZoneInfo

        Holiday.objects.create(date=dt.date(2026, 12, 8), name="Mariä Empfängnis")
        monday = dt.datetime(2026, 12, 7, 16, 0, tzinfo=ZoneInfo("Europe/Vienna"))
        due = timezone.localtime(due_for("urgent", monday))
        self.assertEqual((due.day, due.hour), (9, 11))  # Mi 9.12., 11 Uhr

    def test_holiday_shows_in_planner_with_zero_capacity(self):
        today = timezone.localdate()
        monday = today + timedelta(days=7 - today.weekday())
        Holiday.objects.create(date=monday, name="Betriebsurlaub")
        self.client.login(username="agent", password="pw")
        page = self.client.get(reverse("tickets:planner"), {"woche": monday.isoformat()})
        self.assertContains(page, "Betriebsurlaub")

    def test_first_response_is_recorded_and_late_response_is_reported(self):
        self.assertIsNotNone(self.ticket.response_due_at)
        Ticket.objects.filter(pk=self.ticket.pk).update(
            response_due_at=timezone.now() - timedelta(minutes=5)
        )
        self.assertEqual(maintenance.escalate_overdue(), 1)
        self.assertEqual(maintenance.escalate_overdue(), 0)
        self.assertIn("Noch keine Antwort", mail.outbox[0].subject)

        self.client.login(username="agent", password="pw")
        self.assertContains(
            self.client.get(reverse("tickets:list"), {"scope": "unanswered"}), "Monitor flackert"
        )
        self.client.post(reverse("tickets:comment", args=[self.ticket.pk]), {"body": "Wir schauen."})
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.first_response_at)
        page = self.client.get(reverse("tickets:list"), {"scope": "unanswered"})
        self.assertEqual(page.context["page"].paginator.count, 0)
        self.assertEqual(self.client.get(reverse("tickets:stats")).status_code, 200)

    def test_internal_note_is_not_a_response(self):
        self.client.login(username="agent", password="pw")
        self.client.post(
            reverse("tickets:comment", args=[self.ticket.pk]), {"body": "intern", "internal": "on"}
        )
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.first_response_at)


class AnnouncementTests(Base):
    def test_banner_is_shown_until_ended(self):
        self.client.login(username="agent", password="pw")
        self.client.post(
            reverse("announcement_create"),
            {
                "title": "E-Mail-Server gestört", "text": "Wir arbeiten daran.",
                "level": "warning", "active": "on",
                "starts_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            },
        )
        item = Announcement.objects.get()
        self.assertEqual(item.created_by, self.agent)
        self.assertContains(self.client.get(reverse("announcements")), "wird angezeigt")

        self.client.login(username="anna", password="pw")
        self.assertContains(self.client.get(reverse("tickets:create")), "E-Mail-Server gestört")

        self.client.login(username="agent", password="pw")
        self.client.post(reverse("announcement_end", args=[item.pk]))
        self.client.login(username="anna", password="pw")
        self.assertNotContains(self.client.get(reverse("dashboard")), "E-Mail-Server gestört")

    def test_announcement_for_one_organization(self):
        org = Organization.objects.create(name="Kunde B")
        Announcement.objects.create(title="Nur Kunde B betroffen", organization=org)
        self.client.login(username="anna", password="pw")
        self.assertNotContains(self.client.get(reverse("dashboard")), "Nur Kunde B betroffen")
        Membership.objects.create(user=self.user, organization=org)
        self.assertContains(self.client.get(reverse("dashboard")), "Nur Kunde B betroffen")


class RequestFormTests(Base):
    def setUp(self):
        super().setUp()
        self.form = RequestForm.objects.create(name="Neuer Mitarbeiter", priority="high")
        self.name = RequestField.objects.create(
            form=self.form, label="Name", kind="text", required=True, in_title=True, position=1
        )
        self.dept = RequestField.objects.create(
            form=self.form, label="Abteilung", kind="select", required=True,
            choices="IT\nVerkauf\nLager", position=2,
        )
        self.start = RequestField.objects.create(
            form=self.form, label="Eintritt", kind="date", required=True, position=3
        )
        self.laptop = RequestField.objects.create(
            form=self.form, label="Laptop benötigt", kind="checkbox", required=False, position=4
        )
        self.url = reverse("tickets:request_form", args=[self.form.pk])
        self.client.login(username="anna", password="pw")

    def test_form_is_offered_and_required_fields_are_enforced(self):
        self.assertContains(self.client.get(reverse("tickets:create")), "Neuer Mitarbeiter")
        self.assertEqual(self.client.get(self.url).status_code, 200)
        before = Ticket.objects.count()
        response = self.client.post(self.url, {f"f{self.name.pk}": "Max Muster"})
        self.assertEqual(response.status_code, 200)  # Formular mit Fehlern erneut
        self.assertEqual(Ticket.objects.count(), before)

    def test_valid_form_creates_structured_ticket(self):
        response = self.client.post(
            self.url,
            {
                f"f{self.name.pk}": "Max Muster",
                f"f{self.dept.pk}": "IT",
                f"f{self.start.pk}": "2027-01-04",
                f"f{self.laptop.pk}": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        ticket = Ticket.objects.get(title="Neuer Mitarbeiter: Max Muster")
        self.assertEqual(ticket.priority, "high")
        self.assertIn("Abteilung: IT", ticket.description)
        self.assertIn("Eintritt: 04.01.2027", ticket.description)
        self.assertIn("Laptop benötigt: Ja", ticket.description)

    def test_staff_only_form_is_hidden_from_requesters(self):
        self.form.staff_only = True
        self.form.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)


class LinkAndListTests(Base):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.bert = User.objects.create_user("bert", email="bert@example.com", password="pw")
        self.child = Ticket.objects.create(
            title="Kein Internet (Bert)", description="x", requester=self.bert
        )
        self.client.login(username="agent", password="pw")

    def test_resolving_parent_resolves_children_and_notifies_them(self):
        self.client.post(
            reverse("tickets:link", args=[self.ticket.pk]),
            {"target": self.child.pk, "relation": "child"},
        )
        self.child.refresh_from_db()
        self.assertEqual(self.child.parent, self.ticket)
        self.assertContains(
            self.client.get(reverse("tickets:detail", args=[self.ticket.pk])), "Kein Internet (Bert)"
        )
        mail.outbox.clear()
        self.client.post(
            reverse("tickets:resolve", args=[self.ticket.pk]),
            {"solution": "Router neu gestartet.", "resolve_children": "on"},
        )
        self.child.refresh_from_db()
        self.assertEqual(self.child.status, Ticket.Status.RESOLVED)
        self.assertIn("Router neu gestartet.", self.child.solution)
        self.assertIn(["bert@example.com"], [m.to for m in mail.outbox])

    def test_related_link_and_unlink(self):
        self.client.post(
            reverse("tickets:link", args=[self.ticket.pk]),
            {"target": self.child.pk, "relation": "related"},
        )
        self.assertIn(self.ticket, self.child.related.all())
        self.client.post(reverse("tickets:unlink", args=[self.ticket.pk, self.child.pk]))
        self.assertFalse(self.ticket.related.exists())

    def test_child_cannot_become_parent(self):
        third = Ticket.objects.create(title="Drittes", description="x", requester=self.bert)
        self.child.parent = self.ticket
        self.child.save()
        self.client.post(
            reverse("tickets:link", args=[self.child.pk]),
            {"target": third.pk, "relation": "child"},
        )
        third.refresh_from_db()
        self.assertIsNone(third.parent)

    def test_long_lists_are_paged(self):
        Ticket.objects.bulk_create(
            Ticket(title=f"Massen-Ticket {i}", description="x", requester=self.user)
            for i in range(60)
        )
        first = self.client.get(reverse("tickets:list"))
        self.assertContains(first, "Seite 1 von 2")
        second = self.client.get(reverse("tickets:list"), {"seite": 2, "status": "active"})
        self.assertContains(second, "Seite 2 von 2")
        self.assertContains(second, "status=active")

    def test_time_can_be_added_to_project_task(self):
        project = Project.objects.create(name="Umzug")
        task = Task.objects.create(project=project, title="Kabel ziehen")
        self.client.post(
            reverse("projects:task_time_add", args=[task.pk]),
            {"date": timezone.localdate().isoformat(), "start": "13:00", "minutes": "30"},
        )
        entry = TimeEntry.objects.get(task=task)
        self.assertEqual(entry.seconds, 1800)
        self.assertEqual(self.client.get(reverse("projects:task_detail", args=[task.pk])).status_code, 200)


import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile

from tickets.models import ChecklistItem, ChecklistTemplate, RecurringTicket


class WaitingTests(Base):
    def setUp(self):
        super().setUp()
        self.client.login(username="agent", password="pw")

    def update(self, **data):
        payload = {"status": "open", "priority": "normal", **data}
        return self.client.post(reverse("tickets:update", args=[self.ticket.pk]), payload)

    @override_settings(SLA_BUSINESS_HOURS=False)
    def test_waiting_pauses_the_clock_and_resuming_extends_the_deadline(self):
        self.update(status="waiting")
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.sla_paused_at)

        # Zwei Tage gewartet, Zielzeit wäre inzwischen abgelaufen
        deadline = timezone.now() - timedelta(hours=1)
        Ticket.objects.filter(pk=self.ticket.pk).update(
            sla_paused_at=timezone.now() - timedelta(days=2), due_at=deadline
        )
        self.ticket.refresh_from_db()
        self.assertFalse(self.ticket.is_overdue)
        self.assertEqual(maintenance.escalate_overdue(), 0)

        self.update(status="open")
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.sla_paused_at)
        shifted = (self.ticket.due_at - deadline).total_seconds()
        self.assertAlmostEqual(shifted, 2 * 86400, delta=120)

    def test_requester_reply_ends_waiting(self):
        self.update(status="waiting")
        self.client.login(username="anna", password="pw")
        self.client.post(reverse("tickets:comment", args=[self.ticket.pk]), {"body": "Hier die Info."})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.OPEN)
        self.assertIsNone(self.ticket.sla_paused_at)

    def test_follow_up_reminds_and_reopens(self):
        today = timezone.localdate()
        self.update(status="on_hold", follow_up_on=today.isoformat(), assignee=self.agent.pk)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.ON_HOLD)
        self.assertIsNotNone(self.ticket.sla_paused_at)
        self.assertContains(
            self.client.get(reverse("tickets:list"), {"scope": "followup"}), "Wiedervorlage"
        )
        mail.outbox.clear()
        self.assertEqual(maintenance.process_follow_ups(), 1)
        self.assertEqual(maintenance.process_follow_ups(), 0)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.OPEN)
        self.assertIsNone(self.ticket.follow_up_on)
        self.assertIn("Wiedervorlage", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ["agent@example.com"])

    @override_settings(WAITING_REMINDER_DAYS=3, WAITING_CLOSE_DAYS=10, AUTO_CLOSE_DAYS=7)
    def test_reminder_then_automatic_closing(self):
        now = timezone.now()
        Ticket.objects.filter(pk=self.ticket.pk).update(
            status=Ticket.Status.WAITING, sla_paused_at=now - timedelta(days=4)
        )
        self.assertEqual(maintenance.remind_and_close(), 1)
        self.assertEqual(maintenance.remind_and_close(), 0)  # nur einmal erinnern
        self.assertIn("Wir warten auf Ihre Rückmeldung", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ["anna@example.com"])

        Ticket.objects.filter(pk=self.ticket.pk).update(sla_paused_at=now - timedelta(days=11))
        self.assertEqual(maintenance.remind_and_close(), 1)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.CLOSED)
        self.assertIn("Geschlossen", mail.outbox[-1].subject)

    @override_settings(AUTO_CLOSE_DAYS=7)
    def test_resolved_ticket_is_closed_after_a_week(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(
            status=Ticket.Status.RESOLVED, resolved_at=timezone.now() - timedelta(days=8)
        )
        other = Ticket.objects.create(title="Frisch gelöst", description="x", requester=self.user)
        Ticket.objects.filter(pk=other.pk).update(
            status=Ticket.Status.RESOLVED, resolved_at=timezone.now() - timedelta(days=2)
        )
        self.assertEqual(maintenance.remind_and_close(), 1)
        self.ticket.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.CLOSED)
        self.assertEqual(other.status, Ticket.Status.RESOLVED)


class ChecklistAndSearchTests(Base):
    def setUp(self):
        super().setUp()
        self.template = ChecklistTemplate.objects.create(
            name="Eintritt", items="Konto anlegen\nHandy ausgeben\n\nSchlüssel übergeben"
        )
        self.client.login(username="agent", password="pw")

    def test_template_and_single_items_can_be_checked_off(self):
        url = reverse("tickets:checklist_add", args=[self.ticket.pk])
        self.client.post(url, {"template": self.template.pk})
        self.client.post(url, {"text": "Fahrzeug zuweisen"})
        items = list(self.ticket.checklist.all())
        self.assertEqual(
            [i.text for i in items],
            ["Konto anlegen", "Handy ausgeben", "Schlüssel übergeben", "Fahrzeug zuweisen"],
        )
        change = reverse("tickets:checklist_change", args=[self.ticket.pk, items[0].pk])
        self.client.post(change)
        items[0].refresh_from_db()
        self.assertTrue(items[0].done)
        self.assertEqual(items[0].done_by, self.agent)
        page = self.client.get(reverse("tickets:detail", args=[self.ticket.pk]))
        self.assertContains(page, "1 von 4 erledigt")
        self.assertContains(page, "noch Punkte offen")
        self.client.post(change, {"delete": "1"})
        self.assertEqual(self.ticket.checklist.count(), 3)

    def test_request_form_and_recurring_ticket_bring_their_checklist(self):
        form = RequestForm.objects.create(name="Neuer Mitarbeiter", checklist=self.template)
        field = RequestField.objects.create(form=form, label="Name", in_title=True)
        self.client.post(
            reverse("tickets:request_form", args=[form.pk]), {f"f{field.pk}": "Max Muster"}
        )
        ticket = Ticket.objects.get(title="Neuer Mitarbeiter: Max Muster")
        self.assertEqual(ticket.checklist.count(), 3)

        today = timezone.localdate()
        RecurringTicket.objects.create(
            title="Quartalsprüfung", description="x", requester=self.agent,
            interval="quarterly", next_run=today, anchor_day=today.day, checklist=self.template,
        )
        maintenance.create_recurring_tickets()
        self.assertEqual(Ticket.objects.get(title="Quartalsprüfung").checklist.count(), 3)

    def test_search_covers_replies_and_solution_but_hides_internal_notes(self):
        Comment.objects.create(ticket=self.ticket, author=self.agent, body="Seriennummer XK-4711 notiert")
        Comment.objects.create(
            ticket=self.ticket, author=self.agent, body="Lieferant Geheimfirma angerufen", internal=True
        )
        other = Ticket.objects.create(
            title="Drucker", description="streikt", requester=self.user, solution="Fixiereinheit getauscht"
        )

        def found(query):
            page = self.client.get(reverse("tickets:list"), {"q": query, "status": "all"})
            return {t.pk for t in page.context["page"]}

        self.assertEqual(found("XK-4711"), {self.ticket.pk})
        self.assertEqual(found("monitor seriennummer"), {self.ticket.pk})  # beide Wörter nötig
        self.assertEqual(found("Fixiereinheit"), {other.pk})
        self.assertEqual(found(f"#{other.pk}"), {other.pk})
        self.assertEqual(found("Geheimfirma"), {self.ticket.pk})

        self.client.login(username="anna", password="pw")
        self.assertEqual(found("Geheimfirma"), set())
        self.assertEqual(found("XK-4711"), {self.ticket.pk})


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PhotoTests(Base):
    def test_photo_field_stores_attachment(self):
        self.client.login(username="anna", password="pw")
        self.assertContains(self.client.get(reverse("tickets:create")), 'capture="environment"')
        self.client.post(
            reverse("tickets:create"),
            {
                "title": "Sicherung fliegt", "description": "Siehe Foto.", "priority": "normal",
                "photos": [SimpleUploadedFile("foto.jpg", b"\xff\xd8\xff\xe0 bild", content_type="image/jpeg")],
            },
        )
        ticket = Ticket.objects.get(title="Sicherung fliegt")
        self.assertEqual([a.name for a in ticket.attachments.all()], ["foto.jpg"])


class OverviewTests(Base):
    def setUp(self):
        super().setUp()
        self.client.login(username="agent", password="pw")

    def test_kind_can_be_set_filtered_and_is_shown(self):
        self.client.post(
            reverse("tickets:update", args=[self.ticket.pk]),
            {"status": "new", "priority": "normal", "kind": "bug"},
        )
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.kind, "bug")
        other = Ticket.objects.create(
            title="Dunkles Design", description="x", requester=self.user, kind="nice"
        )

        def found(kind):
            page = self.client.get(reverse("tickets:list"), {"art": kind})
            return {t.pk for t in page.context["page"]}

        self.assertEqual(found("bug"), {self.ticket.pk})
        self.assertEqual(found("nice"), {other.pk})
        self.assertEqual(found("feature"), set())
        self.assertContains(
            self.client.get(reverse("tickets:detail", args=[self.ticket.pk])), "Fehler"
        )

    def test_requester_can_choose_kind_when_creating(self):
        self.client.login(username="anna", password="pw")
        self.client.post(
            reverse("tickets:create"),
            {"title": "Export als Excel", "description": "Wäre praktisch.", "priority": "low", "kind": "feature"},
        )
        self.assertEqual(Ticket.objects.get(title="Export als Excel").kind, "feature")

    def test_overview_counts_new_done_and_open(self):
        from tickets import overview

        now = timezone.now()
        old = Ticket.objects.create(title="Alt offen", description="x", requester=self.user, kind="bug")
        Ticket.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=40))
        done = Ticket.objects.create(title="Alt erledigt", description="x", requester=self.user)
        Ticket.objects.filter(pk=done.pk).update(
            created_at=now - timedelta(days=40),
            status=Ticket.Status.RESOLVED,
            closed_at=now - timedelta(days=3),
        )
        long_gone = Ticket.objects.create(title="Längst erledigt", description="x", requester=self.user)
        Ticket.objects.filter(pk=long_gone.pk).update(
            created_at=now - timedelta(days=60),
            status=Ticket.Status.CLOSED,
            closed_at=now - timedelta(days=50),
        )

        data = overview.build(days=30)
        self.assertEqual(data["opening"], 2)        # "Alt offen" und "Alt erledigt"
        self.assertEqual(data["new_today"], 1)      # das Ticket aus der Grundausstattung
        self.assertEqual(data["total_created"], 1)
        self.assertEqual(data["total_closed"], 1)
        self.assertEqual(data["open_count"], 2)     # 2 + 1 neu - 1 erledigt
        self.assertEqual(data["change"], 0)
        self.assertEqual(data["rows"][-1]["open"], 2)
        self.assertEqual(len(data["rows"]), 30)

        only_bugs = overview.build(days=14, kind="bug")
        self.assertEqual(only_bugs["open_count"], 1)
        self.assertEqual(overview.build(days=90)["bar_unit"], "je Kalenderwoche")

    def test_resolving_and_reopening_keeps_closed_at_in_step(self):
        self.client.post(
            reverse("tickets:resolve", args=[self.ticket.pk]), {"solution": "Kabel getauscht."}
        )
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.closed_at)
        self.client.post(reverse("tickets:reopen", args=[self.ticket.pk]))
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.closed_at)

    def test_dashboard_shows_charts_and_filters(self):
        page = self.client.get(reverse("dashboard"), {"tage": "14", "art": "none"})
        self.assertContains(page, "Entwicklung der letzten 14 Tage")
        self.assertContains(page, 'class="viz"', count=2)
        self.assertContains(page, "Heute neu angelegt")
        self.assertContains(page, "Monitor flackert")
        self.assertEqual(self.client.get(reverse("dashboard"), {"tage": "abc"}).status_code, 200)
        self.assertEqual(self.client.get(reverse("tickets:stats")).status_code, 200)


class PoolTests(Base):
    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.monday = today - timedelta(days=today.weekday())
        self.other = Ticket.objects.create(
            title="Switch tauschen", description="x", requester=self.user, estimated_minutes=120
        )
        self.client.login(username="agent", password="pw")

    def add(self, *tickets, week=None):
        return self.client.post(
            reverse("tickets:pool_add"),
            {"tickets": [t.pk for t in tickets], "woche": (week or self.monday).isoformat()},
        )

    def test_planning_fills_the_pool_and_people_take_tickets(self):
        page = self.client.get(reverse("tickets:pool"))
        self.assertContains(page, "Der Pool dieser Woche ist noch leer")
        self.assertEqual(len(page.context["candidates"]), 2)

        self.add(self.ticket, self.other)
        page = self.client.get(reverse("tickets:pool"))
        self.assertEqual({t.pk for t in page.context["free"]}, {self.ticket.pk, self.other.pk})
        self.assertEqual(len(page.context["candidates"]), 0)
        self.assertEqual(self.client.get(reverse("dashboard")).context["pool_free_count"], 2)

        self.client.post(reverse("tickets:pool_take", args=[self.ticket.pk]))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.agent)
        self.assertEqual(self.ticket.pool_week, self.monday)

        # Ein Kollege kann ein schon vergebenes Ticket nicht mehr übernehmen
        self.client.login(username="zweiter", password="pw")
        self.client.post(reverse("tickets:pool_take", args=[self.ticket.pk]))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.agent)

        # ... wohl aber das freie, und gleich mit der Arbeit beginnen
        self.client.post(reverse("tickets:pool_take", args=[self.other.pk]), {"start": "1"})
        self.other.refresh_from_db()
        self.assertEqual(self.other.assignee, self.second)
        self.assertEqual(self.other.status, Ticket.Status.OPEN)
        self.assertTrue(TimeEntry.objects.filter(ticket=self.other, user=self.second).exists())

        page = self.client.get(reverse("tickets:pool"))
        self.assertEqual(page.context["free"], [])
        self.assertEqual(page.context["taken_count"], 2)
        self.assertEqual(page.context["groups"][0]["user"], self.second)  # eigene zuerst

    def test_planner_assigns_tickets_and_view_can_be_limited_to_own(self):
        # Beim Planen gleich zuordnen: ein Ticket an den Kollegen ...
        self.client.post(
            reverse("tickets:pool_add"),
            {"tickets": [self.ticket.pk], "woche": self.monday.isoformat(), "assignee": self.second.pk},
        )
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.second)
        self.assertIn(["zweiter@example.com"], [m.to for m in mail.outbox])
        # ... das andere frei in den Pool und dann mir selbst zuordnen
        self.add(self.other)
        self.client.post(reverse("tickets:pool_assign", args=[self.other.pk]), {"user": self.agent.pk})
        self.other.refresh_from_db()
        self.assertEqual(self.other.assignee, self.agent)

        everyone = self.client.get(reverse("tickets:pool"), {"ansicht": "alle"})
        self.assertEqual(
            [g["user"] for g in everyone.context["groups"]], [self.agent, self.second]
        )
        self.assertContains(everyone, "Nicht zugeordnet")

        own = self.client.get(reverse("tickets:pool"), {"ansicht": "meine"})
        self.assertEqual([g["user"] for g in own.context["groups"]], [self.agent])
        self.assertNotContains(own, "Monitor flackert")
        # Die Wahl bleibt beim nächsten Aufruf erhalten
        self.assertEqual(self.client.get(reverse("tickets:pool")).context["view"], "meine")

        # Zuordnung aufheben: Ticket ist wieder frei
        self.client.post(reverse("tickets:pool_assign", args=[self.other.pk]), {"user": ""})
        self.other.refresh_from_db()
        self.assertIsNone(self.other.assignee)
        self.assertEqual(self.other.pool_week, self.monday)

    def test_release_done_and_unplanned_work(self):
        self.add(self.ticket)
        self.client.post(reverse("tickets:pool_take", args=[self.ticket.pk]))
        self.client.post(reverse("tickets:pool_release", args=[self.ticket.pk]))
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.assignee)
        self.assertEqual(self.ticket.pool_week, self.monday)

        # Pool-Ticket und ein ungeplantes Ticket werden gelöst
        self.client.post(reverse("tickets:resolve", args=[self.ticket.pk]), {"solution": "Erledigt."})
        self.client.post(reverse("tickets:resolve", args=[self.other.pk]), {"solution": "Nebenbei."})
        page = self.client.get(reverse("tickets:pool"))
        self.assertEqual([t.pk for t in page.context["done"]], [self.ticket.pk])
        self.assertEqual(page.context["percent_done"], 100)
        self.assertEqual(page.context["unplanned_done"], 1)

    def test_leftovers_are_carried_into_the_new_week(self):
        last_week = self.monday - timedelta(days=7)
        self.add(self.ticket, week=last_week)
        page = self.client.get(reverse("tickets:pool"))
        self.assertEqual(page.context["leftovers"], 1)
        self.client.post(reverse("tickets:pool_carry"), {"woche": self.monday.isoformat()})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.pool_week, self.monday)

    def test_pool_in_planner_ticket_page_and_list(self):
        self.add(self.ticket)
        planner = self.client.get(reverse("tickets:planner"))
        self.assertEqual([t.pk for _, t in planner.context["pool"]], [self.ticket.pk])
        self.assertNotIn(self.ticket.pk, [t.pk for _, t in planner.context["backlog"]])

        # In der Planung auf einen Tag ziehen: bleibt im Pool, bekommt Tag und Bearbeiter
        self.client.post(
            reverse("tickets:planner_move"),
            data=json.dumps({"kind": "ticket", "id": self.ticket.pk,
                             "date": self.monday.isoformat(), "user": self.second.pk}),
            content_type="application/json",
        )
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.pool_week, self.ticket.assignee), (self.monday, self.second))

        # Aus "Noch nicht geplant" in den Pool ziehen und wieder zurück
        move = lambda **extra: self.client.post(
            reverse("tickets:planner_move"),
            data=json.dumps({"kind": "ticket", "id": self.other.pk, "date": None,
                             "keep_user": True, **extra}),
            content_type="application/json",
        )
        move(pool=self.monday.isoformat())
        self.other.refresh_from_db()
        self.assertEqual(self.other.pool_week, self.monday)
        move(unpool=True)
        self.other.refresh_from_db()
        self.assertIsNone(self.other.pool_week)

        detail = self.client.get(reverse("tickets:detail", args=[self.ticket.pk]))
        self.assertContains(detail, "Aus dem Wochenpool nehmen")
        listed = self.client.get(reverse("tickets:list"), {"scope": "pool"})
        self.assertEqual({t.pk for t in listed.context["page"]}, {self.ticket.pk})
        self.client.post(reverse("tickets:pool_remove", args=[self.ticket.pk]))
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.pool_week)


class BrandTests(Base):
    def test_default_brand_is_neutral(self):
        page = self.client.get(reverse("login"))
        self.assertContains(page, "<b>Helpdesk</b>")
        self.assertNotContains(page, "brand-ebner.css")

    @override_settings(BRAND="ebner")
    def test_brand_from_setting(self):
        page = self.client.get(reverse("login"))
        self.assertContains(page, "<b>ebner</b>.ticket")
        self.assertContains(page, "css/brand-ebner.css")
        self.assertContains(page, "<title>Anmelden · ebner.ticket</title>")

    @override_settings(BRAND="ebner", BRAND_HOSTS={"forstenlechner.ticket": "forstenlechner"})
    def test_brand_follows_hostname(self):
        page = self.client.get(reverse("login"), HTTP_HOST="forstenlechner.ticket")
        self.assertContains(page, "<b>forstenlechner</b>.ticket")
        self.assertContains(self.client.get(reverse("login")), "<b>ebner</b>.ticket")

    def test_staff_can_preview_a_brand(self):
        self.client.login(username="anna", password="pw")
        page = self.client.get(reverse("dashboard"), {"design": "ebner"})
        self.assertNotContains(page, "brand-ebner.css")  # Melder können nichts umstellen

        self.client.login(username="agent", password="pw")
        self.assertContains(self.client.get(reverse("dashboard"), {"design": "ebner"}), "brand-ebner.css")
        self.assertContains(self.client.get(reverse("tickets:list")), "brand-ebner.css")  # bleibt
        page = self.client.get(reverse("dashboard"), {"design": "aus"})
        self.assertNotContains(page, "brand-ebner.css")

    @override_settings(BRAND="forstenlechner")
    def test_ticket_title_uses_brand_name(self):
        self.client.login(username="agent", password="pw")
        self.assertContains(self.client.get(reverse("tickets:list")), "<title>Tickets · forstenlechner.ticket</title>")
