"""Zuordnung von Benutzern zu Organisationen und daraus folgende Sichtbarkeit."""

from django.db.models import Q

from .models import Membership, Organization


def membership_of(user):
    """Zuordnung des Benutzers oder None.

    Fragt bewusst die Datenbank, statt ``user.membership`` zu verwenden:
    Django merkt sich am Benutzerobjekt auch "keine Zuordnung", und eine kurz
    danach angelegte Zuordnung bliebe sonst unsichtbar.
    """
    if user is None or not user.pk:
        return None
    return Membership.objects.filter(user=user).select_related("organization").first()


def organization_for(user):
    """Organisation eines Benutzers.

    Hat er noch keine, wird über die Domain seiner E-Mail-Adresse zugeordnet,
    falls eine Organisation diese Domain führt.
    """
    membership = membership_of(user)
    if membership is not None:
        return membership.organization
    if user is None or not user.pk:
        return None
    domain = (user.email or "").rpartition("@")[2].lower()
    if not domain:
        return None
    for organization in Organization.objects.filter(active=True).exclude(email_domains=""):
        if domain in organization.domain_list:
            Membership.objects.create(user=user, organization=organization)
            return organization
    return None


def contact_organization(user):
    """Organisation, deren Tickets der Benutzer als Ansprechpartner alle sehen darf."""
    membership = membership_of(user)
    if membership is not None and membership.is_contact:
        return membership.organization
    return None


def ticket_filter(user):
    """Filter für alle Tickets, die ein Nicht-Bearbeiter sehen darf."""
    organization = contact_organization(user)
    if organization is not None:
        return Q(requester=user) | Q(organization=organization)
    return Q(requester=user)


def can_view_ticket(user, ticket):
    if user.is_staff or ticket.requester_id == user.id:
        return True
    organization = contact_organization(user)
    return organization is not None and ticket.organization_id == organization.id
