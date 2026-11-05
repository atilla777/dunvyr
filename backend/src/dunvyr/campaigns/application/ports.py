"""Ports the campaigns application layer depends on."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from dunvyr.campaigns.domain.campaign import Campaign

Clock = Callable[[], datetime]
IdFactory = Callable[[], UUID]


class CampaignRepository(Protocol):
    def add(self, campaign: Campaign) -> None: ...

    def get(self, campaign_id: UUID) -> Campaign | None: ...

    def find_by_organizer_and_idempotency_key(
        self,
        organizer_id: UUID,
        idempotency_key: UUID,
    ) -> Campaign | None: ...


class UnitOfWork(Protocol):
    @property
    def campaigns(self) -> CampaignRepository: ...

    def commit(self) -> None: ...


class InvitationSecretGenerator(Protocol):
    def generate(self) -> str: ...
