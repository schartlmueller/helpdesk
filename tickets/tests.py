from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from kb.models import Article
from kb.services import search_articles

from .models import Ticket


class TicketToKnowledgeBaseTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.agent = User.objects.create_user("agent", password="pw", is_staff=True)
        self.user = User.objects.create_user("anna", password="pw")
        self.ticket = Ticket.objects.create(
            title="Drucker druckt nur leere Seiten",
            description="Der Drucker im zweiten Stock gibt nur weiße Blätter aus.",
            requester=self.user,
        )

    def test_resolving_creates_draft_and_publishing_makes_it_searchable(self):
        self.client.login(username="agent", password="pw")
        response = self.client.post(
            reverse("tickets:resolve", args=[self.ticket.pk]),
            {"solution": "Tonerkartusche getauscht.", "create_article": "on"},
        )
        self.assertEqual(response.status_code, 302)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.RESOLVED)
        self.assertTrue(self.ticket.comments.filter(is_solution=True).exists())

        article = Article.objects.get(source_ticket=self.ticket)
        self.assertEqual(article.status, Article.Status.DRAFT)
        self.assertEqual(search_articles("Drucker leere Seiten"), [])

        self.client.post(reverse("kb:publish", args=[article.pk]))
        article.refresh_from_db()
        self.assertEqual(article.status, Article.Status.PUBLISHED)
        self.assertEqual(search_articles("Drucker leere Seiten"), [article])

    def test_resolving_without_checkbox_creates_no_article(self):
        self.client.login(username="agent", password="pw")
        self.client.post(
            reverse("tickets:resolve", args=[self.ticket.pk]),
            {"solution": "Neu gestartet."},
        )
        self.assertFalse(Article.objects.exists())

    def test_requester_cannot_see_drafts_or_foreign_tickets(self):
        other = get_user_model().objects.create_user("bert", password="pw")
        foreign = Ticket.objects.create(title="x", description="y", requester=other)
        draft = Article.objects.create(title="t", problem="p", solution="s")

        self.client.login(username="anna", password="pw")
        self.assertEqual(
            self.client.get(reverse("tickets:detail", args=[foreign.pk])).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("kb:detail", args=[draft.pk])).status_code, 404
        )
        self.assertEqual(
            self.client.post(reverse("tickets:resolve", args=[self.ticket.pk])).status_code,
            403,
        )

    def test_pages_render(self):
        self.client.login(username="agent", password="pw")
        for name in [
            "dashboard", "tickets:list", "tickets:create", "tickets:times", "tickets:stats",
            "kb:list", "kb:drafts", "kb:create", "projects:list", "projects:create",
            "password_change",
        ]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertEqual(
            self.client.get(reverse("tickets:detail", args=[self.ticket.pk])).status_code, 200
        )


import tempfile

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from .mail_in import process_message
from .models import Attachment, TimeEntry


class TimeTrackingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.agent = User.objects.create_user("agent", password="pw", is_staff=True)
        self.user = User.objects.create_user("anna", password="pw")
        self.ticket = Ticket.objects.create(
            title="Monitor flackert", description="Seit heute.", requester=self.user
        )
        self.client.login(username="agent", password="pw")

    def running(self):
        return TimeEntry.objects.filter(ticket=self.ticket, ended_at__isnull=True).count()

    def test_start_pause_resume_and_stop_on_resolve(self):
        self.client.post(reverse("tickets:start", args=[self.ticket.pk]))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.OPEN)
        self.assertEqual(self.ticket.assignee, self.agent)
        self.assertEqual(self.running(), 1)

        self.client.post(reverse("tickets:pause", args=[self.ticket.pk]))
        self.assertEqual(self.running(), 0)

        self.client.post(reverse("tickets:start", args=[self.ticket.pk]))
        self.assertEqual(self.running(), 1)
        self.assertEqual(TimeEntry.objects.filter(ticket=self.ticket).count(), 2)

        self.client.post(
            reverse("tickets:resolve", args=[self.ticket.pk]), {"solution": "Kabel getauscht."}
        )
        self.assertEqual(self.running(), 0)

    def test_only_one_running_timer_per_agent(self):
        other = Ticket.objects.create(title="Zweites", description="x", requester=self.user)
        self.client.post(reverse("tickets:start", args=[self.ticket.pk]))
        self.client.post(reverse("tickets:start", args=[other.pk]))
        self.assertEqual(self.running(), 0)
        self.assertEqual(TimeEntry.objects.filter(ended_at__isnull=True).count(), 1)

    def test_report_and_detail_render(self):
        self.client.post(reverse("tickets:start", args=[self.ticket.pk]))
        self.assertEqual(self.client.get(reverse("tickets:times")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("tickets:detail", args=[self.ticket.pk])).status_code, 200
        )


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AttachmentTests(TestCase):
    def test_upload_and_protected_download(self):
        User = get_user_model()
        User.objects.create_user("anna", password="pw")
        User.objects.create_user("bert", password="pw")

        self.client.login(username="anna", password="pw")
        response = self.client.post(
            reverse("tickets:create"),
            {
                "title": "Fehlermeldung",
                "description": "Siehe Anhang.",
                "priority": "normal",
                "files": [SimpleUploadedFile("fehler.txt", b"Fehler 42")],
            },
        )
        self.assertEqual(response.status_code, 302)
        attachment = Attachment.objects.get()
        self.assertEqual(attachment.name, "fehler.txt")

        url = reverse("tickets:attachment", args=[attachment.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"Fehler 42")

        self.client.login(username="bert", password="pw")
        self.assertEqual(self.client.get(url).status_code, 403)


def _raw_mail(sender, subject, body="Die VPN-Verbindung bricht ab.", extra=""):
    return (
        f"From: {sender}\r\n"
        "To: helpdesk@example.com\r\n"
        f"Subject: {subject}\r\n"
        f"{extra}"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"{body}\r\n"
    ).encode()


class MailInTests(TestCase):
    def test_new_mail_creates_ticket_and_reply_becomes_comment(self):
        ticket = process_message(_raw_mail("Anna Muster <anna@example.com>", "VPN geht nicht"))
        self.assertEqual(ticket.title, "VPN geht nicht")
        self.assertEqual(ticket.requester.email, "anna@example.com")
        self.assertIn(f"[Ticket #{ticket.pk}]", mail.outbox[0].subject)

        again = process_message(
            _raw_mail("anna@example.com", f"Re: {mail.outbox[0].subject}", "Jetzt geht es wieder.")
        )
        self.assertEqual(again, ticket)
        self.assertEqual(ticket.comments.get().body, "Jetzt geht es wieder.")
        self.assertEqual(Ticket.objects.count(), 1)

    def test_stranger_cannot_write_into_foreign_ticket(self):
        ticket = process_message(_raw_mail("anna@example.com", "VPN geht nicht"))
        other = process_message(_raw_mail("eve@example.org", f"Re: [Ticket #{ticket.pk}] Hallo"))
        self.assertNotEqual(other, ticket)
        self.assertEqual(ticket.comments.count(), 0)

    def test_automatic_mails_are_ignored(self):
        raw = _raw_mail(
            "anna@example.com", "Abwesend", extra="Auto-Submitted: auto-replied\r\n"
        )
        self.assertIsNone(process_message(raw))
        self.assertEqual(Ticket.objects.count(), 0)
