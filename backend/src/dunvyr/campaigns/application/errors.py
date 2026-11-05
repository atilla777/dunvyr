"""Application-level campaign failures mapped to HTTP by the presentation layer."""

from __future__ import annotations


class CampaignNotFound(Exception):
    """The requested campaign does not exist."""


class CampaignAccessDenied(Exception):
    """The viewer is not a member and must not learn more about the campaign."""


class DuplicateIdempotencyKey(Exception):
    """The database rejected a second campaign for the same organizer and key."""
