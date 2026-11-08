from uuid import uuid4

import pytest

from dunvyr.campaigns.domain.presence import Presence


@pytest.mark.unit
def test_connection_makes_guest_online() -> None:
    presence = Presence()
    campaign, guest, connection = uuid4(), uuid4(), uuid4()
    presence.connect(campaign, guest, connection, now=0.0)
    assert presence.online(campaign, now=0.0) == (guest,)


@pytest.mark.unit
def test_tabs_and_grace_boundary() -> None:
    presence = Presence()
    campaign, guest, first, second = (uuid4() for _ in range(4))
    presence.connect(campaign, guest, first, now=0.0)
    presence.connect(campaign, guest, second, now=1.0)
    presence.disconnect(first, now=2.0)
    assert presence.online(campaign, now=2.0) == (guest,)
    presence.disconnect(second, now=3.0)
    assert presence.online(campaign, now=7.999) == (guest,)
    assert presence.online(campaign, now=8.0) == ()


@pytest.mark.unit
def test_lease_expiry_is_anchored_to_deadline_even_if_swept_late() -> None:
    presence = Presence()
    campaign, guest, connection = uuid4(), uuid4(), uuid4()
    presence.connect(campaign, guest, connection, now=0.0)
    presence.sweep(now=36.0)
    assert presence.online(campaign, now=36.0) == ()
    presence.disconnect(connection, now=37.0)
    assert presence.online(campaign, now=37.0) == ()


@pytest.mark.unit
def test_renew_only_existing_unexpired_connection() -> None:
    presence = Presence()
    campaign, guest, connection = uuid4(), uuid4(), uuid4()
    presence.connect(campaign, guest, connection, now=0.0)
    assert presence.renew(connection, now=29.0)
    presence.sweep(now=35.0)
    assert presence.online(campaign, now=35.0) == (guest,)
    assert not presence.renew(connection, now=59.0)
    presence.sweep(now=64.0)
    assert presence.online(campaign, now=64.0) == ()


@pytest.mark.unit
def test_late_sweep_uses_last_actual_lease_deadline() -> None:
    presence = Presence()
    campaign, guest, first, second = (uuid4() for _ in range(4))
    presence.connect(campaign, guest, first, now=2.0)
    presence.connect(campaign, guest, second, now=0.0)
    presence.sweep(now=36.0)
    assert presence.online(campaign, now=36.0) == (guest,)
    presence.sweep(now=37.0)
    assert presence.online(campaign, now=37.0) == ()
