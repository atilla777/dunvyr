"""Private invalidations target an authenticated guest's subscriptions only."""

import asyncio
from uuid import uuid4

import pytest

from dunvyr.communication.infrastructure.realtime import RealtimeHub

pytestmark = pytest.mark.unit


def test_private_invalidation_targets_all_owner_tabs_and_not_other_guests() -> None:
    async def scenario() -> None:
        hub = RealtimeHub()
        send = getattr(hub, "proposals_changed", None)
        assert callable(send), "hub must support guest-targeted proposal invalidations"
        campaign, other_campaign, owner, other = uuid4(), uuid4(), uuid4(), uuid4()
        subscriptions = [
            hub.subscribe(campaign, owner),
            hub.subscribe(campaign, owner),
            hub.subscribe(campaign, other),
            hub.subscribe(other_campaign, owner),
        ]
        send(campaign, owner)
        await asyncio.sleep(0)
        frame = {"type": "proposals_changed", "campaign_id": str(campaign)}
        assert subscriptions[0][1].get_nowait() == frame
        assert subscriptions[1][1].get_nowait() == frame
        assert subscriptions[2][1].empty() and subscriptions[3][1].empty()

    asyncio.run(scenario())
