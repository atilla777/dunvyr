from uuid import UUID, uuid4

import pytest

from dunvyr.campaigns.application.presence import PresenceRuntime
from dunvyr.campaigns.public import PresenceState


@pytest.mark.unit
def test_revision_grace_reconnect_and_campaign_isolation() -> None:
    class Publisher:
        def __init__(self) -> None:
            self.events: list[tuple[UUID, PresenceState]] = []

        def publish(self, campaign_id: UUID, state: PresenceState) -> None:
            self.events.append((campaign_id, state))

    publisher = Publisher()
    now = [0.0]
    runtime = PresenceRuntime(publisher, clock=lambda: now[0])
    campaign, other, guest, tab1, tab2 = (uuid4() for _ in range(5))
    assert runtime.read(campaign).revision == 0
    runtime.connect(campaign, guest, tab1)
    runtime.connect(campaign, guest, tab2)
    assert runtime.read(campaign).revision == 1
    assert runtime.read(other).online_guest_ids == ()
    runtime.disconnect(tab1)
    runtime.disconnect(tab2)
    now[0] = 4.999
    runtime.connect(campaign, guest, tab1)
    assert runtime.read(campaign).revision == 1
    runtime.disconnect(tab1)
    now[0] = 9.999
    runtime.sweep()
    state = runtime.read(campaign)
    assert state.revision == 2
    assert state.online_guest_ids == ()
    assert [(cid, state.revision) for cid, state in publisher.events] == [
        (campaign, 1),
        (campaign, 2),
    ]
    fresh = PresenceRuntime(Publisher(), clock=lambda: now[0]).read(campaign)
    assert fresh.epoch != state.epoch
    assert fresh.revision == 0
