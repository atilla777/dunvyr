"""Application-level campaign failures mapped to HTTP by the presentation layer."""

from __future__ import annotations


class CampaignNotFound(Exception):
    """The requested campaign does not exist."""


class CampaignAccessDenied(Exception):
    """The viewer is not a member and must not learn more about the campaign."""


class DuplicateIdempotencyKey(Exception):
    """The database rejected a second campaign for the same organizer and key."""


class InvitationUnavailable(Exception):
    """The invitation secret is unknown or its invitation was revoked."""


class NoFreeSeats(Exception):
    """The campaign cannot accept another member."""


class NicknameTaken(Exception):
    """Another member of the campaign already uses the guest nickname."""


class MembershipInsertConflict(Exception):
    """The database rejected a member insert that raced with another join."""
