"""TDD unit tests for communication message and event domain invariants."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from dunvyr.communication.domain.events import (
    ChatMember,
    InvalidEvent,
    MemberJoinedEvent,
    MessageEvent,
)
from dunvyr.communication.domain.message import (
    MESSAGE_MAX_LENGTH,
    InvalidMessage,
    Message,
    MessageAuthor,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
CAMPAIGN_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_CAMPAIGN_ID = UUID("99999999-9999-4999-8999-999999999999")
AUTHOR_ID = UUID("11111111-1111-4111-8111-111111111111")
MESSAGE_ID = UUID("33333333-3333-4333-8333-333333333333")
CLIENT_MESSAGE_ID = UUID("44444444-4444-4444-8444-444444444444")
EVENT_ID = UUID("55555555-5555-4555-8555-555555555555")


def author(**overrides: object) -> MessageAuthor:
    values: dict[str, object] = {
        "campaign_id": CAMPAIGN_ID,
        "guest_id": AUTHOR_ID,
        "nickname": "Алиса",
    }
    values.update(overrides)
    return MessageAuthor(**values)  # type: ignore[arg-type]


def message(**overrides: object) -> Message:
    values: dict[str, object] = {
        "id": MESSAGE_ID,
        "campaign_id": CAMPAIGN_ID,
        "author_id": AUTHOR_ID,
        "author_nickname": "Алиса",
        "client_message_id": CLIENT_MESSAGE_ID,
        "content": "Привет",
        "created_at": NOW,
    }
    values.update(overrides)
    return Message(**values)  # type: ignore[arg-type]


@pytest.mark.unit
def test_message_create_binds_the_author_to_the_campaign() -> None:
    created = Message.create(
        id=MESSAGE_ID,
        campaign_id=CAMPAIGN_ID,
        author=author(),
        client_message_id=CLIENT_MESSAGE_ID,
        content="  Привет  ",
        created_at=NOW,
    )

    assert created.id == MESSAGE_ID
    assert created.campaign_id == CAMPAIGN_ID
    assert created.author_id == AUTHOR_ID
    assert created.author_nickname == "Алиса"
    assert created.client_message_id == CLIENT_MESSAGE_ID
    assert created.content == "Привет"
    assert created.created_at == NOW


@pytest.mark.unit
def test_message_cannot_be_created_for_an_author_of_another_campaign() -> None:
    with pytest.raises(InvalidMessage, match="author"):
        Message.create(
            id=MESSAGE_ID,
            campaign_id=CAMPAIGN_ID,
            author=author(campaign_id=OTHER_CAMPAIGN_ID),
            client_message_id=CLIENT_MESSAGE_ID,
            content="Привет",
            created_at=NOW,
        )


@pytest.mark.unit
@pytest.mark.parametrize("content", ["", "   ", "x" * (MESSAGE_MAX_LENGTH + 1)])
def test_message_rejects_blank_or_overlong_content(content: str) -> None:
    with pytest.raises(InvalidMessage, match="content"):
        Message.create(
            id=MESSAGE_ID,
            campaign_id=CAMPAIGN_ID,
            author=author(),
            client_message_id=CLIENT_MESSAGE_ID,
            content=content,
            created_at=NOW,
        )


@pytest.mark.unit
def test_message_rejects_naive_timestamps_and_non_uuid_identifiers() -> None:
    with pytest.raises(InvalidMessage, match="created_at"):
        Message.create(
            id=MESSAGE_ID,
            campaign_id=CAMPAIGN_ID,
            author=author(),
            client_message_id=CLIENT_MESSAGE_ID,
            content="Привет",
            created_at=datetime(2026, 1, 1, 12, 0),
        )
    with pytest.raises(InvalidMessage, match="id"):
        message(id="not-a-uuid")


@pytest.mark.unit
def test_message_is_immutable() -> None:
    created = message()

    with pytest.raises(FrozenInstanceError):
        created.content = "Другое"  # type: ignore[misc]


@pytest.mark.unit
def test_message_event_requires_a_positive_sequence_and_consistent_campaign() -> None:
    event = MessageEvent.create(
        event_id=EVENT_ID,
        sequence=1,
        occurred_at=NOW,
        message=message(),
    )

    assert event.campaign_id == CAMPAIGN_ID
    assert event.message.id == MESSAGE_ID

    with pytest.raises(InvalidEvent, match="sequence"):
        MessageEvent.create(
            event_id=EVENT_ID,
            sequence=0,
            occurred_at=NOW,
            message=message(),
        )
    with pytest.raises(InvalidEvent, match="campaign"):
        MessageEvent(
            event_id=EVENT_ID,
            campaign_id=OTHER_CAMPAIGN_ID,
            sequence=1,
            occurred_at=NOW,
            message=message(),
        )


@pytest.mark.unit
def test_member_joined_event_validates_its_member() -> None:
    member = ChatMember(
        guest_id=AUTHOR_ID,
        nickname="Боб",
        role="player",
        joined_at=NOW,
    )
    event = MemberJoinedEvent.create(
        event_id=EVENT_ID,
        campaign_id=CAMPAIGN_ID,
        sequence=2,
        occurred_at=NOW,
        member=member,
    )

    assert event.member.nickname == "Боб"
    assert event.campaign_id == CAMPAIGN_ID

    with pytest.raises(InvalidEvent, match="member"):
        MemberJoinedEvent.create(
            event_id=EVENT_ID,
            campaign_id=CAMPAIGN_ID,
            sequence=2,
            occurred_at=NOW,
            member=ChatMember(
                guest_id=AUTHOR_ID,
                nickname="",
                role="player",
                joined_at=NOW,
            ),
        )


@pytest.mark.unit
def test_events_are_immutable() -> None:
    event = MessageEvent.create(
        event_id=EVENT_ID,
        sequence=1,
        occurred_at=NOW,
        message=message(),
    )

    with pytest.raises(FrozenInstanceError):
        event.sequence = 2  # type: ignore[misc]
