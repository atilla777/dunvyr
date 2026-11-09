"""Post-commit private proposal invalidation delivery."""

from uuid import UUID

from dunvyr.communication.infrastructure.realtime import RealtimeHub


class ProposalNotifier:
    def __init__(self, hub: RealtimeHub) -> None:
        self.hub = hub

    def notify(self, campaign_id: UUID, actor_id: UUID) -> None:
        self.hub.proposals_changed(campaign_id, actor_id)
